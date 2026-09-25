"""Create non-medical PNG test patterns. These are NOT simulated radiographs."""

import hashlib
import json
import struct
import zlib
from pathlib import Path
from uuid import uuid4


def pattern_png(index: int) -> bytes:
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    width = height = 64
    rows = b"".join(
        b"\0" + bytes((x * 3 + y * 2 + index * 47) % 256 for x in range(width))
        for y in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def create_demo(output: Path) -> Path:
    # Refuse to overwrite any existing case, including an earlier demo.
    output.mkdir(parents=True, exist_ok=False)
    study = "synthetic-" + uuid4().hex
    views = []
    for index, name in enumerate(("AP", "LATERAL", "OBLIQUE")):
        image = pattern_png(index)
        relative = name.lower() + ".png"
        with (output / relative).open("xb") as stream:
            stream.write(image)
        views.append(
            {
                "view": name,
                "relative_path": relative,
                "sha256": hashlib.sha256(image).hexdigest(),
                "study_id": study,
                "laterality": "L",
                "geometry": None,
            }
        )
    manifest = output / "case.json"
    with manifest.open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "schema_version": 1,
                "case_id": uuid4().hex,
                "study_id": study,
                "region": "knee_lower_leg",
                "laterality": "L",
                "data_origin": "synthetic",
                "views": views,
            },
            stream,
            indent=2,
        )
    return manifest
