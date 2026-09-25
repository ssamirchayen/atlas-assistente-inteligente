"""Import immutable source copies and build an offline 2D viewing folder."""

import hashlib
import base64
import json
import shutil
from pathlib import Path
from uuid import uuid4

from atlas.radiology.cases import image_path, require, validate_case
from atlas.radiology.imaging import decode_image, read_image_bytes


def import_case(sources: dict[str, Path], output: Path, side: str, origin: str) -> Path:
    require(
        set(sources) == {"AP", "LATERAL", "OBLIQUE"},
        "views",
        "Selecione as três projeções.",
    )
    require(
        side in {"L", "R"} and origin in {"synthetic", "research"},
        "case_fields",
        "Lado ou origem inválidos.",
    )
    require(not output.exists(), "output_exists", "Escolha uma pasta de destino nova.")
    prepared = []
    identities = []
    for view, source in sources.items():
        data = read_image_bytes(source)
        decoded = decode_image(data, source.suffix)
        identities.append(decoded.identity)
        declared_side = decoded.identity.get("ImageLaterality", "")
        require(
            not declared_side or declared_side == side,
            "side_mismatch",
            "A lateralidade DICOM difere do lado escolhido.",
        )
        prepared.append((view, source.suffix.lower(), data, decoded.metadata))
    for key in ("PatientID", "StudyInstanceUID"):
        declared = {item[key] for item in identities if item.get(key)}
        require(
            len(declared) <= 1,
            "study_mismatch",
            "Os arquivos DICOM declaram pacientes ou estudos diferentes.",
        )
    output.mkdir(parents=True, exist_ok=False)
    try:
        study = "study-" + uuid4().hex
        views, metadata = [], {}
        for view, suffix, data, technical in prepared:
            name = view.lower() + suffix
            with (output / name).open("xb") as stream:
                stream.write(data)
            views.append(
                {
                    "view": view,
                    "relative_path": name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "study_id": study,
                    "laterality": side,
                    "geometry": None,
                }
            )
            metadata[view] = technical
        manifest = output / "case.json"
        with manifest.open("x", encoding="utf-8") as stream:
            json.dump(
                {
                    "schema_version": 1,
                    "case_id": uuid4().hex,
                    "study_id": study,
                    "region": "knee_lower_leg",
                    "laterality": side,
                    "data_origin": origin,
                    "views": views,
                },
                stream,
                indent=2,
            )
        validate_case(manifest)
        with (output / "pixel-report.json").open("x", encoding="utf-8") as stream:
            json.dump(metadata, stream, indent=2)
        return manifest
    except Exception:
        # Only this newly-created folder; source files are never changed.
        shutil.rmtree(output)
        raise


def build_viewer(manifest: Path, output: Path) -> Path:
    validate_case(manifest)
    require(
        not output.exists(),
        "output_exists",
        "Escolha uma pasta nova para o visualizador.",
    )
    data = json.loads(manifest.read_text(encoding="utf-8"))
    prepared = []
    for view in data["views"]:
        source = image_path(manifest.parent, view["relative_path"])
        raw = read_image_bytes(source)
        require(
            hashlib.sha256(raw).hexdigest() == view["sha256"],
            "checksum",
            "Uma imagem foi alterada.",
        )
        prepared.append((view["view"], decode_image(raw, source.suffix)))
    output.mkdir(parents=True, exist_ok=False)
    try:
        report = {}
        previews = {}
        for name, decoded in prepared:
            with (output / (name.lower() + ".png")).open("xb") as stream:
                stream.write(decoded.preview_png)
            report[name] = decoded.metadata
            previews[name] = "data:image/png;base64," + base64.b64encode(
                decoded.preview_png
            ).decode("ascii")
        template = Path(__file__).with_name("viewer.html").read_text(encoding="utf-8")
        # Whitelisted technical data only, escaped even if the whitelist expands.
        payload = json.dumps(report, ensure_ascii=True).replace("<", "\\u003c")
        page = template.replace("__TECHNICAL_DATA__", payload)
        page = page.replace("__PREVIEW_DATA__", json.dumps(previews))
        page = page.replace(
            "__CASE_ORIGIN__",
            "Demonstração: padrões sintéticos, não são radiografias."
            if data["data_origin"] == "synthetic"
            else "Caso de pesquisa: revisar identificação nos pixels antes de compartilhar.",
        )
        page = page.replace(
            "__SIDE__", "Esquerdo" if data["laterality"] == "L" else "Direito"
        )
        with (output / "index.html").open("x", encoding="utf-8") as stream:
            stream.write(page)
        with (output / "pixel-report.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
        return output / "index.html"
    except Exception:
        shutil.rmtree(output)
        raise
