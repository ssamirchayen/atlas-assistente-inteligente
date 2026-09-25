"""Offline research interchange; no clinical approval or network connection."""

import shutil
import tempfile
from pathlib import Path

import numpy as np

from atlas.radiology.cases import require
from atlas.radiology.linked_viewer import read_surface
from atlas.radiology.privacy import digest, read_json, write_json
from atlas.radiology.reconstruction import reconstruct
from atlas.radiology.uncertainty import assess


def write_stl(path, vertices, faces, label):
    """ASCII STL, preserving coordinates and winding; units live in manifest."""
    triangles = np.asarray(vertices, dtype=float)[np.asarray(faces, dtype=int)]
    normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    require(np.isfinite(triangles).all() and (lengths > 1e-12).all(),
            "export_mesh", "Triângulos inválidos.")
    normals /= lengths[:, None]
    with path.open("x", encoding="ascii", newline="\n") as stream:
        stream.write(f"solid {label}\n")
        for normal, triangle in zip(normals, triangles, strict=True):
            stream.write("  facet normal " + " ".join(format(x, ".17g") for x in normal) + "\n    outer loop\n")
            for vertex in triangle:
                stream.write("      vertex " + " ".join(format(x, ".17g") for x in vertex) + "\n")
            stream.write("    endloop\n  endfacet\n")
        stream.write(f"endsolid {label}\n")


def export_bundle(manifest, annotation, geometry, settings, output, diagnostic=False):
    require(type(diagnostic) is bool, "export_mode", "Modo inválido.")
    require(not output.exists(), "output_exists", "Use uma pasta nova para exportação.")
    sources = dict(zip(("manifest", "annotation", "geometry", "settings"),
                       (manifest, annotation, geometry, settings), strict=True))
    initial = {name: digest(path.read_bytes()) for name, path in sources.items()}
    with tempfile.TemporaryDirectory(prefix="atlas-export-") as temp:
        root = Path(temp)
        # Never trust a manually edited assessment or stale result folder.
        assessment = assess(manifest, annotation, geometry, settings, root / "assessment")
        rejected = bool(assessment["reasons"])
        include_mesh = not rejected or diagnostic
        reconstruction = None
        if include_mesh:
            reconstruction = read_json(reconstruct(manifest, annotation, geometry,
                                                   settings, root / "reconstruction"))
        current = {name: digest(path.read_bytes()) for name, path in sources.items()}
        require(initial == current == assessment["inputs_sha256"], "export_binding",
                "Entradas mudaram durante a exportação.")
        if reconstruction:
            require(all(reconstruction[name+"_sha256"] == value for name, value in initial.items()),
                    "export_binding", "Reconstrução não corresponde à avaliação.")
        output.mkdir(parents=True, exist_ok=False)
        try:
            shutil.copyfile(root / "assessment/assessment.json", output / "assessment.json")
            state = "blocked" if rejected and not diagnostic else (
                "rejected_diagnostic_only" if rejected else "research_review_required")
            if include_mesh:
                raw, vertices, faces = read_surface(root / "reconstruction/envelope.obj")
                require(digest(raw) == reconstruction["mesh_sha256"], "export_integrity",
                        "Malha não corresponde ao relatório.")
                prefix = "REJECTED" if rejected else "UNVALIDATED"
                (output / f"{prefix}_envelope.obj").write_bytes(
                    f"# {prefix}; research only; LPS mm; no clinical approval\n".encode("ascii") + raw)
                write_stl(output / f"{prefix}_envelope.stl", vertices, faces, prefix+"_LPS_mm")
                shutil.copyfile(root / "assessment/sensitivity.npz", output / "sensitivity.npz")
                shutil.copyfile(root / "reconstruction/reconstruction-report.json",
                                output / "reconstruction-report.json")
            (output / "README.txt").write_text(
                f"ATLAS RESEARCH EXPORT\nState: {state}\n"
                "No clinical approval. Not CT. Not for diagnosis or surgical planning.\n"
                "Coordinates: LPS, millimeters. STL/OBJ consumers may ignore units.\n"
                "Do not separate meshes from this manifest and assessment.\n"
                "Hashes detect accidental modification; they are not signatures.\n"
                "No original radiographs included. Geometry may still be sensitive research data.\n",
                encoding="utf-8")
            report = {
                "schema_version": 1, "contract": "atlas_radiology_research_bundle_v1",
                "status": state, "mesh_included": include_mesh,
                "assessment_status": assessment["status"], "reasons": assessment["reasons"],
                "units": "mm", "coordinate_system": "LPS",
                "axes": {"x": "left", "y": "posterior", "z": "superior"},
                "clinical_use_validated": False, "approved": False,
                "inputs_sha256": initial,
                "files": {p.name: {"sha256": digest(p.read_bytes()), "bytes": p.stat().st_size}
                          for p in sorted(output.iterdir())},
            }
            write_json(output / "bundle.json", report)
        except Exception:
            shutil.rmtree(output)
            raise
        return report
