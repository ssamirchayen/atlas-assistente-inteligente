"""CPU midpoint ray integration for a simplified monoenergetic DRR model."""

import math
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from atlas.radiology.cases import require
from atlas.radiology.geometry import camera, validate_geometry
from atlas.radiology.privacy import VIEWS, digest, read_json, write_json
from atlas.radiology.reference import read_reference


def integrate_rays(hu, lower, spacing, source, directions, step_mm, water_mu):
    upper = lower + np.asarray(hu.shape)*spacing
    require(np.isfinite(directions).all()
            and np.allclose(np.linalg.norm(directions, axis=1), 1),
            "ray_direction", "Direções dos raios devem ser unitárias.")
    n = len(directions)
    enter = np.zeros(n)
    leave = np.full(n, np.inf)
    valid = np.ones(n, dtype=bool)
    for axis in range(3):
        parallel = np.abs(directions[:, axis]) < 1e-12
        valid &= ~parallel | ((source[axis] >= lower[axis]) & (source[axis] < upper[axis]))
        near = np.full(n, -np.inf)
        far = np.full(n, np.inf)
        moving = ~parallel
        first = (lower[axis]-source[axis])/directions[moving, axis]
        last = (upper[axis]-source[axis])/directions[moving, axis]
        near[moving], far[moving] = np.minimum(first,last), np.maximum(first,last)
        enter = np.maximum(enter, near)
        leave = np.minimum(leave, far)
    valid &= (leave > enter) & np.isfinite(leave)
    lengths = np.where(valid, leave-enter, 0)
    steps = np.ceil(lengths/step_mm).astype(int)
    require((steps <= 1024).all(), "ray_budget", "Mais de 1024 amostras por raio.")
    result = np.zeros(n, dtype=np.float64)
    for start in range(0, n, 256):
        stop = min(start+256, n)
        count = steps[start:stop]
        max_count = int(count.max())
        if not max_count:
            continue
        delta = lengths[start:stop]/np.maximum(count,1)
        samples = np.arange(max_count)[None,:]
        inside = samples < count[:,None]
        distance = enter[start:stop,None] + (samples+.5)*delta[:,None]
        xyz = source + distance[:,:,None]*directions[start:stop,None,:]
        index = np.floor((xyz-lower)/spacing).astype(int)
        index = np.clip(index,0,np.asarray(hu.shape)-1)
        values = hu[index[:,:,0],index[:,:,1],index[:,:,2]].astype(float)
        mu = np.maximum(1+values/1000,0)*water_mu
        result[start:stop] = (mu*inside).sum(axis=1)*delta
    return result


def create_projections(reference: Path, geometry: Path, output: Path,
                       step_mm=1.0, water_mu=.02):
    meta, arrays = read_reference(reference)
    require(type(step_mm) in (int,float) and math.isfinite(step_mm) and .25 <= step_mm <= 10
            and type(water_mu) in (int,float) and math.isfinite(water_mu) and 0 < water_mu <= 1,
            "projection_parameters", "Passo ou coeficiente de atenuação inválidos.")
    geo = read_json(geometry)
    require(isinstance(geo,dict) and geo.get("origin") == "synthetic",
            "virtual_geometry", "Projeções requerem contrato de câmeras virtuais synthetic.")
    require(validate_geometry(geometry)["status"] == "geometry_consistent",
            "projection_geometry", "Geometria virtual inconsistente.")
    require(all(max(geo["views"][name]["image_size"]) <= 256 for name in VIEWS),
            "detector_budget", "Projeção limitada a 256 pixels por eixo.")
    require(not output.exists(), "output_exists", "Use uma pasta nova para projeções.")
    output.mkdir(parents=True, exist_ok=False)
    try:
        results = {}
        for name in VIEWS:
            spec = geo["views"][name]
            k,r,source = camera(spec)
            width,height = spec["image_size"]
            v,u = np.indices((height,width))
            pixels = np.stack((u.ravel(),v.ravel(),np.ones(width*height)),axis=1)
            directions = (r.T @ np.linalg.solve(k,pixels.T)).T
            directions /= np.linalg.norm(directions,axis=1)[:,None]
            integral = integrate_rays(arrays["hu"],arrays["origin_lps_mm"],
                                      arrays["spacing_mm"],source,directions,step_mm,water_mu)
            integral = integral.reshape(height,width)
            transmission = np.exp(-integral)
            np.savez_compressed(output / (name.lower()+".npz"),
                                line_integral=integral.astype(np.float32),
                                transmission=transmission.astype(np.float32))
            # Fixed scale: air white, attenuating matter dark. No per-view normalization.
            Image.fromarray(np.rint(transmission*255).astype(np.uint8)).save(
                output / (name.lower()+".png"))
            results[name] = {"max_line_integral":float(integral.max()),
                             "min_transmission":float(transmission.min()),
                             "pixels":width*height,
                             "npz_sha256":digest((output / (name.lower()+".npz")).read_bytes())}
        write_json(output / "projection-report.json", {
            "schema_version":1,"method":"midpoint_nearest_voxel_monoenergetic_v1",
            "reference_sha256":meta["volume_sha256"],"origin":meta["origin"],
            "geometry_sha256":digest(geometry.read_bytes()),"step_mm":step_mm,
            "water_mu_per_mm":water_mu,"views":results,
            "scatter_modeled":False,"detector_noise_modeled":False,
            "spectral_calibration_verified":False,"clinical_use_validated":False,
        })
        return output / "projection-report.json"
    except Exception:
        shutil.rmtree(output)
        raise
