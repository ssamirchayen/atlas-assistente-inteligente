"""Bounded pixel decoding and derived previews for an experimental 2D viewer."""

from __future__ import annotations

import io
import struct
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pydicom
from pydicom.errors import InvalidDicomError
from PIL import Image, ImageOps
from pydicom.pixels import apply_modality_lut, apply_voi_lut

from atlas.radiology.cases import CaseError, MAX_IMAGE_BYTES, require

MAX_PIXELS = 16_000_000
PREVIEW_EDGE = 1600
NATIVE_SYNTAXES = {"1.2.840.10008.1.2", "1.2.840.10008.1.2.1", "1.2.840.10008.1.2.2"}


@dataclass
class DecodedImage:
    preview_png: bytes
    metadata: dict
    identity: dict = field(default_factory=dict, repr=False)


def read_image_bytes(path: Path) -> bytes:
    try:
        require(
            path.is_file(), "image_file", "Selecione um arquivo de imagem existente."
        )
        with path.open("rb") as stream:
            data = stream.read(MAX_IMAGE_BYTES + 1)
        require(
            0 < len(data) <= MAX_IMAGE_BYTES,
            "image_size",
            "Imagem vazia ou maior que 50 MiB.",
        )
        return data
    except OSError as exc:
        raise CaseError("image_read", "Não foi possível ler a imagem.") from exc


def dimensions(width, height):
    require(
        0 < width and 0 < height and width * height <= MAX_PIXELS,
        "pixel_limit",
        "Dimensões inválidas ou acima de 16 milhões de pixels.",
    )


def preview(image: Image.Image, metadata: dict) -> DecodedImage:
    image.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE), Image.Resampling.LANCZOS)
    # Build a fresh image: do not propagate EXIF, DICOM tags or PNG text chunks.
    clean = Image.fromarray(np.asarray(image).copy())
    output = io.BytesIO()
    clean.save(output, format="PNG")
    return DecodedImage(
        output.getvalue(),
        {
            **metadata,
            "preview_width": clean.width,
            "preview_height": clean.height,
            "preview_precision_bits": 8,
            "pixel_decoding_performed": True,
            "anatomy_or_projection_verified": False,
            "deidentification_performed": False,
            "reconstruction_available": False,
        },
    )


def normalize(values, mask=None):
    selected = values if mask is None else values[mask]
    if selected.size == 0:
        return np.zeros(values.shape, dtype=np.float64)
    lo, hi = float(selected.min()), float(selected.max())
    if hi == lo:
        return np.zeros(values.shape, dtype=np.float64)
    return np.clip((values - lo) / (hi - lo), 0, 1)


def first_number(value):
    if not isinstance(value, (str, bytes)) and hasattr(value, "__len__"):
        value = value[0]
    number = float(value)
    require(np.isfinite(number), "window", "Janela DICOM inválida.")
    return number


def check_transfer_syntax(data: bytes):
    # Read only explicit little-endian File Meta Information before dcmread.
    # This rejects deflated datasets before pydicom can inflate their contents.
    require(
        data[128:132] == b"DICM",
        "dicom_header",
        "Use um arquivo DICOM Part 10 com preâmbulo.",
    )
    offset, syntax = 132, None
    while offset + 8 <= len(data):
        group, element = struct.unpack_from("<HH", data, offset)
        if group != 2:
            break
        vr = data[offset + 4 : offset + 6]
        if vr in {
            b"OB",
            b"OD",
            b"OF",
            b"OL",
            b"OV",
            b"OW",
            b"SQ",
            b"UC",
            b"UR",
            b"UT",
            b"UN",
        }:
            require(
                offset + 12 <= len(data), "dicom_header", "Metadados DICOM truncados."
            )
            length, start = struct.unpack_from("<I", data, offset + 8)[0], offset + 12
        else:
            length, start = struct.unpack_from("<H", data, offset + 6)[0], offset + 8
        end = start + length
        require(
            end <= len(data) and end <= 1024 * 1024,
            "dicom_header",
            "Metadados DICOM inválidos ou excessivos.",
        )
        if element == 0x0010:
            require(
                vr == b"UI" and syntax is None,
                "dicom_header",
                "Transfer Syntax inválida ou repetida.",
            )
            syntax = data[start:end].rstrip(b"\0 ").decode("ascii")
        offset = end
    require(
        syntax in NATIVE_SYNTAXES,
        "dicom_encoding",
        "DICOM comprimido ou sem sintaxe suportada. Use DICOM nativo sem compressão.",
    )


def dicom_preview(data: bytes) -> DecodedImage:
    check_transfer_syntax(data)
    ds = pydicom.dcmread(io.BytesIO(data), force=False)
    require(
        str(ds.file_meta.get("TransferSyntaxUID", "")) in NATIVE_SYNTAXES,
        "dicom_encoding",
        "DICOM comprimido ou sem sintaxe suportada. Nesta etapa use DICOM nativo sem compressão.",
    )
    require(
        str(ds.get("Modality", "")) in {"CR", "DX"},
        "dicom_modality",
        "Esta etapa aceita radiografias DICOM CR ou DX.",
    )
    rows, cols = int(ds.Rows), int(ds.Columns)
    dimensions(cols, rows)
    require(
        int(ds.get("NumberOfFrames", 1)) == 1,
        "dicom_frames",
        "DICOM multiframe ainda não é suportado.",
    )
    require(
        int(ds.SamplesPerPixel) == 1
        and str(ds.PhotometricInterpretation) in {"MONOCHROME1", "MONOCHROME2"},
        "dicom_color",
        "Esta etapa aceita DICOM monocromático.",
    )
    bits, stored = int(ds.BitsAllocated), int(ds.BitsStored)
    require(
        bits in {8, 16}
        and 1 <= stored <= bits
        and int(ds.HighBit) == stored - 1
        and int(ds.PixelRepresentation) in {0, 1},
        "dicom_bits",
        "Representação dos pixels DICOM não suportada.",
    )
    require(
        "PresentationLUTSequence" not in ds
        and ds.get("PresentationLUTShape", "IDENTITY") == "IDENTITY",
        "presentation_lut",
        "Presentation LUT adicional não é suportada nesta etapa.",
    )
    require("PixelData" in ds, "dicom_pixels", "Pixel Data ausente.")
    expected = rows * cols * (bits // 8)
    require(
        len(ds.PixelData) in {expected, expected + expected % 2},
        "dicom_pixels",
        "Tamanho do Pixel Data inconsistente.",
    )
    raw = ds.pixel_array
    require(raw.shape == (rows, cols), "dicom_pixels", "Matriz de pixels inesperada.")
    if "RescaleSlope" in ds or "RescaleIntercept" in ds:
        require(
            "RescaleSlope" in ds and "RescaleIntercept" in ds,
            "dicom_values",
            "RescaleSlope e RescaleIntercept devem estar presentes juntos.",
        )
        require(
            np.isfinite(float(ds.RescaleSlope))
            and float(ds.RescaleSlope) != 0
            and np.isfinite(float(ds.RescaleIntercept)),
            "dicom_values",
            "Transformação de intensidade inválida.",
        )
    values = np.asarray(apply_modality_lut(raw, ds), dtype=np.float64)
    require(
        np.isfinite(values).all(),
        "dicom_values",
        "Transformação de intensidade inválida.",
    )
    valid = np.ones(raw.shape, dtype=bool)
    if "PixelPaddingValue" in ds:
        a = float(ds.PixelPaddingValue)
        b = float(ds.get("PixelPaddingRangeLimit", a))
        valid = (raw < min(a, b)) | (raw > max(a, b))
    if "VOILUTSequence" in ds:
        lut_bits = int(ds.VOILUTSequence[0].LUTDescriptor[2])
        require(8 <= lut_bits <= 16, "window", "VOI LUT não suportada.")
        shown = np.asarray(apply_voi_lut(values, ds, prefer_lut=True), dtype=np.float64)
        require(np.isfinite(shown).all(), "window", "VOI LUT inválida.")
        shown = np.clip(shown / (2**lut_bits - 1), 0, 1)
        display = "dicom_voi_lut"
    elif "WindowCenter" in ds or "WindowWidth" in ds:
        require(
            "WindowCenter" in ds and "WindowWidth" in ds,
            "window",
            "Centro e largura de janela devem estar presentes.",
        )
        center, width = first_number(ds.WindowCenter), first_number(ds.WindowWidth)
        function = str(ds.get("VOILUTFunction", "LINEAR"))
        require(
            function in {"LINEAR", "LINEAR_EXACT"},
            "window",
            "Função VOI não suportada nesta etapa.",
        )
        require(
            width >= 1 if function == "LINEAR" else width > 0,
            "window",
            "Largura de janela inválida.",
        )
        if function == "LINEAR":
            shown = (
                (values > center - 0.5).astype(float)
                if width == 1
                else np.clip((values - (center - 0.5)) / (width - 1) + 0.5, 0, 1)
            )
        else:
            shown = np.clip((values - center) / width + 0.5, 0, 1)
        display = "dicom_window"
    else:
        shown = normalize(values, valid)
        display = "auto_minmax_non_padding"
    if ds.PhotometricInterpretation == "MONOCHROME1":
        shown = 1 - shown
    shown[~valid] = 0
    image = Image.fromarray(np.rint(shown * 255).astype(np.uint8))
    # Whitelist technical metadata: no patient/study identifiers or free text.
    spacing = None
    if "PixelSpacing" in ds:
        candidates = [float(v) for v in ds.PixelSpacing]
        if len(candidates) == 2 and all(np.isfinite(v) and v > 0 for v in candidates):
            spacing = candidates
    result = preview(
        image,
        {
            "format": "DICOM",
            "width": cols,
            "height": rows,
            "stored_bits": stored,
            "signed": bool(ds.PixelRepresentation),
            "photometric": str(ds.PhotometricInterpretation),
            "display_transform": display,
            "pixel_spacing_mm": spacing,
            "spacing_is_full_calibration": False,
        },
    )
    result.identity = {
        key: str(ds.get(key, ""))
        for key in ("PatientID", "StudyInstanceUID", "ImageLaterality")
    }
    return result


def raster_preview(data: bytes, suffix: str) -> DecodedImage:
    expected = "PNG" if suffix == ".png" else "JPEG"
    with Image.open(io.BytesIO(data), formats=[expected]) as source:
        dimensions(*source.size)
        require(
            getattr(source, "n_frames", 1) == 1,
            "image_frames",
            "Imagem animada ou multiframe não suportada.",
        )
        source.verify()
    with Image.open(io.BytesIO(data), formats=[expected]) as source:
        source.load()
        oriented = ImageOps.exif_transpose(source)
        if oriented.mode in {"I", "I;16", "I;16L", "I;16B", "F"}:
            values = np.asarray(oriented, dtype=np.float64)
            require(np.isfinite(values).all(), "pixel_values", "Pixels não finitos.")
            image = Image.fromarray(np.rint(normalize(values) * 255).astype(np.uint8))
            transform = "auto_minmax"
        elif oriented.mode == "L":
            image, transform = oriented.copy(), "original_8bit"
        else:
            rgba = oriented.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
            image, transform = (
                Image.alpha_composite(background, rgba).convert("RGB"),
                "rgb_preview",
            )
        return preview(
            image,
            {
                "format": expected,
                "width": oriented.width,
                "height": oriented.height,
                "display_transform": transform,
                "pixel_spacing_mm": None,
                "spacing_is_full_calibration": False,
                "exif_orientation_normalized": True,
            },
        )


def decode_image(data: bytes, suffix: str) -> DecodedImage:
    require(
        0 < len(data) <= MAX_IMAGE_BYTES, "image_size", "Tamanho de imagem inválido."
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            # Do not expose arbitrary metadata in pydicom warning messages.
            warnings.filterwarnings("ignore", category=UserWarning, module="pydicom.*")
            if suffix.lower() == ".dcm":
                return dicom_preview(data)
            require(
                suffix.lower() in {".png", ".jpg", ".jpeg"},
                "format",
                "Formato não suportado.",
            )
            return raster_preview(data, suffix.lower())
    except CaseError:
        raise
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        KeyError,
        IndexError,
        RuntimeError,
        NotImplementedError,
        OverflowError,
        RecursionError,
        struct.error,
        InvalidDicomError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as exc:
        raise CaseError(
            "pixel_decode",
            "Não foi possível decodificar os pixels. Arquivo inválido ou recurso não suportado.",
        ) from exc
