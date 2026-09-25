import json

import numpy as np
import pytest

from atlas.radiology.__main__ import main
from atlas.radiology.cases import CaseError
from atlas.radiology.reconstruction_lab import create_reconstruction_lab
from atlas.radiology.uncertainty import assess, boundary, decision


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
    path = tmp_path_factory.mktemp("sensitivity") / "lab"
    create_reconstruction_lab(path)
    return path


def run(lab, out, radius=1):
    return assess(lab / "case/case.json", lab / "annotations.json", lab / "geometry.json",
                  lab / "reconstruction-settings.json", out, radius)


def test_envelopes_nested_and_repeatable(lab, tmp_path):
    a = run(lab, tmp_path / "a")
    b = run(lab, tmp_path / "b")
    assert a["core_voxels"] <= a["nominal_voxels"] <= a["outer_voxels"]
    assert a["sensitive_fraction_of_outer"] == b["sensitive_fraction_of_outer"]
    assert a["clinical_confidence_available"] is False
    with np.load(tmp_path / "a/sensitivity.npz", allow_pickle=False) as data:
        assert not (data["core"] & ~data["nominal"]).any()
        assert not (data["nominal"] & ~data["outer"]).any()
        assert np.array_equal(data["sensitive_shell"], data["outer"] & ~data["core"])
    with pytest.raises(CaseError):
        run(lab, tmp_path / "a")


def test_larger_perturbation_widens_envelope(lab, tmp_path):
    a = run(lab, tmp_path / "a", 1)
    b = run(lab, tmp_path / "b", 3)
    assert b["core_voxels"] <= a["core_voxels"]
    assert b["outer_voxels"] >= a["outer_voxels"]


@pytest.mark.parametrize("radius", [0, 4, True, 1.5])
def test_invalid_radius(lab, tmp_path, radius):
    with pytest.raises(CaseError):
        run(lab, tmp_path / "bad", radius)
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("core,outer,roi,clip,iou,coverage,reason", [
    (0, 10, False, False, 1, 1, "empty_eroded_core"),
    (4, 10, False, False, 1, 1, "high_contour_sensitivity"),
    (10, 10, True, False, 1, 1, "roi_boundary"),
    (10, 10, False, True, 1, 1, "detector_boundary"),
    (10, 10, False, False, .69, 1, "low_reprojection_agreement"),
    (10, 10, False, False, 1, .79, "low_reprojection_agreement"),
])
def test_rejections(core, outer, roi, clip, iou, coverage, reason):
    assert reason in decision({"AP": {"silhouette_iou": iou, "target_coverage": coverage}},
                              core, outer, roi, clip)


def test_thresholds_and_boundary():
    assert not decision({"AP": {"silhouette_iou": .7, "target_coverage": .8}},
                        5, 10, False, False)
    mask = np.zeros((4, 4, 4), dtype=bool)
    mask[2, 2, 2] = True
    assert not boundary(mask)
    mask[0, 2, 2] = True
    assert boundary(mask)


def test_cli(lab, tmp_path):
    out = tmp_path / "cli"
    code = main(["sensitivity", str(lab / "case/case.json"),
                 "--annotation", str(lab / "annotations.json"),
                 "--geometry", str(lab / "geometry.json"),
                 "--settings", str(lab / "reconstruction-settings.json"),
                 "--output", str(out)])
    report = json.loads((out / "assessment.json").read_text())
    assert code == (2 if report["reasons"] else 0)
