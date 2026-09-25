"""Compare binary model outputs on an identical, explicit reference grid."""

from pathlib import Path

import numpy as np

from atlas.radiology.cases import require
from atlas.radiology.privacy import digest, write_json
from atlas.radiology.reference import check_grid, load_arrays, read_reference


def compare_reference(reference: Path, prediction: Path, output: Path):
    meta, truth = read_reference(reference)
    arrays = load_arrays(prediction, {"prediction", "origin_lps_mm", "spacing_mm"})
    check_grid(arrays,"prediction")
    pred = arrays["prediction"]
    target = truth["reference_mask"].astype(bool)
    require(pred.dtype.kind in "biu" and np.isin(pred,[0,1]).all(),
            "prediction_mask","Predição deve ser máscara binária; limiarize externamente.")
    require(pred.shape == target.shape
            and np.array_equal(arrays["origin_lps_mm"],truth["origin_lps_mm"])
            and np.array_equal(arrays["spacing_mm"],truth["spacing_mm"]),
            "prediction_grid","Grades diferentes: sem registro ou reamostragem automática.")
    pred = pred.astype(bool)
    tp = int(np.logical_and(pred,target).sum())
    fp = int(np.logical_and(pred,~target).sum())
    fn = int(np.logical_and(~pred,target).sum())
    voxel_volume = float(np.prod(truth["spacing_mm"]))
    result = {"schema_version":1,"status":"comparison_computed",
              "origin":meta["origin"],"split":meta["split"],
              "reference_sha256":meta["volume_sha256"],
              "prediction_sha256":digest(prediction.read_bytes()),
              "dice":2*tp/(2*tp+fp+fn),"iou":tp/(tp+fp+fn),
              "recall":tp/(tp+fn),"precision":tp/(tp+fp) if tp+fp else None,
              "false_positive_voxels":fp,"false_negative_voxels":fn,
              "reference_volume_mm3":float(target.sum()*voxel_volume),
              "predicted_volume_mm3":float(pred.sum()*voxel_volume),
              "signed_volume_error_mm3":float((int(pred.sum())-int(target.sum()))*voxel_volume),
              "model_identity_verified":False,"clinical_use_validated":False}
    write_json(output,result)
    return result


def adapt_stage7_prediction(volume: Path, output: Path):
    arrays = load_arrays(volume,{"occupied","origin_lps_mm","voxel_size_mm"})
    require(arrays["voxel_size_mm"].shape == (),"prediction_grid","Voxel deve ser escalar.")
    result = {"prediction":arrays["occupied"],"origin_lps_mm":arrays["origin_lps_mm"],
              "spacing_mm":np.repeat(arrays["voxel_size_mm"],3)}
    check_grid(result,"prediction")
    require(result["prediction"].dtype == np.bool_,"prediction_mask","Ocupação deve ser booleana.")
    with output.open("xb") as stream:
        np.savez_compressed(stream,**result)
