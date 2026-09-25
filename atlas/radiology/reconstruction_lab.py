"""Analytic ellipsoid silhouettes: no patient data, radiographs or DRRs."""

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from atlas.radiology.annotations import annotation_context
from atlas.radiology.cases import require
from atlas.radiology.geometry import camera, create_geometry_demo, project
from atlas.radiology.privacy import write_json
from atlas.radiology.reconstruction import convex_hull, reconstruct
from atlas.radiology.workspace import import_case


def create_reconstruction_lab(output: Path):
    require(not output.exists(), "output_exists", "Use uma pasta nova para o LAB.")
    output.mkdir(parents=True, exist_ok=False)
    try:
        geometry = output / "geometry.json"
        temporary = output / "geometry-template.json"
        create_geometry_demo(temporary)
        data = json.loads(temporary.read_text())
        # Eight independent known calibration landmarks retained from Etapa 5.
        for spec in data["views"].values():
            spec["K"][:2] = (np.asarray(spec["K"][:2])/4).tolist()
            spec["observed_px"] = (np.asarray(spec["observed_px"])/4).tolist()
            spec["image_size"] = [256, 256]
        write_json(geometry, data)
        temporary.unlink()
        surface = np.array([[20*np.sin(theta)*np.cos(phi),
                             30*np.sin(theta)*np.sin(phi), 45*np.cos(theta)]
                            for theta in np.linspace(0, np.pi, 25)
                            for phi in np.linspace(0, 2*np.pi, 60, endpoint=False)])
        sources, polygons = {}, {}
        for name, spec in data["views"].items():
            outline = convex_hull(project(*camera(spec), surface))
            polygons[name] = [list(p) for p in outline]
            image = Image.new("L", (256, 256), 0)
            ImageDraw.Draw(image).polygon(outline, fill=220)
            path = output / (name.lower()+".png")
            image.save(path)
            sources[name] = path
        manifest = import_case(sources, output / "case", "L", "synthetic")
        annotation, _ = annotation_context(manifest)
        for name, points in polygons.items():
            annotation["views"][name]["polygons"] = [{"bone": "tibia", "points": points}]
        annotation_path = output / "annotations.json"
        write_json(annotation_path, annotation)
        settings = output / "reconstruction-settings.json"
        write_json(settings, {"schema_version": 1, "bone": "tibia",
                             "bounds_lps_mm": [[-70,-70,-70],[70,70,70]],
                             "voxel_size_mm": 5})
        result = reconstruct(manifest, annotation_path, geometry, settings, output / "result")
        with np.load(output / "result/volume.npz", allow_pickle=False) as volume:
            occupied = volume["occupied"]
            indices = np.indices(occupied.shape).reshape(3, -1).T
            centers = -70 + (indices + .5)*5
            truth = ((centers/np.array([20,30,45]))**2).sum(axis=1) <= 1
            flat = occupied.ravel()
            dice = float(2*np.logical_and(flat, truth).sum()/(flat.sum()+truth.sum()))
        write_json(output / "synthetic-comparison.json", {
            "object": "analytic_ellipsoid_not_bone", "radii_mm": [20,30,45],
            "dice_vs_ellipsoid_on_same_grid": dice,
            "independent_clinical_validation": False,
            "note": "Calibration and silhouette generation share the camera model.",
        })
        return result
    except Exception:
        shutil.rmtree(output)
        raise
