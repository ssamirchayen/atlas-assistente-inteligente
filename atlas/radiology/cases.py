"""Validate an offline case manifest and file integrity, never image anatomy."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath

MAX_MANIFEST_BYTES = 256 * 1024
MAX_IMAGE_BYTES = 50 * 1024 * 1024
VIEWS = frozenset({"AP", "LATERAL", "OBLIQUE"})


class CaseError(ValueError):
    """A safe, static error code and explanation without patient data or paths."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise CaseError(code, message)


def fields(value, expected: set[str]) -> None:
    require(
        isinstance(value, dict) and set(value) == expected,
        "schema_fields",
        "Campos ausentes ou não suportados no manifesto.",
    )


def identifier(value) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value))


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_key", "Chave JSON repetida.")
        result[key] = value
    return result


def check_geometry(geometry) -> None:
    if geometry is None:
        return
    fields(geometry, {"calibration_id", "coordinate_system", "projection_matrix"})
    require(
        identifier(geometry["calibration_id"]),
        "geometry",
        "Identificador de calibração inválido.",
    )
    require(
        geometry["coordinate_system"] == "LPS_mm",
        "geometry",
        "Referencial esperado: LPS_mm.",
    )
    matrix = geometry["projection_matrix"]
    require(
        isinstance(matrix, list)
        and len(matrix) == 3
        and all(isinstance(row, list) and len(row) == 4 for row in matrix),
        "geometry",
        "A matriz de projeção deve ter dimensão 3 por 4.",
    )
    require(
        all(
            type(v) in (int, float) and math.isfinite(v) and abs(v) <= 1e12
            for row in matrix
            for v in row
        ),
        "geometry",
        "A matriz contém valores inválidos.",
    )
    # Scale rows before checking the determinant of the camera's left 3x3 block.
    scales = [max(abs(v) for v in row[:3]) for row in matrix]
    require(all(scales), "geometry", "Matriz de câmera degenerada.")
    a, b, c = [[v / scale for v in row[:3]] for row, scale in zip(matrix, scales)]
    det = (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )
    require(abs(det) > 1e-10, "geometry", "Matriz de câmera degenerada.")


def image_path(root: Path, relative) -> Path:
    require(
        isinstance(relative, str) and bool(relative),
        "path",
        "Caminho relativo ausente.",
    )
    require(
        "\\" not in relative and ":" not in relative and "\x00" not in relative,
        "path",
        "Caminho de imagem inválido.",
    )
    parts = relative.split("/")
    require(
        not PurePosixPath(relative).is_absolute()
        and all(p not in {"", ".", ".."} for p in parts),
        "path",
        "Use um caminho relativo dentro do caso.",
    )
    path = root.joinpath(*parts)
    require(
        not any(
            root.joinpath(*parts[:i]).is_symlink() for i in range(1, len(parts) + 1)
        ),
        "path",
        "Links simbólicos não são aceitos no caso.",
    )
    require(
        path.resolve().is_relative_to(root.resolve()),
        "path",
        "Imagem fora da pasta do caso.",
    )
    require(
        path.suffix.lower() in {".png", ".jpg", ".jpeg", ".dcm"},
        "format",
        "Extensão não suportada.",
    )
    return path


def check_image(path: Path, expected: str) -> None:
    require(path.is_file(), "missing_image", "Uma imagem referenciada não existe.")
    require(
        0 < path.stat().st_size <= MAX_IMAGE_BYTES,
        "image_size",
        "Tamanho de imagem inválido.",
    )
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        header = stream.read(132)
        digest.update(header)
        size += len(header)
        for block in iter(lambda: stream.read(65536), b""):
            size += len(block)
            require(size <= MAX_IMAGE_BYTES, "image_size", "Imagem excede o limite.")
            digest.update(block)
    suffix = path.suffix.lower()
    valid_signature = (
        (suffix == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"))
        or (suffix in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff"))
        or (suffix == ".dcm" and header[128:132] == b"DICM")
    )
    require(
        valid_signature,
        "signature",
        "Assinatura do arquivo incompatível com a extensão.",
    )
    require(
        digest.hexdigest() == expected,
        "checksum",
        "A integridade de uma imagem não confere.",
    )


def validate_case(manifest: Path) -> dict:
    try:
        with manifest.open("rb") as stream:
            raw = stream.read(MAX_MANIFEST_BYTES + 1)
        require(
            len(raw) <= MAX_MANIFEST_BYTES,
            "manifest_size",
            "Manifesto excede o limite.",
        )
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        fields(
            data,
            {
                "schema_version",
                "case_id",
                "study_id",
                "region",
                "laterality",
                "data_origin",
                "views",
            },
        )
        require(
            type(data["schema_version"]) is int and data["schema_version"] == 1,
            "version",
            "Versão de manifesto não suportada.",
        )
        require(
            identifier(data["case_id"]) and identifier(data["study_id"]),
            "identifier",
            "Identificadores de caso ou estudo inválidos.",
        )
        require(
            data["region"] == "knee_lower_leg",
            "region",
            "Esta etapa cobre somente joelho/perna.",
        )
        require(
            data["laterality"] in ("L", "R"),
            "laterality",
            "Lateralidade deve ser L ou R.",
        )
        require(
            data["data_origin"] in ("synthetic", "research"),
            "origin",
            "Origem deve ser synthetic ou research.",
        )
        views = data["views"]
        require(
            isinstance(views, list) and len(views) == 3,
            "views",
            "São necessárias três projeções.",
        )
        seen, paths, hashes, calibration_ids = set(), set(), set(), set()
        geometry_count = 0
        for view in views:
            fields(
                view,
                {
                    "view",
                    "relative_path",
                    "sha256",
                    "study_id",
                    "laterality",
                    "geometry",
                },
            )
            name = view["view"]
            require(
                isinstance(name, str) and name in VIEWS and name not in seen,
                "views",
                "Exige AP, LATERAL e OBLIQUE sem repetição.",
            )
            seen.add(name)
            require(
                view["study_id"] == data["study_id"],
                "study_mismatch",
                "As projeções declaram estudos diferentes.",
            )
            require(
                view["laterality"] == data["laterality"],
                "side_mismatch",
                "As projeções declaram lados diferentes.",
            )
            digest = view["sha256"]
            require(
                isinstance(digest, str) and bool(re.fullmatch(r"[a-f0-9]{64}", digest)),
                "checksum",
                "SHA-256 inválido.",
            )
            path = image_path(manifest.parent, view["relative_path"])
            require(
                path.resolve() not in paths and digest not in hashes,
                "duplicate_image",
                "Projeções não podem reutilizar a mesma imagem.",
            )
            paths.add(path.resolve())
            hashes.add(digest)
            check_image(path, digest)
            check_geometry(view["geometry"])
            if view["geometry"] is not None:
                geometry_count += 1
                calibration_ids.add(view["geometry"]["calibration_id"])
        require(
            geometry_count in (0, 3),
            "partial_geometry",
            "A geometria deve ser declarada nas três projeções ou permanecer ausente.",
        )
        require(
            len(calibration_ids) <= 1,
            "calibration_mismatch",
            "As projeções devem usar a mesma calibração declarada.",
        )
        return {
            "schema_version": 1,
            "status": "files_and_manifest_valid",
            "views_checked": sorted(seen),
            "synthetic": data["data_origin"] == "synthetic",
            "geometry_status": "declared_not_verified" if geometry_count else "missing",
            "pixel_decoding_performed": False,
            "anatomy_or_projection_verified": False,
            "privacy_review_required": data["data_origin"] != "synthetic",
            "reconstruction_available": False,
            "clinical_use_validated": False,
        }
    except CaseError:
        raise
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise CaseError(
            "invalid_case", "Não foi possível ler ou validar o caso."
        ) from exc
