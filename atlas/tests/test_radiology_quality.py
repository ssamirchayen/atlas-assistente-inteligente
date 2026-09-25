import io
import json

import pytest
from PIL import Image

from atlas.radiology.cases import CaseError
from atlas.radiology.lab import create_demo_2d
from atlas.radiology.quality import (
    analyze_quality, review_quality, screen_pixels, write_review_template,
)


@pytest.fixture
def case(tmp_path):
    create_demo_2d(tmp_path / "lab")
    return tmp_path / "lab/case/case.json"


def filled_review(case, tmp_path):
    report = analyze_quality(case)
    path = tmp_path / "review.json"
    write_review_template(report, path)
    review = json.loads(path.read_text())
    for name, entry in review["views"].items():
        entry.update(observed_projection=name, observed_laterality="L",
                     anatomy_coverage="acceptable", positioning="acceptable",
                     image_quality="acceptable", flags_reviewed=True)
    path.write_text(json.dumps(review))
    return path, review


def test_constant_detection():
    data = io.BytesIO()
    Image.new("L", (64, 64), 42).save(data, "PNG")
    report = screen_pixels(data.getvalue())
    assert set(report["flags"]) == {
        "constant_display_image", "small_display_image", "narrow_display_range"}
    assert report["display_std"] == 0


def test_report_and_pending_template(case, tmp_path):
    report = analyze_quality(case)
    assert report["status"] == "human_review_required"
    assert report["views"]["OBLIQUE"]["dicom_laterality"] == "L"
    assert "Patient" not in json.dumps(report)
    template = tmp_path / "template.json"
    write_review_template(report, template)
    result = review_quality(case, template, tmp_path / "result.json")
    assert result["status"] == "blocked"
    assert not result["eligible_for_geometry_stage"]


def test_synthetic_never_eligible(case, tmp_path):
    path, _ = filled_review(case, tmp_path)
    result = review_quality(case, path, tmp_path / "result.json")
    assert result["status"] == "human_review_recorded"
    assert not result["eligible_for_geometry_stage"]
    assert not result["clinical_use_validated"]


@pytest.mark.parametrize("field,value", [
    ("observed_projection", "LATERAL"), ("observed_laterality", "R"),
    ("anatomy_coverage", "unknown"), ("positioning", "reject"),
    ("image_quality", "reject"), ("flags_reviewed", False),
])
def test_each_review_gate(case, tmp_path, field, value):
    path, review = filled_review(case, tmp_path)
    review["views"]["AP"][field] = value
    path.write_text(json.dumps(review))
    result = review_quality(case, path, tmp_path / "result.json")
    assert result["status"] == "blocked"


@pytest.mark.parametrize("mutation", ["hash", "missing", "type", "manifest"])
def test_invalid_review(case, tmp_path, mutation):
    path, review = filled_review(case, tmp_path)
    if mutation == "hash":
        review["views"]["AP"]["source_sha256"] = "0" * 64
    elif mutation == "missing":
        del review["views"]["LATERAL"]
    elif mutation == "type":
        review["views"]["AP"]["observed_projection"] = []
    else:
        review["manifest_sha256"] = "0" * 64
    path.write_text(json.dumps(review))
    with pytest.raises(CaseError):
        review_quality(case, path, tmp_path / "result.json")
    assert not (tmp_path / "result.json").exists()


def test_source_change_rejected(case, tmp_path):
    path, _ = filled_review(case, tmp_path)
    image = case.parent / "ap.png"
    image.write_bytes(image.read_bytes() + b"changed")
    with pytest.raises(CaseError):
        review_quality(case, path, tmp_path / "result.json")


def test_no_overwrite(case, tmp_path):
    path, _ = filled_review(case, tmp_path)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        review_quality(case, path, path)
    assert path.read_bytes() == before


def test_cli_blocked_returns_two(case, tmp_path):
    from atlas.radiology.__main__ import main

    report, template, output = [tmp_path / n for n in ("report.json", "template.json", "result.json")]
    assert main(["quality", str(case), "--output", str(report),
                 "--template", str(template)]) == 0
    assert main(["quality-review", str(case), "--review", str(template),
                 "--output", str(output)]) == 2


@pytest.mark.parametrize("fault", ["constant", "laterality"])
def test_hard_blocks_cannot_be_overridden(case, tmp_path, fault):
    import hashlib
    import pydicom

    data = json.loads(case.read_text())
    name = "AP" if fault == "constant" else "OBLIQUE"
    entry = next(v for v in data["views"] if v["view"] == name)
    path = case.parent / entry["relative_path"]
    if fault == "constant":
        Image.new("L", (256, 256), 42).save(path)
    else:
        ds = pydicom.dcmread(path)
        ds.ImageLaterality = "R"
        ds.save_as(path, enforce_file_format=True)
    entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    case.write_text(json.dumps(data))
    review, _ = filled_review(case, tmp_path)
    result = review_quality(case, review, tmp_path / "result.json")
    assert result["status"] == "blocked"
    assert any(("constant_display_image" if fault == "constant" else
                "dicom_laterality_conflict") in r for r in result["blocking_reasons"])


def test_research_gate_is_only_human_attestation(case, tmp_path):
    # Exercise the declared-origin branch; these are still synthetic test pixels.
    data = json.loads(case.read_text())
    data["data_origin"] = "research"
    case.write_text(json.dumps(data))
    review, _ = filled_review(case, tmp_path)
    result = review_quality(case, review, tmp_path / "result.json")
    assert result["eligible_for_geometry_stage"]
    assert not result["anatomy_or_projection_verified"]
    assert not result["reconstruction_available"]
