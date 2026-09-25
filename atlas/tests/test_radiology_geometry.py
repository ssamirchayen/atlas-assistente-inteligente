import json

import numpy as np
import pytest

from atlas.radiology.cases import CaseError
from atlas.radiology.geometry import create_geometry_demo, project, validate_geometry


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "geometry.json"
    create_geometry_demo(path)
    return path


def test_analytic_projection():
    k = np.diag([100., 100., 1.])
    result = project(k, np.eye(3), np.array([1, 2, 3]), np.array([[3, 6, 13]]))
    np.testing.assert_allclose(result, [[20, 40]])


def test_demo(config):
    report = validate_geometry(config)
    assert report["status"] == "geometry_consistent"
    assert not report["physical_calibration_verified"]
    assert not report["reconstruction_available"]
    for view in report["views"].values():
        assert view["max_error_px"] < 1e-9
        assert np.asarray(view["projection_matrix"]).shape == (3, 4)
    assert sorted(round(p["optical_axis_angle_deg"]) for p in report["pairs"]) == [45, 45, 90]


def test_residual_blocks(config):
    data = json.loads(config.read_text())
    data["views"]["AP"]["observed_px"][0][0] += 3
    config.write_text(json.dumps(data))
    result = validate_geometry(config)
    assert result["status"] == "blocked"
    assert result["views"]["AP"]["max_error_px"] == pytest.approx(3)


@pytest.mark.parametrize("fault", ["rotation", "reflection", "intrinsics", "coincident",
                                  "planar", "duplicate", "behind", "nan", "boolean",
                                  "units", "outside", "research", "missing", "limit"])
def test_invalid_geometry(config, fault):
    data = json.loads(config.read_text())
    ap = data["views"]["AP"]
    if fault == "rotation":
        ap["R_world_to_camera"][0][0] = 3
    elif fault == "reflection":
        ap["R_world_to_camera"][0] = [-x for x in ap["R_world_to_camera"][0]]
    elif fault == "intrinsics":
        ap["K"][0][0] = 0
    elif fault == "coincident":
        data["views"]["OBLIQUE"] = ap
    elif fault == "planar":
        for p in data["points_lps_mm"]:
            p[2] = 0
    elif fault == "duplicate":
        data["points_lps_mm"][0] = data["points_lps_mm"][1]
    elif fault == "behind":
        ap["center_lps_mm"] = [0, 1000, 0]
    elif fault == "nan":
        ap["K"][0][0] = float("nan")
    elif fault == "boolean":
        ap["K"][0][0] = True
    elif fault == "units":
        data["coordinate_system"] = "LPS_cm"
    elif fault == "outside":
        ap["observed_px"][0][0] = -1
    elif fault == "research":
        data["origin"] = "research"
    elif fault == "missing":
        del data["views"]["LATERAL"]
    else:
        data["max_error_px"] = 1000
    config.write_text(json.dumps(data))
    with pytest.raises(CaseError):
        validate_geometry(config)


def test_no_overwrite(config):
    before = config.read_bytes()
    with pytest.raises(FileExistsError):
        create_geometry_demo(config)
    assert config.read_bytes() == before


def test_cli(config, tmp_path):
    from atlas.radiology.__main__ import main

    assert main(["geometry-check", str(config), "--output", str(tmp_path / "report.json")]) == 0
    assert main(["geometry-check", str(config), "--output", str(config)]) == 1


@pytest.mark.parametrize("fault", [None, "binding", "resolution"])
def test_research_binding(config, tmp_path, fault):
    from atlas.radiology.lab import create_demo_2d
    from atlas.radiology.quality import analyze_quality

    # Synthetic test fixture exercises the declared research branch only.
    create_demo_2d(tmp_path / "lab")
    manifest = tmp_path / "lab/case/case.json"
    case = json.loads(manifest.read_text())
    case["data_origin"] = "research"
    manifest.write_text(json.dumps(case))
    evidence = analyze_quality(manifest)
    data = json.loads(config.read_text())
    data["origin"] = "research"
    data["case_binding"] = {
        "manifest_sha256": evidence["manifest_sha256"],
        "images": {v: info["source_sha256"] for v, info in evidence["views"].items()},
    }
    for spec in data["views"].values():
        spec["image_size"] = [256, 256]
        spec["K"][:2] = (np.asarray(spec["K"][:2]) / 4).tolist()
        spec["observed_px"] = (np.asarray(spec["observed_px"]) / 4).tolist()
    if fault == "binding":
        data["case_binding"]["images"]["AP"] = "0" * 64
    if fault == "resolution":
        data["views"]["AP"]["image_size"] = [512, 512]
    config.write_text(json.dumps(data))
    if fault:
        with pytest.raises(CaseError):
            validate_geometry(config, manifest)
    else:
        assert validate_geometry(config, manifest)["status"] == "geometry_consistent"
