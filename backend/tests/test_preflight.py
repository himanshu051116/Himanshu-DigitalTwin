from pathlib import Path
import pandas as pd
from scripts.preflight_data import audit_cgmacros


def test_preflight_rejects_incomplete_primary_cohort(tmp_path: Path):
    pd.DataFrame([{'Subject':1,'Age':40,'Gender':'M','BMI':28,'HbA1c':7.1,'Fasting Glucose':130}]).to_csv(tmp_path/'bio.csv',index=False)
    pd.DataFrame({
        'Timestamp':['2026-01-01 00:00'],'Dexcom GL':[120],'HR':[70],'Mets':[12],'Carbs':[0]
    }).to_csv(tmp_path/'CGMacros-001.csv',index=False)
    r=audit_cgmacros(tmp_path)
    assert r['subject_files']==1
    assert r['ready_for_final_primary_training'] is False
