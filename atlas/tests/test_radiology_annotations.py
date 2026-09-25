import json

import pytest
from PIL import Image

from atlas.radiology.annotations import (
    annotation_context, create_annotation_editor, export_annotation, validate_annotation,
)
from atlas.radiology.cases import CaseError
from atlas.radiology.lab import create_demo_2d


@pytest.fixture
def case(tmp_path):
    create_demo_2d(tmp_path / "lab")
    return tmp_path / "lab/case/case.json"


def sample(case, tmp_path):
    data, _ = annotation_context(case)
    data["views"]["AP"]["polygons"] = [
        {"bone": "tibia", "points": [[10, 10], [100, 10], [100, 100], [10, 100]]}]
    data["views"]["AP"]["landmarks"] = [
        {"bone": "tibia", "label": "P1", "point": [40, 40]}]
    path = tmp_path / "annotations.json"
    path.write_text(json.dumps(data))
    return path, data


def test_export_masks_preserves_original(case, tmp_path):
    before = {p.name: p.read_bytes() for p in case.parent.iterdir()}
    path, _ = sample(case, tmp_path)
    output = tmp_path / "export"
    export_annotation(case, path, output)
    with Image.open(output / "ap_tibia.png") as mask:
        assert mask.size == (256, 256)
        assert mask.getpixel((40, 40)) == 255
        assert mask.getpixel((0, 0)) == 0
        assert set(mask.tobytes()) == {0, 255}
    assert not (output / "lateral_tibia.png").exists()
    assert before == {p.name: p.read_bytes() for p in case.parent.iterdir()}
    report = json.loads((output / "annotation-report.json").read_text())
    assert not report["ready_for_metric_reconstruction"]


@pytest.mark.parametrize("fault", ["empty", "hash", "preview", "outside", "boolean",
                                  "cross", "repeated", "zero_area", "unknown_bone",
                                  "landmark_duplicate", "view_missing", "size"])
def test_rejected_annotations(case, tmp_path, fault):
    path, data = sample(case, tmp_path)
    ap = data["views"]["AP"]
    if fault == "empty":
        ap["polygons"] = []
    elif fault == "hash":
        data["manifest_sha256"] = "0" * 64
    elif fault == "preview":
        ap["preview_sha256"] = "0" * 64
    elif fault == "outside":
        ap["polygons"][0]["points"][0] = [-1, 0]
    elif fault == "boolean":
        ap["landmarks"][0]["point"] = [True, 20]
    elif fault == "cross":
        ap["polygons"][0]["points"] = [[10, 10], [100, 100], [10, 100], [100, 10]]
    elif fault == "repeated":
        ap["polygons"][0]["points"][1] = [10, 10]
    elif fault == "zero_area":
        ap["polygons"][0]["points"] = [[10, 10], [20, 20], [30, 30]]
    elif fault == "unknown_bone":
        ap["polygons"][0]["bone"] = "unknown"
    elif fault == "landmark_duplicate":
        ap["landmarks"] *= 2
    elif fault == "view_missing":
        del data["views"]["LATERAL"]
    else:
        ap["size"] = [512, 512]
    path.write_text(json.dumps(data))
    with pytest.raises(CaseError):
        export_annotation(case, path, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_source_change_invalidates(case, tmp_path):
    path, _ = sample(case, tmp_path)
    image = case.parent / "ap.png"
    image.write_bytes(image.read_bytes() + b"changed")
    with pytest.raises(CaseError):
        validate_annotation(case, path)


def test_editor_binding_and_no_overwrite(case, tmp_path):
    output = tmp_path / "editor"
    page = create_annotation_editor(case, output).read_text(encoding="utf-8")
    assert "__ANNOTATION_DATA__" not in page
    assert "data:image/png;base64," in page
    assert "connect-src 'none'" in page
    with pytest.raises(CaseError):
        create_annotation_editor(case, output)


def test_multiple_contours_and_overlap(case, tmp_path):
    path, data = sample(case, tmp_path)
    data["views"]["AP"]["polygons"].extend([
        {"bone": "tibia", "points": [[150, 150], [180, 150], [150, 180]]},
        {"bone": "fibula", "points": [[30, 30], [60, 30], [30, 60]]}])
    path.write_text(json.dumps(data))
    export_annotation(case, path, tmp_path / "export")
    with Image.open(tmp_path / "export/ap_tibia.png") as mask:
        assert mask.getpixel((155, 155)) == 255
    with Image.open(tmp_path / "export/ap_fibula.png") as mask:
        assert mask.getpixel((35, 35)) == 255


def test_cli(case, tmp_path):
    from atlas.radiology.__main__ import main

    path, _ = sample(case, tmp_path)
    assert main(["annotation-editor", str(case), "--output", str(tmp_path / "editor")]) == 0
    assert main(["annotation-export", str(case), "--annotation", str(path),
                 "--output", str(tmp_path / "export")]) == 0
    assert main(["annotation-export", str(case), "--annotation", str(path),
                 "--output", str(tmp_path / "export")]) == 1
