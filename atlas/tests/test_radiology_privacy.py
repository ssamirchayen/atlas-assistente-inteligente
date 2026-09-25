import io
import json

import pytest
from PIL import Image

from atlas.radiology.cases import CaseError
from atlas.radiology.lab import create_demo_2d
from atlas.radiology.privacy import (
    VIEWS, export_reviewed, prepare_privacy, record_review,
)


@pytest.fixture
def source(tmp_path):
    create_demo_2d(tmp_path / "source")
    return tmp_path / "source" / "case" / "case.json"


@pytest.fixture
def bundle(source, tmp_path):
    folder = tmp_path / "privacy"
    prepare_privacy(source, folder)
    return folder


def test_clean_preserves_source_and_removes_metadata(source, tmp_path):
    before = {p.name: p.read_bytes() for p in source.parent.iterdir()}
    output = tmp_path / "clean"
    prepare_privacy(source, output, {"AP": [[0, 0, 10, 10]]})
    assert before == {p.name: p.read_bytes() for p in source.parent.iterdir()}
    for name in VIEWS:
        raw = (output / (name.lower() + ".png")).read_bytes()
        assert b"SYNTHETIC" not in raw
        with Image.open(io.BytesIO(raw)) as im:
            assert im.info == {}
            if name == "AP":
                assert im.crop((0, 0, 10, 10)).getextrema() == (0, 0)
    assert json.loads((output / "privacy.json").read_text())["status"] == "pending_pixel_review"


@pytest.mark.parametrize("masks", [[], {"bad": []}, {"AP": "bad"},
                                     {"AP": [[False, 0, 3, 3]]},
                                     {"AP": [[0, 0, 99999, 2]]},
                                     {"AP": [[3, 0, 2, 3]]}])
def test_invalid_masks(source, tmp_path, masks):
    with pytest.raises(CaseError):
        prepare_privacy(source, tmp_path / "bad", masks)
    assert not (tmp_path / "bad").exists()


def test_missing_review_blocks_export(bundle, tmp_path):
    review = tmp_path / "pending.json"
    review.write_text("{}")
    with pytest.raises(CaseError, match="Exportação bloqueada"):
        export_reviewed(bundle, review, tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_rejection_blocks_export(bundle, tmp_path):
    decisions = dict.fromkeys(VIEWS, "clear")
    decisions["LATERAL"] = "reject"
    record_review(bundle, decisions, "OP01", tmp_path / "review.json")
    with pytest.raises(CaseError):
        export_reviewed(bundle, tmp_path / "review.json", tmp_path / "export")


def test_export_allowlist(bundle, tmp_path):
    review = tmp_path / "review.json"
    record_review(bundle, dict.fromkeys(VIEWS, "clear"), "OP01", review)
    (bundle / "secret.txt").write_text("patient")
    output = tmp_path / "export"
    export_reviewed(bundle, review, output)
    assert {p.name for p in output.iterdir()} == {
        "ap.png", "lateral.png", "oblique.png", "export.json"}
    report = (output / "export.json").read_text()
    assert "OP01" not in report and "source_sha256" not in report
    with pytest.raises(CaseError):
        export_reviewed(bundle, review, output)
    with pytest.raises(FileExistsError):
        record_review(bundle, dict.fromkeys(VIEWS, "clear"), "OP01", review)


@pytest.mark.parametrize("changed", ["ap.png", "privacy.json", "provenance-private.json"])
def test_changed_content_invalidates_review(bundle, tmp_path, changed):
    review = tmp_path / "review.json"
    record_review(bundle, dict.fromkeys(VIEWS, "clear"), "OP01", review)
    path = bundle / changed
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(CaseError):
        export_reviewed(bundle, review, tmp_path / "export")


def test_different_bundle_review_rejected(bundle, source, tmp_path):
    review = tmp_path / "review.json"
    record_review(bundle, dict.fromkeys(VIEWS, "clear"), "OP01", review)
    other = tmp_path / "other"
    prepare_privacy(source, other)
    with pytest.raises(CaseError):
        export_reviewed(other, review, tmp_path / "export")


def test_missing_view_rejected(bundle, tmp_path):
    with pytest.raises(CaseError):
        record_review(bundle, {"AP": "clear"}, "OP01", tmp_path / "review.json")


def test_cli_pipeline(source, tmp_path, capsys):
    from atlas.radiology.__main__ import main

    folder, review, output = [tmp_path / x for x in ("clean", "review.json", "export")]
    assert main(["privacy-prepare", str(source), "--output", str(folder)]) == 0
    assert main(["privacy-review", str(folder), "--reviewer", "OP01", "--ap",
                 "clear", "--lateral", "clear", "--oblique", "clear", "--output",
                 str(review)]) == 0
    assert main(["privacy-export", str(folder), "--review", str(review),
                 "--output", str(output)]) == 0
    assert "human_reviewed_display_derivatives" in capsys.readouterr().out
