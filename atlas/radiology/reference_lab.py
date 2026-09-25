"""Synthetic reference, approximate DRRs and geometric baseline comparison."""

import shutil
from pathlib import Path

import numpy as np

from atlas.radiology.cases import require
from atlas.radiology.privacy import write_json
from atlas.radiology.reconstruction_lab import create_reconstruction_lab
from atlas.radiology.reference import audit_reference_splits, import_reference
from atlas.radiology.reference_benchmark import adapt_stage7_prediction, compare_reference
from atlas.radiology.reference_projection import create_projections


def create_reference_lab(output: Path):
    require(not output.exists(),"output_exists","Use uma pasta nova para o LAB.")
    output.mkdir(parents=True,exist_ok=False)
    try:
        create_reconstruction_lab(output / "baseline")
        indices = np.indices((28,28,28)).reshape(3,-1).T
        centers = -70+(indices+.5)*5
        mask = (((centers/np.array([20,30,45]))**2).sum(axis=1) <= 1).reshape(28,28,28)
        # Approximate test phantom: uniform material inside an ellipsoid, air outside.
        raw = output / "phantom.npz"
        np.savez_compressed(raw,hu=np.where(mask,1000,-1000).astype(np.int16),
                            reference_mask=mask,origin_lps_mm=np.array([-70.,-70.,-70.]),
                            spacing_mm=np.array([5.,5.,5.]))
        reference = import_reference(raw,output / "reference","synthetic-001","test",origin="synthetic")
        create_projections(reference,output / "baseline/geometry.json",output / "projections",step_mm=2.5)
        adapt_stage7_prediction(output / "baseline/result/volume.npz",output / "baseline-prediction.npz")
        compare_reference(reference,output / "baseline-prediction.npz",output / "baseline-comparison.json")
        write_json(output / "dataset-audit.json",audit_reference_splits([reference]))
        write_json(output / "lab-report.json",{
            "schema_version":1,"status":"synthetic_reference_lab_completed",
            "real_ct_used":False,"neural_model_trained":False,
            "neural_comparison_available":False,"clinical_use_validated":False,
            "missing_for_neural_comparison":["authorized_dataset","trained_model_predictions"],
        })
        return output / "lab-report.json"
    except Exception:
        shutil.rmtree(output)
        raise
