import json
from zipfile import ZipFile

import numpy as np
import pytest

from atlas.radiology.cases import CaseError
from atlas.radiology.reference import import_reference, read_reference, audit_reference_splits, load_arrays
from atlas.radiology.reference_benchmark import compare_reference
from atlas.radiology.reference_lab import create_reference_lab
from atlas.radiology.reference_projection import integrate_rays


@pytest.fixture
def raw(tmp_path):
    path = tmp_path / "volume.npz"
    np.savez_compressed(path,hu=np.zeros((4,4,4),dtype=np.int16),
                        reference_mask=np.ones((4,4,4),dtype=bool),
                        origin_lps_mm=np.zeros(3),spacing_mm=np.ones(3))
    return path


def test_import_requires_research_attestations(raw,tmp_path):
    with pytest.raises(CaseError):
        import_reference(raw,tmp_path / "ref","S001","test")
    manifest = import_reference(raw,tmp_path / "ref","S001","test",authorized=True,privacy_reviewed=True)
    meta,arrays = read_reference(manifest)
    assert meta["origin"] == "research"
    assert arrays["hu"].shape == (4,4,4)


def test_checksum(raw,tmp_path):
    manifest = import_reference(raw,tmp_path / "ref","S001","test",origin="synthetic")
    path = manifest.parent / "reference.npz"
    with ZipFile(path,"a") as archive:
        archive.comment = b"modified"
    with pytest.raises(CaseError) as exc:
        read_reference(manifest)
    assert exc.value.code == "reference_checksum"


@pytest.mark.parametrize("fault",["object","extra","nan","shape","hu","mask","spacing"])
def test_bad_volumes(raw,tmp_path,fault):
    with np.load(raw) as source:
        data = dict(source)
    if fault == "object":
        data["hu"] = np.array([object()],dtype=object)
    elif fault == "extra":
        data["patient_name"] = np.array([1])
    elif fault == "nan":
        data["hu"] = np.full((4,4,4),np.nan)
    elif fault == "shape":
        data["reference_mask"] = np.ones((2,2,2),dtype=bool)
    elif fault == "hu":
        data["hu"] = np.full((4,4,4),-5000)
    elif fault == "mask":
        data["reference_mask"] = np.full((4,4,4),2)
    else:
        data["spacing_mm"] = np.zeros(3)
    np.savez_compressed(raw,**data)
    with pytest.raises(CaseError):
        import_reference(raw,tmp_path / "bad","S001","test",origin="synthetic")


def test_header_allocation_budget(tmp_path):
    import io
    stream = io.BytesIO()
    np.lib.format.write_array_header_1_0(stream,{"descr":"<f8","fortran_order":False,"shape":(10**9,)})
    path = tmp_path / "bad.npz"
    with ZipFile(path,"w") as archive:
        archive.writestr("hu.npy",stream.getvalue())
    with pytest.raises(CaseError):
        load_arrays(path,{"hu"})


@pytest.mark.parametrize("same_subject",[True,False])
def test_split_leakage(raw,tmp_path,same_subject):
    first = import_reference(raw,tmp_path / "train","S001","train",origin="synthetic")
    second = import_reference(raw,tmp_path / "test","S001" if same_subject else "S002","test",origin="synthetic")
    with pytest.raises(CaseError) as exc:
        audit_reference_splits([first,second])
    assert exc.value.code == ("subject_leakage" if same_subject else "volume_leakage")


def test_distinct_subjects_and_volumes_pass(raw,tmp_path):
    first = import_reference(raw,tmp_path / "train","S001","train",origin="synthetic")
    with np.load(raw) as source:
        data = dict(source)
    data["hu"] += 10
    np.savez_compressed(raw,**data)
    second = import_reference(raw,tmp_path / "test","S002","test",origin="synthetic")
    report = audit_reference_splits([first,second])
    assert report["counts"] == {"train":1,"validation":0,"test":1}


@pytest.mark.parametrize("empty",[False,True])
def test_comparison(raw,tmp_path,empty):
    ref = import_reference(raw,tmp_path / "ref","S001","test",origin="synthetic")
    pred = tmp_path / "prediction.npz"
    np.savez_compressed(pred,prediction=np.full((4,4,4),not empty,dtype=bool),
                        origin_lps_mm=np.zeros(3),spacing_mm=np.ones(3))
    result = compare_reference(ref,pred,tmp_path / "report.json")
    assert result["dice"] == (0 if empty else 1)
    assert result["precision"] == (None if empty else 1)


def test_grid_mismatch_rejected(raw,tmp_path):
    ref = import_reference(raw,tmp_path / "ref","S001","test",origin="synthetic")
    pred = tmp_path / "prediction.npz"
    np.savez_compressed(pred,prediction=np.ones((4,4,4),dtype=bool),
                        origin_lps_mm=np.ones(3),spacing_mm=np.ones(3))
    with pytest.raises(CaseError):
        compare_reference(ref,pred,tmp_path / "report.json")


def test_ray_integral_analytic_slab():
    result = integrate_rays(np.zeros((4,4,4)),np.zeros(3),np.ones(3),
                            np.array([-10.,2.,2.]),np.array([[1.,0.,0.],[-1.,0.,0.]]),.7,.02)
    np.testing.assert_allclose(result,[.08,0],atol=1e-12)
    np.testing.assert_allclose(np.exp(-result)[0],np.exp(-.08))


def test_parallel_ray_misses_box():
    result = integrate_rays(np.zeros((4,4,4)),np.zeros(3),np.ones(3),
                            np.array([-10.,5.,2.]),np.array([[1.,0.,0.]]),1,.02)
    assert result[0] == 0


def test_lab(tmp_path):
    root = tmp_path / "lab"
    report = json.loads(create_reference_lab(root).read_text())
    assert not report["real_ct_used"] and not report["neural_model_trained"]
    comparison = json.loads((root / "baseline-comparison.json").read_text())
    assert .8 < comparison["dice"] < .9
    with np.load(root / "projections/ap.npz",allow_pickle=False) as images:
        assert images["transmission"].min() < 1
        assert images["transmission"].max() == 1
        assert np.isfinite(images["line_integral"]).all()


def test_cli_import_and_no_overwrite(raw,tmp_path):
    from atlas.radiology.__main__ import main
    args = ["reference-import",str(raw),"--subject","S001","--split","test",
            "--authorized","--privacy-reviewed","--output",str(tmp_path / "ref")]
    assert main(args) == 0
    assert main(args) == 1
