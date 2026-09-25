"""A local three-format demonstration with synthetic pixel patterns only."""

import io
import shutil
from pathlib import Path

import numpy as np
from PIL import Image
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import (
    DigitalXRayImageStorageForPresentation,
    ExplicitVRLittleEndian,
    generate_uid,
)

from atlas.radiology.workspace import build_viewer, import_case


def create_demo_2d(output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=False)
    try:
        sources = output / "sources"
        sources.mkdir()
        y, x = np.mgrid[:256, :256]
        gray = ((x + y) // 2).astype(np.uint8)
        Image.fromarray(gray).save(sources / "ap.png")
        Image.fromarray(np.flipud(gray)).save(sources / "lateral.jpg", quality=95)
        values = ((x * 8 + y * 4) % 4096).astype(np.uint16)
        meta = FileMetaDataset()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        meta.MediaStorageSOPClassUID = DigitalXRayImageStorageForPresentation
        meta.MediaStorageSOPInstanceUID = generate_uid()
        ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
        ds.SOPClassUID, ds.SOPInstanceUID = (
            meta.MediaStorageSOPClassUID,
            meta.MediaStorageSOPInstanceUID,
        )
        ds.StudyInstanceUID, ds.SeriesInstanceUID = generate_uid(), generate_uid()
        ds.PatientName, ds.PatientID = "SYNTHETIC^DEMO", "SYNTHETIC-LAB"
        ds.Modality, ds.ImageLaterality = "DX", "L"
        ds.Rows, ds.Columns = values.shape
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = (
            16,
            12,
            11,
            0,
        )
        ds.WindowCenter, ds.WindowWidth = 2048, 4096
        ds.PixelData = values.tobytes()
        buffer = io.BytesIO()
        ds.save_as(buffer, enforce_file_format=True)
        (sources / "oblique.dcm").write_bytes(buffer.getvalue())
        manifest = import_case(
            {
                "AP": sources / "ap.png",
                "LATERAL": sources / "lateral.jpg",
                "OBLIQUE": sources / "oblique.dcm",
            },
            output / "case",
            "L",
            "synthetic",
        )
        return build_viewer(manifest, output / "viewer")
    except Exception:
        shutil.rmtree(output)
        raise
