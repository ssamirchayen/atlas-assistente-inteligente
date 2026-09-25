"""Offline 3D surface viewer linked to supplied projection geometry."""

import base64
import io
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from atlas.radiology.cases import CaseError, image_path, require, validate_case
from atlas.radiology.geometry import validate_geometry
from atlas.radiology.imaging import decode_image, read_image_bytes
from atlas.radiology.privacy import VIEWS, digest, read_json, write_json


def read_surface(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 32*1024*1024,
            "viewer_mesh", "Malha ausente, link ou grande demais.")
    raw = path.read_bytes()
    vertices, faces = [], []
    try:
        for line in raw.decode("ascii").splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) == 4 and parts[0] == "v":
                vertices.append([float(x) for x in parts[1:]])
            elif len(parts) == 4 and parts[0] == "f":
                faces.append([int(x)-1 for x in parts[1:]])
            else:
                raise ValueError
    except (ValueError, UnicodeError, OverflowError):
        raise CaseError("viewer_mesh", "Formato de malha não suportado.") from None
    require(3 <= len(vertices) <= 100000 and 1 <= len(faces) <= 100000,
            "viewer_mesh_budget", "Visualizador aceita até 100000 vértices e triângulos.")
    points = np.asarray(vertices)
    indices = np.asarray(faces)
    require(np.isfinite(points).all() and (np.abs(points) <= 1e9).all()
            and indices.min() >= 0 and indices.max() < len(points)
            and all(len(set(f)) == 3 for f in faces),
            "viewer_mesh", "Vértices ou índices inválidos.")
    triangles = points[indices]
    area = np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],
                                   triangles[:,2]-triangles[:,0]),axis=1)
    require((area > 1e-12).all(), "viewer_mesh", "Malha contém triângulos degenerados.")
    return raw, vertices, faces


def build_linked_viewer(manifest: Path, geometry: Path, result: Path, output: Path):
    validate_case(manifest)
    case = read_json(manifest)
    report = read_json(result / "reconstruction-report.json")
    require(isinstance(report,dict) and report.get("manifest_sha256") == digest(manifest.read_bytes())
            and report.get("geometry_sha256") == digest(geometry.read_bytes()),
            "viewer_binding", "Resultado, caso e geometria não correspondem.")
    require(report.get("status") in ("experimental_envelope_generated","roi_boundary_warning")
            and report.get("method") == "voxel_center_silhouette_intersection_v1"
            and report.get("coordinate_system") == "LPS_mm", "viewer_report",
            "Relatório de reconstrução não suportado.")
    require(isinstance(report.get("mesh_sha256"),str), "viewer_legacy_result",
            "Resultado antigo sem hash da malha. Gere novamente com a Etapa 9 instalada.")
    raw, vertices, faces = read_surface(result / "envelope.obj")
    require(digest(raw) == report["mesh_sha256"], "viewer_integrity", "Malha alterada.")
    checked = validate_geometry(geometry,manifest if case["data_origin"] == "research" else None)
    geo = read_json(geometry)
    require(geo["origin"] == case["data_origin"]
            and checked["status"] == "geometry_consistent", "viewer_geometry",
            "Geometria inconsistente ou de outra origem.")
    payload = {"vertices":vertices,"faces":faces,"views":{},
               "synthetic":case["data_origin"] == "synthetic",
               "roi_warning":report["status"] == "roi_boundary_warning"}
    for name in VIEWS:
        view = next(v for v in case["views"] if v["view"] == name)
        source = image_path(manifest.parent,view["relative_path"])
        image_bytes = read_image_bytes(source)
        require(digest(image_bytes) == view["sha256"],"viewer_integrity","Imagem alterada.")
        decoded = decode_image(image_bytes,source.suffix)
        if source.suffix.lower() != ".dcm":
            with Image.open(io.BytesIO(image_bytes)) as image:
                require(image.getexif().get(274,1) == 1,"viewer_orientation",
                        "Imagem com transformação EXIF não suportada.")
        size = [decoded.metadata["preview_width"],decoded.metadata["preview_height"]]
        require(size == geo["views"][name]["image_size"]
                and size == [decoded.metadata["width"],decoded.metadata["height"]],
                "viewer_mapping","Prévia e geometria exigem pixels sem redimensionamento.")
        payload["views"][name] = {
            "size":size,"matrix":checked["views"][name]["projection_matrix"],
            "image":"data:image/png;base64,"+base64.b64encode(decoded.preview_png).decode("ascii")}
    template = Path(__file__).with_name("linked_viewer.html").read_text(encoding="utf-8")
    math_script = Path(__file__).with_name("linked_math.js").read_text(encoding="utf-8")
    template = template.replace("__LINKED_MATH__",math_script)
    page = template.replace("__LINKED_DATA__",json.dumps(payload).replace("<","\\u003c"))
    require(not output.exists(),"output_exists","Use uma pasta nova para o visualizador.")
    output.mkdir(parents=True,exist_ok=False)
    try:
        (output / "index.html").write_text(page,encoding="utf-8")
        write_json(output / "viewer-report.json",{
            "schema_version":1,"status":"linked_viewer_created",
            "manifest_sha256":digest(manifest.read_bytes()),
            "geometry_sha256":digest(geometry.read_bytes()),
            "mesh_sha256":digest(raw),"clinical_use_validated":False,
            "link_type":"geometric_projection_not_anatomical_confirmation",
        })
        return output / "index.html"
    except Exception:
        shutil.rmtree(output)
        raise
