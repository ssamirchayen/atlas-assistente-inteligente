import json
import shutil
import subprocess
from pathlib import Path

import pytest

from atlas.radiology.cases import CaseError
from atlas.radiology.linked_viewer import build_linked_viewer, read_surface
from atlas.radiology.reconstruction_lab import create_reconstruction_lab


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
    root=tmp_path_factory.mktemp("linked") / "lab"
    create_reconstruction_lab(root)
    return root


def build(root,output):
    return build_linked_viewer(root / "case/case.json",root / "geometry.json",root / "result",output)


def test_offline_payload_and_no_overwrite(lab,tmp_path):
    path=build(lab,tmp_path / "viewer")
    text=path.read_text(encoding="utf-8")
    assert "__LINKED_DATA__" not in text and "__LINKED_MATH__" not in text
    assert "connect-src 'none'" in text
    assert text.count("data:image/png;base64,") == 3
    assert "pickImage" in text
    with pytest.raises(CaseError):
        build(lab,tmp_path / "viewer")


@pytest.mark.parametrize("fault",["mesh","case","geometry","legacy"])
def test_bindings(lab,tmp_path,fault):
    root=tmp_path / "lab"
    shutil.copytree(lab,root)
    if fault == "mesh":
        path=root / "result/envelope.obj"
        path.write_bytes(path.read_bytes()+b"#changed\n")
    elif fault == "legacy":
        path=root / "result/reconstruction-report.json"
        data=json.loads(path.read_text())
        del data["mesh_sha256"]
        path.write_text(json.dumps(data))
    else:
        path=root / ("case/case.json" if fault == "case" else "geometry.json")
        path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(CaseError):
        build(root,tmp_path / "viewer")
    assert not (tmp_path / "viewer").exists()


@pytest.mark.parametrize("obj",[
    "v nan 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n",
    "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 9\n",
    "v 0 0 0\nv 1 0 0\nv 2 0 0\nf 1 2 3\n",
    "mtllib ../private.txt\n",
])
def test_bad_mesh(tmp_path,obj):
    path=tmp_path / "mesh.obj"
    path.write_text(obj)
    with pytest.raises(CaseError):
        read_surface(path)


def test_cli(lab,tmp_path):
    from atlas.radiology.__main__ import main
    assert main(["linked-viewer",str(lab / "case/case.json"),"--geometry",str(lab / "geometry.json"),
                 "--result",str(lab / "result"),"--output",str(tmp_path / "viewer")]) == 0


def test_javascript_projection_math():
    node=shutil.which("node")
    if not node:
        pytest.skip("Node indisponível: teste matemático JS opcional.")
    root=Path(__file__).resolve().parents[2]
    completed=subprocess.run([node,str(root / "tools/radiology_linked_math_test.cjs")],
                             capture_output=True,text=True,timeout=15)
    assert completed.returncode == 0, completed.stderr
