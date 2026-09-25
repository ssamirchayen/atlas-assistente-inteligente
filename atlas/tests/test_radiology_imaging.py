import io
import json

import numpy as np
import pydicom
import pytest
from PIL import Image
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, DigitalXRayImageStorageForPresentation

from atlas.radiology.__main__ import main
from atlas.radiology.cases import CaseError, validate_case
from atlas.radiology.demo import create_demo
from atlas.radiology.imaging import decode_image
from atlas.radiology.workspace import build_viewer, import_case
from atlas.radiology.lab import create_demo_2d


def dicom_bytes(pixels=None, **changes):
    pixels = (
        np.array([[0, 100], [200, 300]], dtype=np.uint16) if pixels is None else pixels
    )
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = DigitalXRayImageStorageForPresentation
    meta.MediaStorageSOPInstanceUID = "1.2.826.0.1.3680043.8.498.1234"
    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.PatientName = "PRIVATE-NAME"
    ds.PatientID = "PRIVATE-ID"
    ds.StudyInstanceUID = "1.2.826.0.1.3680043.8.498.4321"
    ds.ImageLaterality = "L"
    ds.Modality = "DX"
    ds.Rows, ds.Columns = pixels.shape
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = pixels.dtype.itemsize * 8
    ds.BitsStored = ds.BitsAllocated
    ds.HighBit = ds.BitsStored - 1
    ds.PixelRepresentation = int(pixels.dtype.kind == "i")
    ds.PixelData = pixels.tobytes()
    for key, value in changes.items():
        setattr(ds, key, value)
    out = io.BytesIO()
    ds.save_as(out, enforce_file_format=True)
    return out.getvalue()


def preview_array(decoded):
    return np.asarray(Image.open(io.BytesIO(decoded.preview_png)))


def raster_bytes(kind="PNG", pixels=None):
    pixels = np.arange(16, dtype=np.uint8).reshape(4, 4) if pixels is None else pixels
    out = io.BytesIO()
    Image.fromarray(pixels).save(out, format=kind)
    return out.getvalue()


@pytest.mark.parametrize("kind,suffix", [("PNG", ".png"), ("JPEG", ".jpg")])
def test_raster_decoding(kind, suffix):
    result = decode_image(raster_bytes(kind), suffix)
    assert result.metadata["width"] == 4
    assert result.metadata["format"] == kind
    assert result.metadata["pixel_decoding_performed"] is True
    assert result.metadata["reconstruction_available"] is False
    assert preview_array(result).shape == (4, 4)


def test_16bit_png_is_not_truncated_to_8bit():
    result = decode_image(
        raster_bytes(pixels=np.array([[0, 1024], [2048, 4095]], dtype=np.uint16)),
        ".png",
    )
    values = preview_array(result)
    assert values[0, 0] == 0 and values[1, 1] == 255
    assert 60 <= values[0, 1] <= 70 and 120 <= values[1, 0] <= 135


def test_dicom_monochrome1_is_inverted():
    normal = preview_array(decode_image(dicom_bytes(), ".dcm"))
    inverted = preview_array(
        decode_image(dicom_bytes(PhotometricInterpretation="MONOCHROME1"), ".dcm")
    )
    np.testing.assert_array_equal(inverted, 255 - normal)


def test_signed_rescale_then_window():
    raw = np.array([[-100, 0], [50, 100]], dtype=np.int16)
    result = decode_image(
        dicom_bytes(
            raw, RescaleSlope=2, RescaleIntercept=100, WindowCenter=100, WindowWidth=201
        ),
        ".dcm",
    )
    np.testing.assert_allclose(preview_array(result), [[0, 128], [255, 255]], atol=1)
    assert result.metadata["signed"] is True
    assert result.metadata["display_transform"] == "dicom_window"


def test_width_one_threshold():
    raw = np.array([[0, 1], [2, 3]], dtype=np.uint16)
    result = decode_image(dicom_bytes(raw, WindowCenter=2, WindowWidth=1), ".dcm")
    np.testing.assert_array_equal(preview_array(result), [[0, 0], [255, 255]])


def test_voi_lut_and_native_8bit():
    lut = Dataset()
    lut.LUTDescriptor = [4, 0, 8]
    lut.add_new(0x00283006, "US", [0, 64, 128, 255])
    raw = np.array([[0, 1], [2, 3]], dtype=np.uint8)
    result = decode_image(dicom_bytes(raw, VOILUTSequence=[lut]), ".dcm")
    np.testing.assert_array_equal(preview_array(result), [[0, 64], [128, 255]])


def test_linear_exact_window():
    raw = np.array([[0, 50], [100, 150]], dtype=np.uint16)
    result = decode_image(
        dicom_bytes(
            raw, WindowCenter=100, WindowWidth=100, VOILUTFunction="LINEAR_EXACT"
        ),
        ".dcm",
    )
    np.testing.assert_allclose(preview_array(result), [[0, 0], [128, 255]], atol=1)


def test_exif_orientation_and_metadata_removal():
    image = Image.new("RGB", (3, 5), "red")
    exif = image.getexif()
    exif[274] = 6
    exif[315] = "PRIVATE-ARTIST"
    output = io.BytesIO()
    image.save(output, format="JPEG", exif=exif)
    result = decode_image(output.getvalue(), ".jpg")
    assert (result.metadata["width"], result.metadata["height"]) == (5, 3)
    assert b"PRIVATE" not in result.preview_png
    assert not Image.open(io.BytesIO(result.preview_png)).getexif()


def test_partial_rescale_rejected():
    with pytest.raises(CaseError) as error:
        decode_image(dicom_bytes(RescaleSlope=2), ".dcm")
    assert error.value.code == "dicom_values"


def test_padding_does_not_distort_auto_contrast():
    raw = np.array([[0, 100], [150, 200]], dtype=np.uint16)
    result = decode_image(dicom_bytes(raw, PixelPaddingValue=0), ".dcm")
    np.testing.assert_allclose(preview_array(result), [[0, 0], [128, 255]], atol=1)


def test_no_identifying_metadata_in_report_or_preview():
    result = decode_image(dicom_bytes(PixelSpacing=[0.2, 0.3]), ".dcm")
    text = json.dumps(result.metadata)
    assert "PRIVATE" not in text and "4321" not in text
    assert b"PRIVATE" not in result.preview_png
    assert result.metadata["pixel_spacing_mm"] == [0.2, 0.3]
    assert result.metadata["deidentification_performed"] is False
    assert result.metadata["spacing_is_full_calibration"] is False


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"NumberOfFrames": 2}, "dicom_frames"),
        ({"Modality": "CT"}, "dicom_modality"),
        ({"PhotometricInterpretation": "RGB"}, "dicom_color"),
        ({"WindowCenter": 1, "WindowWidth": 0}, "window"),
        ({"WindowCenter": 1, "WindowWidth": 2, "VOILUTFunction": "SIGMOID"}, "window"),
        ({"Rows": 65535, "Columns": 65535}, "pixel_limit"),
        ({"PixelData": b"\0\0"}, "dicom_pixels"),
    ],
)
def test_unsupported_dicom_rejected(changes, code):
    with pytest.raises(CaseError) as error:
        decode_image(dicom_bytes(**changes), ".dcm")
    assert error.value.code == code


def test_deflated_rejected_before_dcmread(monkeypatch):
    dataset = pydicom.dcmread(io.BytesIO(dicom_bytes()))
    dataset.file_meta.TransferSyntaxUID = "1.2.840.10008.1.2.1.99"
    encoded = io.BytesIO()
    dataset.save_as(encoded, enforce_file_format=True)
    source = encoded.getvalue()

    def forbidden(*args, **kwargs):
        pytest.fail("dcmread must not see compressed input")

    monkeypatch.setattr(pydicom, "dcmread", forbidden)
    with pytest.raises(CaseError):
        decode_image(source, ".dcm")


@pytest.mark.parametrize("suffix", [".png", ".jpg", ".dcm"])
def test_corrupt_files_return_safe_error(suffix):
    with pytest.raises(CaseError) as error:
        decode_image(b"PRIVATE-NAME-invalid-file", suffix)
    assert "PRIVATE" not in str(error.value)


def test_preview_is_bounded():
    pixels = np.zeros((10, 2000), dtype=np.uint8)
    result = decode_image(raster_bytes(pixels=pixels), ".png")
    assert result.metadata["width"] == 2000
    assert result.metadata["preview_width"] == 1600


def test_import_mixed_formats_and_offline_viewer(tmp_path):
    sources = {}
    for name, suffix, raw in [
        ("AP", ".png", raster_bytes()),
        ("LATERAL", ".jpg", raster_bytes("JPEG")),
        ("OBLIQUE", ".dcm", dicom_bytes()),
    ]:
        path = tmp_path / (name + suffix)
        path.write_bytes(raw)
        sources[name] = path
    originals = {name: path.read_bytes() for name, path in sources.items()}
    manifest = import_case(sources, tmp_path / "case", "L", "synthetic")
    assert validate_case(manifest)["geometry_status"] == "missing"
    page = build_viewer(manifest, tmp_path / "viewer")
    html = page.read_text(encoding="utf-8")
    assert "PRIVATE" not in html and "__TECHNICAL_DATA__" not in html
    assert "connect-src 'none'" in html
    assert all(
        (page.parent / (v + ".png")).is_file() for v in ("ap", "lateral", "oblique")
    )
    assert {name: path.read_bytes() for name, path in sources.items()} == originals
    with pytest.raises(CaseError, match="pasta"):
        build_viewer(manifest, page.parent)


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("PatientID", "different", "study_mismatch"),
        ("StudyInstanceUID", "1.2.3.4", "study_mismatch"),
        ("ImageLaterality", "R", "side_mismatch"),
    ],
)
def test_import_rejects_dicom_identity_conflicts(tmp_path, field, value, code):
    sources = {}
    for index, view in enumerate(("AP", "LATERAL", "OBLIQUE")):
        path = tmp_path / (view + ".dcm")
        path.write_bytes(dicom_bytes(**({field: value} if index == 1 else {})))
        sources[view] = path
    with pytest.raises(CaseError) as error:
        import_case(sources, tmp_path / "case", "L", "research")
    assert error.value.code == code
    assert not (tmp_path / "case").exists()


def test_viewer_refuses_altered_source(tmp_path):
    manifest = create_demo(tmp_path / "demo")
    (manifest.parent / "ap.png").write_bytes(b"changed")
    with pytest.raises(CaseError):
        build_viewer(manifest, tmp_path / "viewer")
    assert not (tmp_path / "viewer").exists()


def test_cli_inspect_and_viewer(tmp_path, capsys):
    manifest = create_demo(tmp_path / "demo")
    assert main(["inspect", str(manifest.parent / "ap.png")]) == 0
    assert json.loads(capsys.readouterr().out)["pixel_decoding_performed"] is True
    assert main(["viewer", str(manifest), "--output", str(tmp_path / "viewer")]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "viewer_created"


def test_three_format_lab(tmp_path):
    page = create_demo_2d(tmp_path / "lab")
    assert page.is_file()
    assert "padrões sintéticos" in page.read_text(encoding="utf-8")
    report = json.loads((page.parent / "pixel-report.json").read_text())
    assert {item["format"] for item in report.values()} == {"PNG", "JPEG", "DICOM"}
    with pytest.raises(FileExistsError):
        create_demo_2d(tmp_path / "lab")


def test_import_failure_cleans_only_new_output(tmp_path):
    manifest = create_demo(tmp_path / "sources")
    source = manifest.parent / "ap.png"
    original = source.read_bytes()
    with pytest.raises(CaseError):
        import_case(
            dict.fromkeys(("AP", "LATERAL", "OBLIQUE"), source),
            tmp_path / "case",
            "L",
            "synthetic",
        )
    assert not (tmp_path / "case").exists()
    assert source.read_bytes() == original
