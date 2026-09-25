"""Validate supplied pinhole geometry against known calibration landmarks."""

import math
from pathlib import Path

import numpy as np

from atlas.radiology.cases import require
from atlas.radiology.privacy import VIEWS, digest, read_json, write_json
from atlas.radiology.quality import analyze_quality


def array(value, shape):
    def numeric(v):
        try:
            return (all(numeric(x) for x in v) if isinstance(v, list)
                    else type(v) in (int, float) and math.isfinite(v))
        except OverflowError:
            return False
    require(numeric(value), "geometry_numbers", "Use números finitos, sem booleanos.")
    try:
        result = np.asarray(value, dtype=float)
    except (ValueError, TypeError, OverflowError):
        require(False, "geometry_shape", "Dimensões numéricas inválidas.")
    require(result.shape == shape and np.isfinite(result).all()
            and (np.abs(result) <= 1e9).all(),
            "geometry_shape", "Dimensões ou escala numérica inválidas.")
    return result


def camera(spec):
    require(isinstance(spec, dict) and set(spec) == {
        "K", "R_world_to_camera", "center_lps_mm", "image_size", "observed_px"},
        "camera_fields", "Campos da câmera inválidos.")
    k = array(spec["K"], (3, 3))
    r = array(spec["R_world_to_camera"], (3, 3))
    c = array(spec["center_lps_mm"], (3,))
    size = spec["image_size"]
    require(isinstance(size, list) and len(size) == 2
            and all(type(x) is int and 1 <= x <= 16000 for x in size),
            "detector_size", "Use largura e altura em pixels de origem.")
    require(np.allclose(k[2], [0, 0, 1], atol=1e-9, rtol=0)
            and abs(k[1, 0]) < 1e-9 and k[0, 0] > 0 and k[1, 1] > 0
            and 0 <= k[0, 2] < size[0] and 0 <= k[1, 2] < size[1],
            "intrinsics", "Matriz intrínseca inválida.")
    require(np.allclose(r @ r.T, np.eye(3), atol=1e-6, rtol=0)
            and abs(np.linalg.det(r) - 1) < 1e-6,
            "rotation", "Rotação deve ser ortonormal, com determinante +1.")
    return k, r, c


def project(k, r, c, points):
    local = (r @ (points - c).T).T
    require((local[:, 2] > 1e-6).all(), "behind_detector",
            "Pontos devem estar à frente das câmeras.")
    homogeneous = (k @ local.T).T
    return homogeneous[:, :2] / homogeneous[:, 2, None]


def validate_geometry(config: Path, manifest: Path | None = None):
    data = read_json(config)
    require(isinstance(data, dict) and set(data) == {
        "schema_version", "origin", "coordinate_system", "pixel_convention",
        "distortion", "max_error_px", "points_lps_mm", "views", "case_binding"}
        and type(data["schema_version"]) is int and data["schema_version"] == 1,
        "geometry_schema", "Contrato de geometria inválido.")
    require(data["origin"] in ("synthetic", "research")
            and data["coordinate_system"] == "LPS_mm"
            and data["pixel_convention"] == "pixel_centers_zero_based"
            and data["distortion"] == "rectified_pinhole",
            "geometry_convention", "Use LPS em mm e pixels retificados, origem zero.")
    limit = data["max_error_px"]
    require(type(limit) in (int, float) and math.isfinite(limit) and 0 < limit <= 10,
            "error_limit", "Limite de erro deve estar entre 0 e 10 pixels.")
    require(isinstance(data["points_lps_mm"], list)
            and 6 <= len(data["points_lps_mm"]) <= 1000,
            "landmarks", "Forneça de 6 a 1000 pontos conhecidos de calibração.")
    points = array(data["points_lps_mm"], (len(data["points_lps_mm"]), 3))
    singular = np.linalg.svd(points - points.mean(axis=0), compute_uv=False)
    require(singular[-1] > 1e-3 and singular[-1] / singular[0] > 1e-4
            and len(np.unique(points, axis=0)) == len(points),
            "landmark_geometry", "Use pontos distintos com distribuição tridimensional.")
    require(isinstance(data["views"], dict) and set(data["views"]) == set(VIEWS),
            "geometry_views", "Geometria exige AP, LATERAL e OBLIQUE.")
    for spec in data["views"].values():
        camera(spec)
    if data["origin"] == "research":
        require(manifest is not None, "case_required", "Vincule o caso original de pesquisa.")
        evidence = analyze_quality(manifest)
        binding = {"manifest_sha256": evidence["manifest_sha256"],
                   "images": {v: evidence["views"][v]["source_sha256"] for v in VIEWS}}
        require(not evidence["synthetic"] and data["case_binding"] == binding,
                "case_binding", "Geometria não corresponde ao caso original.")
        for v in VIEWS:
            require(data["views"][v].get("image_size") == [
                evidence["views"][v]["source_width"], evidence["views"][v]["source_height"]],
                "source_size", "Coordenadas devem usar resolução original.")
    else:
        require(data["case_binding"] is None and manifest is None,
                "synthetic_binding", "LAB sintético não pode validar um caso real.")
    cameras, reports = {}, {}
    for name in VIEWS:
        spec = data["views"][name]
        k, r, c = camera(spec)
        observed = array(spec["observed_px"], (len(points), 2))
        require((observed >= 0).all()
                and (observed < np.asarray(spec["image_size"])).all(),
                "landmark_pixels", "Pontos observados fora do detector.")
        predicted = project(k, r, c, points)
        residual = np.linalg.norm(predicted - observed, axis=1)
        matrix = k @ np.column_stack((r, -r @ c))
        reports[name] = {"projection_matrix": matrix.tolist(),
                         "rms_error_px": float(np.sqrt(np.mean(residual ** 2))),
                         "max_error_px": float(residual.max()),
                         "within_tolerance": bool((residual <= limit).all())}
        cameras[name] = (r, c)
    pairs = []
    for i, first in enumerate(VIEWS):
        for second in VIEWS[i + 1:]:
            r1, c1 = cameras[first]
            r2, c2 = cameras[second]
            baseline = float(np.linalg.norm(c1 - c2))
            angle = float(np.degrees(np.arccos(np.clip(r1[2] @ r2[2], -1, 1))))
            require(baseline >= 1 and 5 <= angle <= 175, "degenerate_views",
                    "Vistas coincidentes ou com separação angular insuficiente.")
            pairs.append({"views": [first, second], "baseline_mm": baseline,
                          "optical_axis_angle_deg": angle})
    passed = all(v["within_tolerance"] for v in reports.values())
    return {"schema_version": 1, "status": "geometry_consistent" if passed else "blocked",
            "config_sha256": digest(config.read_bytes()), "origin": data["origin"],
            "coordinate_system": "LPS_mm", "views": reports, "pairs": pairs,
            "max_error_threshold_px": limit, "physical_calibration_verified": False,
            "clinical_use_validated": False, "reconstruction_available": False,
            "scope": "supplied_geometry_vs_supplied_landmarks"}


def create_geometry_demo(output: Path):
    points = np.array([[x, y, z] for x in (-50, 50) for y in (-50, 50)
                       for z in (-50, 50)], dtype=float)
    k = np.array([[1200, 0, 512], [0, 1200, 512], [0, 0, 1]], dtype=float)
    views = {}
    for name, degrees in (("AP", 0), ("LATERAL", 90), ("OBLIQUE", 45)):
        angle = math.radians(degrees)
        center = 1000 * np.array([math.sin(angle), -math.cos(angle), 0])
        z = -center / np.linalg.norm(center)
        y = np.array([0., 0., -1.])
        x = np.cross(y, z)
        r = np.stack((x, y, z))
        views[name] = {"K": k.tolist(), "R_world_to_camera": r.tolist(),
                       "center_lps_mm": center.tolist(), "image_size": [1024, 1024],
                       "observed_px": project(k, r, center, points).tolist()}
    write_json(output, {"schema_version": 1, "origin": "synthetic",
                       "coordinate_system": "LPS_mm",
                       "pixel_convention": "pixel_centers_zero_based",
                       "distortion": "rectified_pinhole", "max_error_px": 2,
                       "points_lps_mm": points.tolist(), "views": views,
                       "case_binding": None})
