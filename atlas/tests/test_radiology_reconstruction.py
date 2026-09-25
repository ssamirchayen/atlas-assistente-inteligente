import json
import shutil

import numpy as np
import pytest

from atlas.radiology.cases import CaseError
from atlas.radiology.reconstruction import carve, grid_points, reconstruct, write_surface
from atlas.radiology.reconstruction_lab import create_reconstruction_lab


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
    root = tmp_path_factory.mktemp("reconstruction") / "lab"
    create_reconstruction_lab(root)
    return root


def run(root, output):
    return reconstruct(root / "case/case.json", root / "annotations.json",
                       root / "geometry.json", root / "reconstruction-settings.json", output)


def test_lab_generates_volume_mesh_and_reprojection(lab):
    report = json.loads((lab / "result/reconstruction-report.json").read_text())
    assert report["status"] == "experimental_envelope_generated"
    assert 100 < report["occupied_voxels"] < 20000
    assert not report["clinical_use_validated"] and not report["anatomical_prior_used"]
    assert not report["equivalent_to_ct"]
    assert all(0 <= v["silhouette_iou"] <= 1 for v in report["reprojection"].values())
    score = json.loads((lab / "synthetic-comparison.json").read_text())
    assert score["dice_vs_ellipsoid_on_same_grid"] > .65
    assert (lab / "result/envelope.obj").stat().st_size > 100


def test_grid_centers_and_units():
    points, _, shape, _ = grid_points([[0,0,0],[2,2,2]], 1)
    np.testing.assert_allclose(points[0], [.5,.5,.5])
    np.testing.assert_allclose(points[-1], [1.5,1.5,1.5])
    assert tuple(shape) == (2,2,2)


@pytest.mark.parametrize("bounds,spacing", [
    ([[0,0,0],[1,1,1]], 0), ([[0,0,0],[1,1,1]], True),
    ([[0,0,0],[2.2,2,2]], 1), ([[0,0,0],[128,128,128]], 1),
    ([[0,0,0],[-1,2,2]], 1), ([[0,0,0],[100000,2,2]], 1),
])
def test_grid_limits(bounds, spacing):
    with pytest.raises(CaseError):
        grid_points(bounds, spacing)


def test_carving_analytic_camera():
    masks = {name: np.zeros((10,10), dtype=bool) for name in ("AP","LATERAL","OBLIQUE")}
    for mask in masks.values():
        mask[2,1] = True
    cameras = {name: (np.eye(3),np.eye(3),np.zeros(3)) for name in masks}
    points = np.array([[1.,2.,1.], [3.,4.,1.], [1.,2.,-1.]])
    np.testing.assert_array_equal(carve(points,cameras,masks), [True,False,False])


def test_surface_single_cell(tmp_path):
    path = tmp_path / "mesh.obj"
    result = write_surface(path,np.ones((1,1,1),dtype=bool),np.zeros(3),2)
    assert result == {"vertices":8,"triangles":12}
    vertices = [list(map(float,line.split()[1:])) for line in path.read_text().splitlines() if line.startswith("v ")]
    assert np.asarray(vertices).min() == 0 and np.asarray(vertices).max() == 2


def test_shared_face_removed(tmp_path):
    result = write_surface(tmp_path / "mesh.obj",np.ones((2,1,1),dtype=bool),np.zeros(3),1)
    assert result["triangles"] == 20


@pytest.mark.parametrize("fault", ["missing_contour", "mapping", "geometry", "origin", "empty"])
def test_reconstruction_rejects(lab, tmp_path, fault):
    root = tmp_path / "lab"
    shutil.copytree(lab, root)
    if fault in ("missing_contour", "empty"):
        path = root / "annotations.json"
        data = json.loads(path.read_text())
        if fault == "missing_contour":
            data["views"]["AP"]["polygons"] = []
        else:
            data["views"]["AP"]["polygons"][0]["points"] = [[0,0],[2,0],[0,2]]
    else:
        path = root / "geometry.json"
        data = json.loads(path.read_text())
        if fault == "mapping":
            data["views"]["AP"]["image_size"] = [512,512]
        elif fault == "geometry":
            data["views"]["AP"]["observed_px"][0][0] += 5
        else:
            data["origin"] = "research"
    path.write_text(json.dumps(data))
    with pytest.raises(CaseError):
        run(root,tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_boundary_warning(lab,tmp_path):
    root = tmp_path / "lab"
    shutil.copytree(lab,root)
    path = root / "reconstruction-settings.json"
    data = json.loads(path.read_text())
    data["bounds_lps_mm"] = [[-10,-10,-10],[10,10,10]]
    path.write_text(json.dumps(data))
    result = json.loads(run(root,tmp_path / "result").read_text())
    assert result["touches_roi_boundary"]
    assert result["status"] == "roi_boundary_warning"


def test_no_overwrite(lab):
    before = (lab / "result/envelope.obj").read_bytes()
    with pytest.raises(CaseError):
        run(lab,lab / "result")
    assert (lab / "result/envelope.obj").read_bytes() == before


def test_cli(lab,tmp_path):
    from atlas.radiology.__main__ import main
    assert main(["reconstruct",str(lab / "case/case.json"),"--annotation",
                 str(lab / "annotations.json"),"--geometry",str(lab / "geometry.json"),
                 "--settings",str(lab / "reconstruction-settings.json"),
                 "--output",str(tmp_path / "result")]) == 0


@pytest.mark.parametrize("change", ["resize", "orientation"])
def test_transformed_preview_is_rejected(lab, tmp_path, change):
    from PIL import Image
    from atlas.radiology.annotations import annotation_context
    from atlas.radiology.privacy import digest

    root = tmp_path / "lab"
    shutil.copytree(lab, root)
    manifest = root / "case/case.json"
    case = json.loads(manifest.read_text())
    view = next(v for v in case["views"] if v["view"] == "AP")
    source = manifest.parent / view["relative_path"]
    with Image.open(source) as image:
        image.load()
        copy = image.copy()
    if change == "resize":
        copy.resize((2048,2048)).save(source)
    else:
        exif = Image.Exif()
        exif[274] = 6
        copy.save(source, exif=exif)
    view["sha256"] = digest(source.read_bytes())
    manifest.write_text(json.dumps(case))
    previous = json.loads((root / "annotations.json").read_text())
    current, _ = annotation_context(manifest)
    for name in current["views"]:
        current["views"][name]["polygons"] = previous["views"][name]["polygons"]
    (root / "annotations.json").write_text(json.dumps(current))
    geometry = json.loads((root / "geometry.json").read_text())
    geometry["views"]["AP"]["image_size"] = current["views"]["AP"]["size"]
    (root / "geometry.json").write_text(json.dumps(geometry))
    with pytest.raises(CaseError) as exc:
        run(root,tmp_path / "output")
    assert exc.value.code == ("preview_mapping" if change == "resize" else "preview_orientation")
