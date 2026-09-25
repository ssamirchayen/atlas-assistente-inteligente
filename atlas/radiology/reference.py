"""Bounded canonical volume references and explicit research provenance."""

import io
import math
import re
import shutil
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import numpy as np

from atlas.radiology.cases import CaseError, require
from atlas.radiology.privacy import digest, read_json, write_json

MAX_ARRAY_BYTES = 16 * 1024 * 1024


def load_arrays(path, required):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 32*1024*1024,
            "volume_file", "Volume ausente, link ou maior que 32 MiB.")
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            require(len(members) == len(required)
                    and {m.filename for m in members} == {k+".npy" for k in required}
                    and all(m.file_size <= MAX_ARRAY_BYTES for m in members),
                    "volume_archive", "NPZ contém campos inesperados ou arrays grandes demais.")
            result = {}
            for member in members:
                raw = archive.read(member)
                stream = io.BytesIO(raw)
                version = np.lib.format.read_magic(stream)
                require(version in ((1,0), (2,0)), "volume_format", "Versão NPY não suportada.")
                reader = (np.lib.format.read_array_header_1_0 if version == (1,0)
                          else np.lib.format.read_array_header_2_0)
                shape, _, dtype = reader(stream)
                require(len(shape) <= 3 and not dtype.hasobject and dtype.kind in "bifu"
                        and dtype.itemsize <= 8 and math.prod(shape)*dtype.itemsize <= MAX_ARRAY_BYTES
                        and len(raw)-stream.tell() == math.prod(shape)*dtype.itemsize,
                        "volume_array", "Array inválido, objeto ou tamanho inconsistente.")
                result[member.filename[:-4]] = np.load(io.BytesIO(raw), allow_pickle=False)
            return result
    except (BadZipFile, ValueError, EOFError, OverflowError):
        raise CaseError("volume_format", "Arquivo volumétrico inválido.") from None


def check_grid(arrays, key):
    volume = arrays[key]
    origin, spacing = arrays["origin_lps_mm"], arrays["spacing_mm"]
    require(volume.ndim == 3 and all(2 <= n <= 128 for n in volume.shape)
            and volume.size <= 2097152 and np.isfinite(volume).all(),
            "volume_grid", "Use grade 3D finita, de 2 a 128 células por eixo.")
    require(origin.shape == (3,) and spacing.shape == (3,)
            and origin.dtype.kind in "ifu" and spacing.dtype.kind in "ifu"
            and np.isfinite(origin).all() and np.isfinite(spacing).all()
            and (np.abs(origin) <= 1000000).all() and (spacing >= .25).all()
            and (spacing <= 20).all(), "volume_coordinates", "Origem ou espaçamento inválidos.")


def check_reference_arrays(arrays):
    check_grid(arrays, "hu")
    require(arrays["hu"].dtype.kind in "if" and (arrays["hu"] >= -1024).all()
            and (arrays["hu"] <= 10000).all(), "volume_hu", "HU fora do intervalo suportado.")
    mask = arrays["reference_mask"]
    require(mask.shape == arrays["hu"].shape and mask.dtype.kind in "biu"
            and np.isin(mask, [0,1]).all() and mask.any(),
            "reference_mask", "Máscara de referência deve ser binária e não vazia.")


def import_reference(volume: Path, output: Path, subject: str, split: str,
                     origin="research", authorized=False, privacy_reviewed=False):
    require(isinstance(subject, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", subject)
            and split in ("train", "validation", "test")
            and origin in ("synthetic", "research"), "reference_metadata",
            "Use código pseudônimo, origem e divisão válidos.")
    require(origin == "synthetic" or (authorized is True and privacy_reviewed is True),
            "research_authorization", "Pesquisa exige confirmação de autorização e revisão de privacidade.")
    arrays = load_arrays(volume, {"hu", "reference_mask", "origin_lps_mm", "spacing_mm"})
    check_reference_arrays(arrays)
    require(not output.exists(), "output_exists", "Use uma pasta nova.")
    output.mkdir(parents=True, exist_ok=False)
    try:
        # Re-encode only allowlisted numeric arrays; never copy extra ZIP members.
        np.savez_compressed(output / "reference.npz", **arrays)
        manifest = {"schema_version": 1, "origin": origin, "subject_code": subject,
                    "split": split, "coordinate_system": "LPS_mm_xyz_lower_corner",
                    "authorization_attested": bool(authorized),
                    "privacy_review_attested": bool(privacy_reviewed),
                    "volume_sha256": digest((output / "reference.npz").read_bytes()),
                    "clinical_use_validated": False}
        write_json(output / "reference.json", manifest)
        return output / "reference.json"
    except Exception:
        shutil.rmtree(output)
        raise


def read_reference(manifest: Path):
    data = read_json(manifest)
    fields = {"schema_version", "origin", "subject_code", "split", "coordinate_system",
              "authorization_attested", "privacy_review_attested", "volume_sha256",
              "clinical_use_validated"}
    require(isinstance(data, dict) and set(data) == fields
            and type(data["schema_version"]) is int and data["schema_version"] == 1
            and data["coordinate_system"] == "LPS_mm_xyz_lower_corner"
            and data["origin"] in ("synthetic", "research")
            and data["split"] in ("train", "validation", "test")
            and isinstance(data["subject_code"], str)
            and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", data["subject_code"])
            and type(data["authorization_attested"]) is bool
            and type(data["privacy_review_attested"]) is bool
            and data["clinical_use_validated"] is False,
            "reference_metadata", "Manifesto de referência inválido.")
    require(data["origin"] == "synthetic" or
            (data["authorization_attested"] and data["privacy_review_attested"]),
            "research_authorization", "Faltam declarações de pesquisa e privacidade.")
    path = manifest.parent / "reference.npz"
    arrays = load_arrays(path, {"hu", "reference_mask", "origin_lps_mm", "spacing_mm"})
    require(digest(path.read_bytes()) == data["volume_sha256"],
            "reference_checksum", "Volume de referência alterado.")
    check_reference_arrays(arrays)
    return data, arrays


def audit_reference_splits(manifests):
    require(1 <= len(manifests) <= 1000, "dataset_size", "Informe de 1 a 1000 referências.")
    subjects, content, counts = {}, {}, {"train":0, "validation":0, "test":0}
    for path in manifests:
        meta, arrays = read_reference(path)
        split = meta["split"]
        # Semantic fingerprint catches identical arrays compressed differently.
        fingerprint = digest(arrays["hu"].astype("<f8").tobytes()
                             + arrays["origin_lps_mm"].astype("<f8").tobytes()
                             + arrays["spacing_mm"].astype("<f8").tobytes()
                             + str(arrays["hu"].shape).encode("ascii"))
        require(meta["subject_code"] not in subjects or subjects[meta["subject_code"]] == split,
                "subject_leakage", "Mesmo sujeito presente em divisões diferentes.")
        require(fingerprint not in content or content[fingerprint] == split,
                "volume_leakage", "Mesmo volume presente em divisões diferentes.")
        subjects[meta["subject_code"]] = split
        content[fingerprint] = split
        counts[split] += 1
    return {"status": "no_detected_split_overlap", "counts": counts,
            "unique_subject_codes": len(subjects), "identity_verified": False,
            "external_validation": False}
