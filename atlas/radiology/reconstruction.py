"""Experimental voxel silhouette intersection, without an anatomical prior."""

import io
import math
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from atlas.radiology.annotations import BONES, validate_annotation
from atlas.radiology.cases import image_path, require
from atlas.radiology.geometry import array, camera, project, validate_geometry
from atlas.radiology.imaging import decode_image, read_image_bytes
from atlas.radiology.privacy import VIEWS, digest, read_json, write_json


def grid_points(bounds, spacing):
    limits = array(bounds, (2, 3))
    require(type(spacing) in (int, float) and math.isfinite(spacing)
            and 0.25 <= spacing <= 20 and (limits[1] > limits[0]).all(),
            "reconstruction_grid", "Limites inválidos; voxel deve medir 0,25–20 mm.")
    counts_float = (limits[1] - limits[0]) / spacing
    require((counts_float >= 2).all() and (counts_float <= 128).all()
            and np.allclose(counts_float, np.rint(counts_float), atol=1e-7, rtol=0),
            "reconstruction_grid", "Extensão deve ser múltipla do voxel, com 2–128 células por eixo.")
    counts = np.rint(counts_float).astype(int)
    require(int(np.prod(counts)) <= 262144, "reconstruction_budget",
            "Grade excede 262144 voxels. Aumente o tamanho do voxel.")
    indices = np.indices(tuple(counts)).reshape(3, -1).T
    return limits[0] + (indices + .5) * spacing, indices, counts, limits


def carve(points, cameras, masks):
    keep = np.ones(len(points), dtype=bool)
    for name in VIEWS:
        k, r, c = cameras[name]
        local = (r @ (points - c).T).T
        valid = local[:, 2] > 1e-6
        projected = np.zeros((len(points), 2))
        h = (k @ local[valid].T).T
        projected[valid] = h[:, :2] / h[:, 2, None]
        height, width = masks[name].shape
        valid &= ((projected[:, 0] >= 0) & (projected[:, 0] < width - .5)
                  & (projected[:, 1] >= 0) & (projected[:, 1] < height - .5))
        pixels = np.floor(projected[valid] + .5).astype(int)
        accepted = np.zeros(len(points), dtype=bool)
        accepted[valid] = masks[name][pixels[:, 1], pixels[:, 0]]
        keep &= accepted
    return keep


def convex_hull(points):
    pts = sorted(set(map(tuple, points)))
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
    def half(items):
        result = []
        for p in items:
            while len(result) >= 2 and cross(result[-2], result[-1], p) <= 0:
                result.pop()
            result.append(p)
        return result
    return half(pts)[:-1] + half(reversed(pts))[:-1]


def voxel_projection(points, spacing, cam, size):
    image = Image.new("L", size, 0)
    draw = ImageDraw.Draw(image)
    corners = np.array([[x, y, z] for x in (-.5, .5)
                        for y in (-.5, .5) for z in (-.5, .5)]) * spacing
    # Project occupied cell footprints, not just sparse voxel centers.
    for center in points:
        outline = convex_hull(project(*cam, center + corners))
        if len(outline) >= 3:
            draw.polygon(outline, fill=255)
    return image


def write_surface(path, occupied, lower, spacing):
    """Exposed voxel faces with shared vertices, no smoothing or hole filling."""
    cells = {tuple(p) for p in np.argwhere(occupied)}
    vertices, faces = {}, []
    facespec = [((-1,0,0),[(0,0,0),(0,0,1),(0,1,1),(0,1,0)]),
                ((1,0,0),[(1,0,0),(1,1,0),(1,1,1),(1,0,1)]),
                ((0,-1,0),[(0,0,0),(1,0,0),(1,0,1),(0,0,1)]),
                ((0,1,0),[(0,1,0),(0,1,1),(1,1,1),(1,1,0)]),
                ((0,0,-1),[(0,0,0),(0,1,0),(1,1,0),(1,0,0)]),
                ((0,0,1),[(0,0,1),(1,0,1),(1,1,1),(0,1,1)])]
    for cell in sorted(cells):
        for direction, offsets in facespec:
            if tuple(cell[i]+direction[i] for i in range(3)) in cells:
                continue
            face = []
            for offset in offsets:
                vertex = tuple(cell[i]+offset[i] for i in range(3))
                if vertex not in vertices:
                    vertices[vertex] = len(vertices)+1
                face.append(vertices[vertex])
            faces.append(face)
    require(len(faces) <= 200000, "mesh_budget", "Superfície excede limite de faces.")
    with path.open("x", encoding="ascii") as stream:
        stream.write("# Atlas experimental voxel envelope; LPS millimeters; not clinical\n")
        for vertex in vertices:
            xyz = lower + np.array(vertex) * spacing
            stream.write("v " + " ".join(f"{n:.9g}" for n in xyz) + "\n")
        for a, b, c, d in faces:
            stream.write(f"f {a} {b} {c}\nf {a} {c} {d}\n")
    return {"vertices": len(vertices), "triangles": 2*len(faces)}


def reconstruct(manifest: Path, annotation: Path, geometry: Path,
                settings: Path, output: Path):
    annotations = validate_annotation(manifest, annotation)
    case = read_json(manifest)
    geo = read_json(geometry)
    require(case["data_origin"] == geo.get("origin"), "reconstruction_origin",
            "Origem do caso e da geometria deve coincidir.")
    checked = validate_geometry(geometry, manifest if geo["origin"] == "research" else None)
    require(checked["status"] == "geometry_consistent", "calibration_failed",
            "Geometria não passou na comparação com os marcadores.")
    config = read_json(settings)
    require(isinstance(config, dict) and set(config) == {
        "schema_version", "bone", "bounds_lps_mm", "voxel_size_mm"}
        and type(config["schema_version"]) is int and config["schema_version"] == 1
        and config["bone"] in BONES, "reconstruction_settings", "Configuração inválida.")
    spacing = config["voxel_size_mm"]
    points, _, counts, bounds = grid_points(config["bounds_lps_mm"], spacing)
    require(not output.exists(), "output_exists", "Use uma pasta nova para reconstrução.")
    masks, cameras = {}, {}
    for name in VIEWS:
        view = annotations["views"][name]
        require(view["size"] == geo["views"][name]["image_size"], "preview_mapping",
                "Prévia redimensionada: mapeamento para pixels originais ainda não suportado.")
        source_view = next(v for v in case["views"] if v["view"] == name)
        source = image_path(manifest.parent, source_view["relative_path"])
        source_bytes = read_image_bytes(source)
        decoded = decode_image(source_bytes, source.suffix)
        require(view["size"] == [decoded.metadata["width"], decoded.metadata["height"]],
                "preview_mapping", "Prévia reduzida não pode ser usada sem mapeamento explícito.")
        if source.suffix.lower() != ".dcm":
            with Image.open(io.BytesIO(source_bytes)) as im:
                require(im.getexif().get(274, 1) == 1, "preview_orientation",
                        "Orientação EXIF transformada não suportada nesta reconstrução.")
        polygons = [p for p in view["polygons"] if p["bone"] == config["bone"]]
        require(bool(polygons), "missing_contour", "Anote a estrutura nas três vistas.")
        mask = Image.new("L", tuple(view["size"]), 0)
        draw = ImageDraw.Draw(mask)
        for polygon in polygons:
            draw.polygon([tuple(p) for p in polygon["points"]], fill=255)
        masks[name] = np.asarray(mask) > 0
        cameras[name] = camera(geo["views"][name])
        # The full search volume must be in front of each camera.
        corners = np.array([[x,y,z] for x in bounds[:,0]
                            for y in bounds[:,1] for z in bounds[:,2]])
        project(*cameras[name], corners)
    keep = carve(points, cameras, masks)
    require(keep.any(), "empty_reconstruction", "Contornos não produziram volume comum na região.")
    require(keep.sum() <= 20000, "surface_budget",
            "Mais de 20000 voxels ocupados; aumente o voxel para este protótipo.")
    occupied = keep.reshape(tuple(counts))
    touches = bool(any(np.any(np.take(occupied, edge, axis=axis))
                       for axis in range(3) for edge in (0, -1)))
    selected = points[keep]
    output.mkdir(parents=True, exist_ok=False)
    try:
        np.savez_compressed(output / "volume.npz", occupied=occupied,
                            origin_lps_mm=bounds[0], voxel_size_mm=float(spacing))
        mesh = write_surface(output / "envelope.obj", occupied, bounds[0], spacing)
        metrics = {}
        for name in VIEWS:
            image = voxel_projection(selected, spacing, cameras[name],
                                     tuple(annotations["views"][name]["size"]))
            image.save(output / (name.lower() + "_reprojection.png"))
            predicted = np.asarray(image) > 0
            target = masks[name]
            union = np.logical_or(target, predicted).sum()
            metrics[name] = {"silhouette_iou": float(np.logical_and(target, predicted).sum()/union),
                             "target_coverage": float(np.logical_and(target, predicted).sum()/target.sum())}
        write_json(output / "reconstruction-report.json", {
            "schema_version": 1, "method": "voxel_center_silhouette_intersection_v1",
            "status": "roi_boundary_warning" if touches else "experimental_envelope_generated",
            "origin": case["data_origin"], "bone_label": config["bone"],
            "coordinate_system": "LPS_mm", "grid_shape": counts.tolist(),
            "voxel_size_mm": spacing, "occupied_voxels": int(keep.sum()),
            "envelope_volume_mm3": float(keep.sum()*spacing**3),
            "touches_roi_boundary": touches, "mesh": mesh, "reprojection": metrics,
            "mesh_sha256": digest((output / "envelope.obj").read_bytes()),
            "volume_sha256": digest((output / "volume.npz").read_bytes()),
            "manifest_sha256": digest(manifest.read_bytes()),
            "annotation_sha256": digest(annotation.read_bytes()),
            "geometry_sha256": digest(geometry.read_bytes()),
            "settings_sha256": digest(settings.read_bytes()),
            "clinical_use_validated": False, "physical_calibration_verified": False,
            "anatomical_shape_verified": False, "equivalent_to_ct": False,
            "anatomical_prior_used": False, "fracture_preservation_verified": False,
        })
        return output / "reconstruction-report.json"
    except Exception:
        shutil.rmtree(output)
        raise
