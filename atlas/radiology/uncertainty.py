"""Deterministic contour sensitivity, never a calibrated probability."""

import shutil
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from atlas.radiology.cases import require
from atlas.radiology.geometry import camera
from atlas.radiology.privacy import VIEWS, digest, read_json, write_json
from atlas.radiology.reconstruction import carve, grid_points, reconstruct


def boundary(mask):
    return bool(any(np.any(np.take(mask, edge, axis=axis))
                    for axis in range(3) for edge in (0, -1)))


def decision(metrics, core_count, outer_count, roi_touched, clipped):
    """Fixed research screening policy; thresholds are not clinical limits."""
    reasons = []
    if core_count == 0:
        reasons.append("empty_eroded_core")
    if outer_count == 0 or (outer_count-core_count)/max(outer_count, 1) > .5:
        reasons.append("high_contour_sensitivity")
    if roi_touched:
        reasons.append("roi_boundary")
    if clipped:
        reasons.append("detector_boundary")
    if any(v["silhouette_iou"] < .70 or v["target_coverage"] < .80
           for v in metrics.values()):
        reasons.append("low_reprojection_agreement")
    return reasons


def assess(manifest, annotation, geometry, settings, output, radius_px=1):
    require(type(radius_px) is int and 1 <= radius_px <= 3,
            "sensitivity_radius", "Raio inteiro deve ser de 1 a 3 pixels.")
    require(not output.exists(), "output_exists", "Use uma pasta nova.")
    # Recompute from validated inputs instead of trusting editable result metrics.
    with tempfile.TemporaryDirectory(prefix="atlas-sensitivity-") as temporary:
        from pathlib import Path

        result = Path(temporary) / "baseline"
        baseline = read_json(reconstruct(manifest, annotation, geometry, settings, result))
        config, ann, geo = map(read_json, (settings, annotation, geometry))
        points, _, counts, bounds = grid_points(config["bounds_lps_mm"], config["voxel_size_mm"])
        cameras, eroded, dilated = {}, {}, {}
        clipped = False
        for name in VIEWS:
            view = ann["views"][name]
            mask = Image.new("L", tuple(view["size"]), 0)
            painter = ImageDraw.Draw(mask)
            for polygon in view["polygons"]:
                if polygon["bone"] == config["bone"]:
                    painter.polygon([tuple(p) for p in polygon["points"]], fill=255)
            raw = np.asarray(mask) > 0
            r = radius_px
            clipped |= bool(raw[:r+1].any() or raw[-r-1:].any()
                            or raw[:, :r+1].any() or raw[:, -r-1:].any())
            padded = ImageOps.expand(mask, border=r, fill=0)
            crop = (r, r, mask.width+r, mask.height+r)
            eroded[name] = np.asarray(padded.filter(ImageFilter.MinFilter(2*r+1)).crop(crop)) > 0
            dilated[name] = np.asarray(padded.filter(ImageFilter.MaxFilter(2*r+1)).crop(crop)) > 0
            cameras[name] = camera(geo["views"][name])
        core = carve(points, cameras, eroded).reshape(tuple(counts))
        outer = carve(points, cameras, dilated).reshape(tuple(counts))
        with np.load(result / "volume.npz", allow_pickle=False) as data:
            nominal = data["occupied"].copy()
        require(not (core & ~nominal).any() and not (nominal & ~outer).any(),
                "sensitivity_nesting", "Falha na inclusão dos envelopes.")
        shell = outer & ~core
        reasons = decision(baseline["reprojection"], int(core.sum()), int(outer.sum()),
                           boundary(outer), clipped)
        report = {
            "schema_version": 1,
            "status": "rejected_for_research_review" if reasons else "research_review_required",
            "reasons": reasons, "policy": "contour_screen_v1",
            "thresholds": {"min_iou": .70, "min_coverage": .80, "max_shell_fraction": .5},
            "radius_px": radius_px, "perturbation": "square_morphology_all_views",
            "core_voxels": int(core.sum()), "nominal_voxels": int(nominal.sum()),
            "outer_voxels": int(outer.sum()),
            "sensitive_fraction_of_outer": float(shell.sum()/max(outer.sum(), 1)),
            "outer_touches_roi": boundary(outer), "near_detector_boundary": clipped,
            "reprojection": baseline["reprojection"],
            "inputs_sha256": {name: digest(path.read_bytes()) for name, path in
                              zip(("manifest", "annotation", "geometry", "settings"),
                                  (manifest, annotation, geometry, settings), strict=True)},
            "clinical_use_validated": False, "clinical_confidence_available": False,
            "fracture_preservation_verified": False,
            "limitations": ["No camera or calibration perturbations",
                            "No anatomical or fracture verification",
                            "Not a probability or confidence interval",
                            "Reprojection reuses reconstruction inputs"],
        }
        output.mkdir(parents=True, exist_ok=False)
        try:
            np.savez_compressed(output / "sensitivity.npz", core=core, nominal=nominal,
                                outer=outer, sensitive_shell=shell,
                                origin_lps_mm=bounds[0], voxel_size_mm=config["voxel_size_mm"])
            report["sensitivity_sha256"] = digest((output / "sensitivity.npz").read_bytes())
            write_json(output / "assessment.json", report)
        except Exception:
            shutil.rmtree(output)
            raise
        return report
