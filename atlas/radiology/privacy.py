"""Reviewed display derivatives; not a DICOM confidentiality implementation."""

import base64
import hashlib
import io
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from PIL import Image

from atlas.radiology.cases import CaseError, image_path, require, validate_case
from atlas.radiology.imaging import decode_image, read_image_bytes

VIEWS = ("AP", "LATERAL", "OBLIQUE")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    try:
        with path.open("rb") as stream:
            raw = stream.read(262145)
        require(len(raw) <= 262144, "privacy_size", "Registro grande demais.")
        return json.loads(raw)
    except (ValueError, UnicodeError):
        raise CaseError("privacy_json", "Registro JSON inválido.") from None


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)


def now():
    return datetime.now(timezone.utc).isoformat()


def prepare_privacy(manifest: Path, output: Path, masks: dict | None = None):
    """Create new, metadata-free 8-bit display PNGs and private provenance."""
    validate_case(manifest)
    require(not output.exists(), "output_exists", "Use uma pasta nova.")
    masks = {} if masks is None else masks
    require(isinstance(masks, dict) and set(masks) <= set(VIEWS),
            "masks", "Máscaras devem indicar AP, LATERAL ou OBLIQUE.")
    case = read_json(manifest)
    prepared, records = {}, {}
    for view in case["views"]:
        name = view["view"]
        source = image_path(manifest.parent, view["relative_path"])
        raw = read_image_bytes(source)
        require(digest(raw) == view["sha256"], "checksum", "Origem alterada.")
        decoded = decode_image(raw, source.suffix)
        with Image.open(io.BytesIO(decoded.preview_png)) as image:
            clean = Image.frombytes(image.mode, image.size, image.tobytes())
        boxes = masks.get(name, [])
        require(isinstance(boxes, list) and len(boxes) <= 100,
                "masks", "Lista de máscaras inválida.")
        for box in boxes:
            require(isinstance(box, list) and len(box) == 4
                    and all(type(n) is int for n in box),
                    "masks", "Use retângulos [x0, y0, x1, y1] inteiros.")
            x0, y0, x1, y1 = box
            require(0 <= x0 < x1 <= clean.width and 0 <= y0 < y1 <= clean.height,
                    "masks", "Retângulo fora da imagem de visualização.")
            clean.paste(0, (x0, y0, x1, y1))
        buffer = io.BytesIO()
        clean.save(buffer, format="PNG")
        prepared[name] = buffer.getvalue()
        records[name] = {"source_sha256": digest(raw), "masks": boxes,
                         "width": clean.width, "height": clean.height}
    output.mkdir(parents=True, exist_ok=False)
    try:
        bundle = {"schema_version": 1, "bundle_id": uuid4().hex,
                  "created_at": now(), "status": "pending_pixel_review",
                  "derivative": "display_png_8bit_max1600",
                  "clinical_use_validated": False, "reconstruction_available": False,
                  "images": {name: digest(raw) for name, raw in prepared.items()}}
        for name, raw in prepared.items():
            (output / (name.lower() + ".png")).write_bytes(raw)
        write_json(output / "provenance-private.json", {
            "schema_version": 1, "bundle_id": bundle["bundle_id"],
            "source_manifest_sha256": digest(manifest.read_bytes()), "views": records,
        })
        bundle["provenance_sha256"] = digest(
            (output / "provenance-private.json").read_bytes())
        write_json(output / "privacy.json", bundle)
        # Embedded pixels are pending review too. Never include this page in export.
        page = ['<!doctype html><html lang="pt-BR"><meta charset="utf-8">',
                '<meta name="viewport" content="width=device-width,initial-scale=1">',
                '<title>Revisão de privacidade — Atlas</title>',
                '<style>body{font:18px sans-serif;margin:32px;background:#102030;',
                'color:white}img{display:block}section{overflow:auto;margin:32px 0}',
                '</style><h1>Revisão obrigatória dos pixels</h1>',
                '<p>PENDENTE. Não compartilhe esta pasta. Examine as três imagens ',
                'em tamanho real, inclusive bordas, nomes, datas e códigos. ',
                'As coordenadas das máscaras referem-se a estes PNGs.</p>',
                '<p>Cópias de visualização: 8 bits, até 1600 pixels. ',
                'Sem validação clínica ou reconstrução 3D.</p>']
        for name, raw in prepared.items():
            encoded = base64.b64encode(raw).decode("ascii")
            page.append(f'<h2>{name}</h2><section><img alt="{name}" '
                        f'src="data:image/png;base64,{encoded}"></section>')
        page.append('</html>')
        (output / "review.html").write_text("".join(page), encoding="utf-8")
        return output / "privacy.json"
    except Exception:
        shutil.rmtree(output)
        raise


def checked_bundle(folder):
    path = folder / "privacy.json"
    require(not path.is_symlink(), "privacy_link", "Registro não pode ser link.")
    bundle = read_json(path)
    require(isinstance(bundle, dict) and bundle.get("schema_version") == 1
            and isinstance(bundle.get("images"), dict)
            and set(bundle["images"]) == set(VIEWS)
            and isinstance(bundle.get("bundle_id"), str)
            and re.fullmatch(r"[a-f0-9]{32}", bundle["bundle_id"]) is not None,
            "privacy_bundle", "Pacote de revisão inválido.")
    images = {}
    provenance = folder / "provenance-private.json"
    require(not provenance.is_symlink(), "privacy_link", "Registro não pode ser link.")
    require(digest(provenance.read_bytes()) == bundle.get("provenance_sha256"),
            "privacy_changed", "Rastreabilidade alterada: prepare novamente.")
    for name in VIEWS:
        path = image_path(folder, name.lower() + ".png")
        raw = read_image_bytes(path)
        require(digest(raw) == bundle["images"][name],
                "privacy_changed", "Imagem alterada: prepare e revise novamente.")
        # Reject metadata injected into a forged bundle; only fresh encoder output.
        with Image.open(io.BytesIO(raw)) as im:
            require(im.format == "PNG" and im.mode in {"L", "RGB"}
                    and max(im.size) <= 1600 and not im.info,
                    "privacy_image", "PNG de revisão inválido.")
            im.load()
        images[name] = raw
    return bundle, images, digest((folder / "privacy.json").read_bytes())


def record_review(folder: Path, decisions: dict, reviewer: str, output: Path):
    bundle, _, bundle_hash = checked_bundle(folder)
    require(re.fullmatch(r"[A-Za-z0-9_-]{1,40}", reviewer) is not None,
            "reviewer", "Use um código de operador, sem nome ou e-mail.")
    require(set(decisions) == set(VIEWS)
            and all(v in {"clear", "reject"} for v in decisions.values()),
            "review", "Registre clear ou reject para cada uma das três imagens.")
    record = {"schema_version": 1, "bundle_id": bundle["bundle_id"],
              "bundle_sha256": bundle_hash, "reviewer_code": reviewer,
              "reviewed_at": now(), "decisions": decisions,
              "method": "human_visual_attestation"}
    write_json(output, record)
    return record


def export_reviewed(folder: Path, review: Path, output: Path):
    bundle, images, bundle_hash = checked_bundle(folder)
    record = read_json(review)
    require(isinstance(record, dict) and record.get("schema_version") == 1
            and record.get("bundle_id") == bundle["bundle_id"]
            and record.get("bundle_sha256") == bundle_hash
            and record.get("method") == "human_visual_attestation"
            and record.get("decisions") == dict.fromkeys(VIEWS, "clear"),
            "review_required", "Exportação bloqueada: falta aprovação das três imagens.")
    require(not output.exists(), "output_exists", "Use uma pasta nova para exportar.")
    output.mkdir(parents=True, exist_ok=False)
    try:
        for name, raw in images.items():
            (output / (name.lower() + ".png")).write_bytes(raw)
        # Allowlist only: no original IDs, source hashes, reviewer or arbitrary text.
        write_json(output / "export.json", {
            "schema_version": 1, "export_id": uuid4().hex,
            "bundle_id": bundle["bundle_id"],
            "status": "human_reviewed_display_derivatives",
            "images": {name: digest(raw) for name, raw in images.items()},
            "derivative": "display_png_8bit_max1600",
            "automatic_anonymity_guaranteed": False,
            "dicom_confidentiality_profile_validated": False,
            "clinical_use_validated": False, "reconstruction_available": False,
        })
        return output / "export.json"
    except Exception:
        shutil.rmtree(output)
        raise
