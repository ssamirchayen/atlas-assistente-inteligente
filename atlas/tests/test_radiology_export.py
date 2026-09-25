import hashlib
import json

import numpy as np
import pytest

from atlas.radiology.cases import CaseError
from atlas.radiology.export_bundle import export_bundle, write_stl
from atlas.radiology.reconstruction_lab import create_reconstruction_lab


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    root = tmp_path_factory.mktemp("export") / "lab"
    create_reconstruction_lab(root)
    return (root / "case/case.json", root / "annotations.json", root / "geometry.json",
            root / "reconstruction-settings.json")


def test_rejected_default_contains_no_mesh(inputs, tmp_path):
    out = tmp_path / "blocked"
    report = export_bundle(*inputs, out)
    assert report["status"] == "blocked"
    assert report["approved"] is False
    assert report["mesh_included"] is False
    assert not list(out.glob("*.stl")) and not list(out.glob("*.obj"))
    assert report["reasons"] == ["high_contour_sensitivity"]
    with pytest.raises(CaseError):
        export_bundle(*inputs, out)


def test_diagnostic_keeps_rejection_and_integrity(inputs, tmp_path):
    out = tmp_path / "diagnostic"
    report = export_bundle(*inputs, out, diagnostic=True)
    assert report["status"] == "rejected_diagnostic_only"
    assert report["approved"] is False
    assert (out / "REJECTED_envelope.stl").is_file()
    for name, record in report["files"].items():
        raw = (out / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == record["sha256"]
        assert len(raw) == record["bytes"]
    assert json.loads((out / "bundle.json").read_text()) == report
    obj = (out / "REJECTED_envelope.obj").read_text()
    stl = (out / "REJECTED_envelope.stl").read_text()
    vertices = [list(map(float, line.split()[1:])) for line in obj.splitlines() if line.startswith("v ")]
    faces = [[int(n)-1 for n in line.split()[1:]] for line in obj.splitlines() if line.startswith("f ")]
    stl_vertices = [list(map(float, line.split()[1:])) for line in stl.splitlines()
                    if line.strip().startswith("vertex ")]
    np.testing.assert_array_equal(np.asarray(vertices)[faces].reshape(-1, 3), stl_vertices)
    assert report["units"] == "mm" and report["coordinate_system"] == "LPS"


def test_stl_normal_and_coordinates(tmp_path):
    out = tmp_path / "one.stl"
    write_stl(out, [[0, 0, 0], [2, 0, 0], [0, 3, 0]], [[0, 1, 2]], "TEST")
    text = out.read_text()
    assert "facet normal 0 0 1" in text
    assert "vertex 2 0 0" in text and "vertex 0 3 0" in text


def test_invalid_triangle(tmp_path):
    with pytest.raises(CaseError):
        write_stl(tmp_path / "bad.stl", [[0, 0, 0]] * 3, [[0, 1, 2]], "TEST")
    assert not (tmp_path / "bad.stl").exists()


def test_invalid_mode(inputs, tmp_path):
    with pytest.raises(CaseError):
        export_bundle(*inputs, tmp_path / "bad", diagnostic="yes")


def test_failed_mesh_export_cleans_output(inputs, tmp_path, monkeypatch):
    import atlas.radiology.export_bundle as module

    def fail(*args):
        raise OSError("simulated disk failure")
    monkeypatch.setattr(module, "write_stl", fail)
    with pytest.raises(OSError):
        export_bundle(*inputs, tmp_path / "failed", diagnostic=True)
    assert not (tmp_path / "failed").exists()
