"""Display-image screening and explicit human acquisition review."""

import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from atlas.radiology.cases import image_path, require, validate_case
from atlas.radiology.imaging import decode_image, read_image_bytes
from atlas.radiology.privacy import VIEWS, digest, now, read_json, write_json


def screen_pixels(preview_png: bytes):
    """Heuristics on 8-bit rendered pixels, not detector exposure measurements."""
    with Image.open(io.BytesIO(preview_png)) as im:
        values = np.asarray(im.convert("L"), dtype=np.float64)
    low, high = np.percentile(values, [1, 99])
    flags = []
    if values.min() == values.max():
        flags.append("constant_display_image")
    if high - low < 16:
        flags.append("narrow_display_range")
    if min(values.shape) < 256:
        flags.append("small_display_image")
    return {
        "display_width": int(values.shape[1]),
        "display_height": int(values.shape[0]),
        "display_p01": round(float(low), 3),
        "display_p99": round(float(high), 3),
        "display_std": round(float(values.std()), 3),
        "display_black_fraction": round(float((values == 0).mean()), 6),
        "display_white_fraction": round(float((values == 255).mean()), 6),
        "flags": flags,
    }


def analyze_quality(manifest: Path):
    validate_case(manifest)
    raw_manifest = manifest.read_bytes()
    case = json.loads(raw_manifest)
    views = {}
    for item in case["views"]:
        path = image_path(manifest.parent, item["relative_path"])
        raw = read_image_bytes(path)
        require(digest(raw) == item["sha256"], "checksum", "Imagem alterada.")
        decoded = decode_image(raw, path.suffix)
        # Only allowlisted laterality, never emit arbitrary DICOM field text.
        side = decoded.identity.get("ImageLaterality", "")
        side = side if side in {"L", "R"} else "unknown"
        metrics = screen_pixels(decoded.preview_png)
        if side != "unknown" and side != case["laterality"]:
            metrics["flags"].append("dicom_laterality_conflict")
        views[item["view"]] = {
            **metrics, "source_sha256": digest(raw),
            "source_width": decoded.metadata["width"],
            "source_height": decoded.metadata["height"],
            "dicom_laterality": side,
            "projection_status": "declared_not_verified",
        }
    return {
        "schema_version": 1, "algorithm": "display_screen_v1",
        "manifest_sha256": digest(raw_manifest),
        "declared_laterality": case["laterality"],
        "synthetic": case["data_origin"] == "synthetic",
        "views": views, "status": "human_review_required",
        "metrics_scope": "rendered_8bit_preview_max1600",
        "anatomy_or_projection_verified": False,
        "clinical_use_validated": False, "reconstruction_available": False,
    }


def review_quality(manifest: Path, review_file: Path, output: Path):
    """Recompute evidence so approvals cannot silently apply to changed inputs."""
    report = analyze_quality(manifest)
    review = read_json(review_file)
    require(isinstance(review, dict) and set(review) == {
        "schema_version", "manifest_sha256", "views"}
        and type(review["schema_version"]) is int and review["schema_version"] == 1
        and review["manifest_sha256"] == report["manifest_sha256"]
        and isinstance(review["views"], dict) and set(review["views"]) == set(VIEWS),
        "quality_review", "Revisão incompleta ou de outro manifesto.")
    reasons = []
    for name in VIEWS:
        entry = review["views"][name]
        require(isinstance(entry, dict) and set(entry) == {
            "source_sha256", "observed_projection", "observed_laterality",
            "anatomy_coverage", "positioning", "image_quality", "flags_reviewed"},
            "quality_review", "Preencha todos os campos de cada vista.")
        require(entry["source_sha256"] == report["views"][name]["source_sha256"],
                "quality_changed", "Imagem diferente da revisão registrada.")
        require(all(isinstance(entry[k], str) for k in (
            "observed_projection", "observed_laterality", "anatomy_coverage",
            "positioning", "image_quality")),
            "quality_review", "Campos de revisão devem conter texto.")
        require(entry["observed_projection"] in {*VIEWS, "unknown"}
                and entry["observed_laterality"] in {"L", "R", "unknown"}
                and all(entry[k] in {"acceptable", "reject", "unknown"}
                        for k in ("anatomy_coverage", "positioning", "image_quality"))
                and type(entry["flags_reviewed"]) is bool,
                "quality_review", "Use somente os valores previstos no modelo.")
        if entry["observed_projection"] != name:
            reasons.append(name + ":projection_unconfirmed_or_mismatch")
        if entry["observed_laterality"] != report["declared_laterality"]:
            reasons.append(name + ":laterality_unconfirmed_or_mismatch")
        for field in ("anatomy_coverage", "positioning", "image_quality"):
            if entry[field] != "acceptable":
                reasons.append(name + ":" + field)
        if not entry["flags_reviewed"]:
            reasons.append(name + ":flags_not_reviewed")
        flags = report["views"][name]["flags"]
        for flag in ("constant_display_image", "dicom_laterality_conflict"):
            if flag in flags:
                reasons.append(name + ":" + flag)
    result = {
        **report, "status": "blocked" if reasons else "human_review_recorded",
        "reviewed_at": now(), "review_sha256": digest(review_file.read_bytes()),
        "review": review["views"], "blocking_reasons": reasons,
        "eligible_for_geometry_stage": not reasons and not report["synthetic"],
        "synthetic_exercise_only": report["synthetic"],
    }
    write_json(output, result)
    return result


def write_review_template(report, output):
    write_json(output, {
        "schema_version": 1, "manifest_sha256": report["manifest_sha256"],
        "views": {name: {
            "source_sha256": report["views"][name]["source_sha256"],
            "observed_projection": "unknown", "observed_laterality": "unknown",
            "anatomy_coverage": "unknown", "positioning": "unknown",
            "image_quality": "unknown", "flags_reviewed": False,
        } for name in VIEWS},
    })
