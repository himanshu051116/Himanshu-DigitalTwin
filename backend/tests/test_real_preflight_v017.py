"""Fail-closed real-cohort checks that cannot be satisfied by CSV headers alone."""
from pathlib import Path
import pandas as pd
import numpy as np
from scripts.preflight_data import audit_cgmacros, REFERENCE_CGMACROS


def _cohort(tmp_path: Path) -> tuple[Path, list[int]]:
    ids=[int(str(x).split('-')[-1]) for x in pd.read_csv(REFERENCE_CGMACROS)['person_id']]
    assert len(ids)==len(set(ids))==45
    stamps=pd.date_range('2026-01-01 00:00:00',periods=510,freq='5min')
    bio=[]
    for sid in ids:
        bio.append({'Subject':sid,'Age':40,'Gender':'M','BMI':27,'HbA1c':7.1,'Fasting Glucose':125})
        pd.DataFrame({'Timestamp':stamps,'Dexcom GL':110+np.sin(np.arange(510)),'HR':75,
                      'METs':12,'Carbs':0}).to_csv(tmp_path/f'CGMacros-{sid:03d}.csv',index=False)
    pd.DataFrame(bio).to_csv(tmp_path/'bio.csv',index=False)
    return tmp_path, ids


def test_full_structural_cohort_can_pass(tmp_path):
    path,_=_cohort(tmp_path)
    audit=audit_cgmacros(path)
    assert audit['ready_for_final_primary_training'] is True
    assert audit['subject_files']==45
    assert len(audit['subject_observation_counts'])==45
    assert audit['unusable_cgm_files']==[]


def test_duplicate_subject_file_rejected_even_if_unique_count_is_45(tmp_path):
    path,ids=_cohort(tmp_path)
    p=path/f'CGMacros-{ids[0]:03d}.csv'
    d=path/'copy';d.mkdir()
    (d/p.name).write_bytes(p.read_bytes())
    audit=audit_cgmacros(path)
    assert audit['subject_files']==45
    assert audit['ready_for_final_primary_training'] is False
    assert f'CGM-{ids[0]:03d}' in audit['duplicate_subject_files']


def test_blank_glucose_rejected_even_with_valid_headers(tmp_path):
    path,ids=_cohort(tmp_path)
    p=path/f'CGMacros-{ids[0]:03d}.csv'
    frame=pd.read_csv(p)
    frame['Dexcom GL']=np.nan
    frame.to_csv(p,index=False)
    audit=audit_cgmacros(path)
    assert audit['ready_for_final_primary_training'] is False
    assert len(audit['unusable_cgm_files'])==1


def test_duplicate_bio_rejected_and_unusual_filename_is_not_accepted(tmp_path):
    path,ids=_cohort(tmp_path)
    bio=pd.read_csv(path/'bio.csv')
    pd.concat([bio,bio.iloc[:1]],ignore_index=True).to_csv(path/'bio.csv',index=False)
    audit=audit_cgmacros(path)
    assert audit['duplicate_bio_subjects']==[f'CGM-{ids[0]:03d}']
    assert audit['ready_for_final_primary_training'] is False
    # Replacing one valid filename with a noncanonical alias cannot pass preflight.
    p=path/f'CGMacros-{ids[0]:03d}.csv'
    p.rename(path/f'CGMacros-{ids[0]:03d}-copy.csv')
    audit=audit_cgmacros(path)
    assert audit['unexpected_subject_csv_filenames']
    assert audit['ready_for_final_primary_training'] is False


def test_manifest_sha256_detects_modified_subject_data(tmp_path):
    import hashlib, json
    path,ids=_cohort(tmp_path)
    entries=[]
    for csv in sorted(path.glob('*.csv')):
        entries.append({'relative_path':csv.name,'bytes':csv.stat().st_size,
                        'sha256':hashlib.sha256(csv.read_bytes()).hexdigest()})
    (path/'csv_only_manifest.json').write_text(json.dumps({'file_sha256':entries}))
    audit=audit_cgmacros(path)
    assert audit['csv_only_manifest_integrity']=='VERIFIED'
    assert audit['ready_for_final_primary_training'] is True
    # Keep headers and row count valid, but alter real sensor values.
    file=path/f'CGMacros-{ids[0]:03d}.csv'
    raw=file.read_bytes()
    assert b'110.0' in raw
    file.write_bytes(raw.replace(b'110.0',b'111.0',1))
    result=audit_cgmacros(path)
    assert result['csv_only_manifest_integrity']=='FAILED'
    assert any(x['error']=='SHA-256 mismatch' for x in result['csv_only_manifest_errors'])
    assert result['ready_for_final_primary_training'] is False


def test_manifest_missing_subject_is_rejected(tmp_path):
    import hashlib,json
    path,_=_cohort(tmp_path)
    only=path/'bio.csv'
    (path/'csv_only_manifest.json').write_text(json.dumps({'file_sha256':[
        {'relative_path':only.name,'bytes':only.stat().st_size,
         'sha256':hashlib.sha256(only.read_bytes()).hexdigest()}
    ]}))
    result=audit_cgmacros(path)
    assert result['csv_only_manifest_integrity']=='FAILED'
    assert any('exactly cover' in x['error'] for x in result['csv_only_manifest_errors'])
    assert result['ready_for_final_primary_training'] is False
