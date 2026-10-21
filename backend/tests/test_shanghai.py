from pathlib import Path
import pandas as pd
from app.shanghai import load_shanghai_metadata, load_shanghai_subject, attach_metadata, cohort_profile

ROOT=Path(__file__).resolve().parents[1]

def test_real_metadata_profile():
    m=load_shanghai_metadata(ROOT/'data/reference/shanghai_t2dm_metadata.csv')
    p=cohort_profile(m)
    assert p['subjects']==100
    assert p['total_cgm_records_reported']==112462
    assert p['hba1c']['available']==92
    assert p['data_quality_flags']['missing_hba1c_subjects']


def test_subject_loader_preserves_quality_and_identity(tmp_path):
    f=tmp_path/'2000.csv'
    pd.DataFrame({
        'timestamp':['2024-01-01 00:00','2024-01-01 00:15','2024-01-01 00:45','2024-01-01 01:15'],
        'glucose_value_mg_dl':[120,130,150,170],
    }).to_csv(f,index=False)
    x=load_shanghai_subject(f)
    assert x['subject_id'].eq('SH-2000').all()
    # 00:30 is one missing interval and may be interpolated; 01:00 is another isolated gap.
    assert 'IMPUTED' in set(x['quality'])
    m=load_shanghai_metadata(ROOT/'data/reference/shanghai_t2dm_metadata.csv')
    joined=attach_metadata(x,m)
    assert joined['age'].notna().all()
    assert joined['source_subject_id'].eq(2000).all()
