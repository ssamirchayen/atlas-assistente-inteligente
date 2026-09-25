"""Manual research contours and landmarks bound to rendered image content."""

import base64
import io
import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from atlas.radiology.cases import image_path, require, validate_case
from atlas.radiology.imaging import decode_image, read_image_bytes
from atlas.radiology.privacy import VIEWS, digest, read_json, write_json

BONES = ("femur_distal", "tibia", "fibula", "patella")


def annotation_context(manifest):
    validate_case(manifest)
    raw_manifest = manifest.read_bytes()
    data = json.loads(raw_manifest)
    views, images = {}, {}
    for view in data["views"]:
        source = image_path(manifest.parent, view["relative_path"])
        raw = read_image_bytes(source)
        require(digest(raw) == view["sha256"], "checksum", "Imagem de origem alterada.")
        decoded = decode_image(raw, source.suffix)
        with Image.open(io.BytesIO(decoded.preview_png)) as im:
            size = list(im.size)
        views[view["view"]] = {"source_sha256": digest(raw),
                               "preview_sha256": digest(decoded.preview_png),
                               "size": size, "polygons": [], "landmarks": []}
        images[view["view"]] = decoded.preview_png
    return {"schema_version": 1, "manifest_sha256": digest(raw_manifest),
            "coordinate_space": "rendered_preview_pixels",
            "views": views}, images


def create_annotation_editor(manifest: Path, output: Path):
    require(not output.exists(), "output_exists", "Use uma pasta nova para o editor.")
    context, images = annotation_context(manifest)
    template = Path(__file__).with_name("annotation_editor.html").read_text(encoding="utf-8")
    payload = {"annotation": context, "images": {
        name: "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        for name, raw in images.items()}}
    page = template.replace("__ANNOTATION_DATA__", json.dumps(payload).replace("<", "\\u003c"))
    output.mkdir(parents=True, exist_ok=False)
    try:
        (output / "index.html").write_text(page, encoding="utf-8")
        write_json(output / "annotation-template.json", context)
        return output / "index.html"
    except Exception:
        shutil.rmtree(output)
        raise


def point(value, size):
    require(isinstance(value, list) and len(value) == 2
            and all(type(n) in (int, float) and 0 <= n <= 16000
                    and math.isfinite(n) for n in value)
            and 0 <= value[0] < size[0] and 0 <= value[1] < size[1],
            "annotation_point", "Ponto inválido ou fora da imagem.")


def simple_polygon(points):
    require(len({tuple(p) for p in points}) == len(points),
            "annotation_polygon", "Contorno contém pontos repetidos.")
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])

    def intersects(a, b, c, d):
        ab1, ab2, cd1, cd2 = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
        def on(a, b, c):
            return (min(a[0], b[0]) <= c[0] <= max(a[0], b[0])
                    and min(a[1], b[1]) <= c[1] <= max(a[1], b[1]))
        return ((ab1 * ab2 < 0 and cd1 * cd2 < 0)
                or (ab1 == 0 and on(a, b, c)) or (ab2 == 0 and on(a, b, d))
                or (cd1 == 0 and on(c, d, a)) or (cd2 == 0 and on(c, d, b)))

    n = len(points)
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            require(not intersects(points[i], points[(i+1) % n],
                                   points[j], points[(j+1) % n]),
                    "annotation_polygon", "Contorno se cruza ou se toca.")
    area = abs(sum(points[i][0] * points[(i+1) % n][1]
                   - points[(i+1) % n][0] * points[i][1] for i in range(n))) / 2
    require(area >= 1, "annotation_polygon", "Contorno sem área suficiente.")


def validate_annotation(manifest: Path, annotation: Path):
    expected, _ = annotation_context(manifest)
    data = read_json(annotation)
    require(isinstance(data, dict) and set(data) == set(expected)
            and type(data["schema_version"]) is int and data["schema_version"] == 1
            and data["manifest_sha256"] == expected["manifest_sha256"]
            and data["coordinate_space"] == expected["coordinate_space"]
            and isinstance(data["views"], dict) and set(data["views"]) == set(VIEWS),
            "annotation_binding", "Anotação inválida ou de outro caso.")
    count = 0
    for name in VIEWS:
        view = data["views"][name]
        require(isinstance(view, dict) and set(view) == set(expected["views"][name]),
                "annotation_view", "Vista de anotação inválida.")
        for field in ("source_sha256", "preview_sha256", "size"):
            require(view[field] == expected["views"][name][field],
                    "annotation_binding", "Imagem ou prévia diferente da anotada.")
        require(isinstance(view["polygons"], list) and len(view["polygons"]) <= 40
                and isinstance(view["landmarks"], list) and len(view["landmarks"]) <= 100,
                "annotation_limit", "Limite de anotações excedido.")
        for polygon in view["polygons"]:
            require(isinstance(polygon, dict) and set(polygon) == {"bone", "points"}
                    and polygon["bone"] in BONES and isinstance(polygon["points"], list)
                    and 3 <= len(polygon["points"]) <= 200,
                    "annotation_polygon", "Contorno inválido: use de 3 a 200 vértices.")
            for p in polygon["points"]:
                point(p, view["size"])
            simple_polygon(polygon["points"])
            count += 1
        ids = set()
        for landmark in view["landmarks"]:
            require(isinstance(landmark, dict)
                    and set(landmark) == {"bone", "label", "point"}
                    and landmark["bone"] in BONES
                    and landmark["label"] in ("P1", "P2", "P3", "P4"),
                    "annotation_landmark", "Marco inválido.")
            point(landmark["point"], view["size"])
            identity = (landmark["bone"], landmark["label"])
            require(identity not in ids, "annotation_landmark", "Marco duplicado na vista.")
            ids.add(identity)
    require(count > 0, "annotation_empty", "Desenhe ao menos um contorno antes de exportar.")
    return data


def export_annotation(manifest: Path, annotation: Path, output: Path):
    data = validate_annotation(manifest, annotation)
    require(not output.exists(), "output_exists", "Use uma pasta nova para exportar.")
    output.mkdir(parents=True, exist_ok=False)
    try:
        files = {}
        for name, view in data["views"].items():
            for bone in BONES:
                polygons = [p for p in view["polygons"] if p["bone"] == bone]
                if not polygons:
                    continue  # Missing anatomy is not represented as a negative mask.
                mask = Image.new("L", tuple(view["size"]), 0)
                draw = ImageDraw.Draw(mask)
                for poly in polygons:
                    draw.polygon([tuple(p) for p in poly["points"]], fill=255)
                filename = name.lower() + "_" + bone + ".png"
                mask.save(output / filename)
                files[filename] = digest((output / filename).read_bytes())
        write_json(output / "annotations.json", data)
        write_json(output / "annotation-report.json", {
            "schema_version": 1, "status": "manual_annotations_exported",
            "annotation_sha256": digest(annotation.read_bytes()), "masks": files,
            "coordinate_space": "rendered_preview_pixels",
            "landmark_correspondence_verified": False,
            "anatomy_verified": False, "clinical_use_validated": False,
            "ready_for_metric_reconstruction": False,
        })
        return output / "annotation-report.json"
    except Exception:
        shutil.rmtree(output)
        raise
