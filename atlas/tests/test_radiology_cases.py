import hashlib
import json
import struct
import zlib
from pathlib import Path

import pytest

from atlas.radiology.__main__ import main
from atlas.radiology.cases import CaseError, validate_case
from atlas.radiology.demo import create_demo


@pytest.fixture
def case(tmp_path):
    return create_demo(tmp_path / "demo")


def edit_case(case, change):
    data = json.loads(case.read_text())
    change(data)
    case.write_text(json.dumps(data), encoding="utf-8")


def geometry():
    return {
        "calibration_id": "synthetic-rig",
        "coordinate_system": "LPS_mm",
        "projection_matrix": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 1]],
    }


def test_demo_is_explicitly_not_reconstruction(case):
    report = validate_case(case)
    assert report["status"] == "files_and_manifest_valid"
    assert report["views_checked"] == ["AP", "LATERAL", "OBLIQUE"]
    assert report["synthetic"] is True
    assert report["geometry_status"] == "missing"
    assert report["reconstruction_available"] is False
    assert report["clinical_use_validated"] is False
    assert report["pixel_decoding_performed"] is False
    assert report["anatomy_or_projection_verified"] is False


def test_png_fixtures_have_valid_chunks_and_pixels(case):
    for path in case.parent.glob("*.png"):
        data = path.read_bytes()
        offset = 8
        compressed = b""
        while offset < len(data):
            size = struct.unpack(">I", data[offset : offset + 4])[0]
            kind = data[offset + 4 : offset + 8]
            body = data[offset + 8 : offset + 8 + size]
            crc = struct.unpack(">I", data[offset + 8 + size : offset + 12 + size])[0]
            assert crc == zlib.crc32(kind + body)
            if kind == b"IDAT":
                compressed += body
            offset += 12 + size
        assert len(zlib.decompress(compressed)) == 64 * 65


def test_validation_is_read_only(case):
    before = {p.name: p.read_bytes() for p in case.parent.iterdir()}
    validate_case(case)
    assert before == {p.name: p.read_bytes() for p in case.parent.iterdir()}


def test_demo_never_overwrites_existing_directory(case):
    original = case.read_bytes()
    with pytest.raises(FileExistsError):
        create_demo(case.parent)
    assert case.read_bytes() == original


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("schema_version", 2, "version"),
        ("schema_version", True, "version"),
        ("case_id", "", "identifier"),
        ("region", "ankle", "region"),
        ("laterality", "unknown", "laterality"),
        ("data_origin", "clinical", "origin"),
        ("views", [], "views"),
        ("views", None, "views"),
    ],
)
def test_bad_case_metadata_is_rejected(case, field, value, code):
    edit_case(case, lambda data: data.__setitem__(field, value))
    with pytest.raises(CaseError) as error:
        validate_case(case)
    assert error.value.code == code


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("view", "AP", "views"),
        ("view", [], "views"),
        ("study_id", "another-study", "study_mismatch"),
        ("laterality", "R", "side_mismatch"),
        ("sha256", "a" * 64, "checksum"),
        ("sha256", "invalid", "checksum"),
    ],
)
def test_mixed_or_invalid_projection_is_rejected(case, field, value, code):
    edit_case(case, lambda data: data["views"][1].__setitem__(field, value))
    with pytest.raises(CaseError) as error:
        validate_case(case)
    assert error.value.code == code


@pytest.mark.parametrize(
    "path",
    [
        "../outside.png",
        "/outside.png",
        "C:/outside.png",
        "\\\\server\\a.png",
        "a/../ap.png",
        "a//b.png",
        "ap.png:stream",
        "ap.txt",
    ],
)
def test_paths_cannot_escape_case(case, path):
    edit_case(case, lambda data: data["views"][0].__setitem__("relative_path", path))
    with pytest.raises(CaseError) as error:
        validate_case(case)
    assert error.value.code in {"path", "format"}


def test_symlink_is_rejected(case, tmp_path):
    original = case.parent / "ap.png"
    target = tmp_path / "external.png"
    original.rename(target)
    try:
        original.symlink_to(target)
    except OSError:
        pytest.skip("OS does not permit symlinks for this account")
    with pytest.raises(CaseError, match="Links simbólicos"):
        validate_case(case)


def test_repeated_image_is_rejected(case):
    def change(data):
        first, second = data["views"][:2]
        second["sha256"] = first["sha256"]
        (case.parent / second["relative_path"]).write_bytes(
            (case.parent / first["relative_path"]).read_bytes()
        )

    edit_case(case, change)
    with pytest.raises(CaseError) as error:
        validate_case(case)
    assert error.value.code == "duplicate_image"


def test_removed_file_is_rejected(case):
    (case.parent / "ap.png").unlink()
    with pytest.raises(CaseError) as error:
        validate_case(case)
    assert error.value.code == "missing_image"


def test_modified_file_is_rejected(case):
    with (case.parent / "ap.png").open("ab") as stream:
        stream.write(b"altered")
    with pytest.raises(CaseError) as error:
        validate_case(case)
    assert error.value.code == "checksum"


def test_extension_alone_does_not_validate_format(case):
    raw = b"not an image"
    (case.parent / "ap.png").write_bytes(raw)
    edit_case(
        case,
        lambda data: data["views"][0].__setitem__(
            "sha256", hashlib.sha256(raw).hexdigest()
        ),
    )
    with pytest.raises(CaseError) as error:
        validate_case(case)
    assert error.value.code == "signature"


def test_research_origin_requires_privacy_review(case):
    edit_case(case, lambda data: data.__setitem__("data_origin", "research"))
    report = validate_case(case)
    assert report["privacy_review_required"] is True
    assert report["clinical_use_validated"] is False


def test_declared_geometry_does_not_claim_verified_calibration(case):
    edit_case(
        case,
        lambda data: [
            view.__setitem__("geometry", geometry()) for view in data["views"]
        ],
    )
    report = validate_case(case)
    assert report["geometry_status"] == "declared_not_verified"
    assert report["reconstruction_available"] is False


@pytest.mark.parametrize(
    "matrix",
    [
        [],
        [[1, 0, 0, 0]] * 3,
        [[True, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 1]],
        [[float("nan"), 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 1]],
    ],
)
def test_bad_geometry_is_rejected(case, matrix):
    def change(data):
        for view in data["views"]:
            view["geometry"] = geometry()
            view["geometry"]["projection_matrix"] = matrix

    edit_case(case, change)
    with pytest.raises(CaseError) as error:
        validate_case(case)
    assert error.value.code == "geometry"


def test_partial_geometry_is_rejected(case):
    edit_case(case, lambda data: data["views"][0].__setitem__("geometry", geometry()))
    with pytest.raises(CaseError) as error:
        validate_case(case)
    assert error.value.code == "partial_geometry"


def test_mixed_calibrations_are_rejected(case):
    def change(data):
        for view in data["views"]:
            view["geometry"] = geometry()
        data["views"][1]["geometry"]["calibration_id"] = "other-rig"

    edit_case(case, change)
    with pytest.raises(CaseError) as error:
        validate_case(case)
    assert error.value.code == "calibration_mismatch"


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "[]",
        '{"schema_version":1,"schema_version":1}',
        '{"patient_name":"not allowed"}',
        "x" * (256 * 1024 + 1),
    ],
    ids=["broken-json", "wrong-root", "duplicate-key", "unknown-field", "oversized"],
)
def test_invalid_manifest_is_rejected(case, raw):
    case.write_text(raw, encoding="utf-8")
    with pytest.raises(CaseError):
        validate_case(case)


def test_report_does_not_include_identifiers_or_paths(case):
    data = json.loads(case.read_text())
    report = json.dumps(validate_case(case))
    for value in (data["case_id"], data["study_id"], str(case), "ap.png"):
        assert value not in report


def test_cli_demo_validate_and_safe_errors(tmp_path, capsys):
    output = tmp_path / "cli-case"
    assert main(["demo", "--output", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["reconstruction_available"] is False
    assert main(["validate", str(output / "case.json")]) == 0
    capsys.readouterr()
    assert main(["demo", "--output", str(output)]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "output_unavailable"
    assert main(["validate", str(Path("private-case-missing.json"))]) == 1
    error = capsys.readouterr().out
    assert "private-case" not in error
    assert json.loads(error)["status"] == "rejected"
