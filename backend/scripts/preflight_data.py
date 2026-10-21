"""Fast structural preflight for real HimanshuDigitalTwin cohorts."""
from __future__ import annotations
import argparse, json, re, hashlib
from collections import Counter
from pathlib import Path
import pandas as pd
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.cgmacros import discover_subject_files, load_bio, normalize_subject_id
from app.shanghai import discover_shanghai_subject_files, load_shanghai_metadata

REFERENCE_CGMACROS=Path(__file__).resolve().parents[1]/'data'/'reference'/'cgmacros_dexcom_metadata.csv'

REQUIRED_CGMACROS_GROUPS={
    'timestamp':['Timestamp','timestamp','Date','date'],
    'cgm':['Dexcom GL','Dexcom','dexcom_gl','CGM','Libre GL','Libre','libre_gl'],
    'heart_rate':['HR','Heart Rate','heart_rate'],
    'activity':['Mets','METs','mets','Intensity'],
    'carbs':['Carbs','carbs','Carbohydrates'],
}

def _has_any(columns, aliases):
    c={str(x).strip().lower() for x in columns}
    return any(a.lower() in c for a in aliases)

def audit_cgmacros(root: str|Path) -> dict:
    root=Path(root); files=discover_subject_files(root)
    bios=[p for p in root.rglob('*.csv') if p.name.lower()=='bio.csv']
    bio=None; bio_ids=set()
    if bios:
        bio=load_bio(bios[0]); bio_ids=set(bio['subject_id'].dropna().astype(str))
    ids_by_path=[(normalize_subject_id(p.stem),p) for p in files]
    file_ids={sid for sid,_ in ids_by_path}
    duplicate_counts=Counter(sid for sid,_ in ids_by_path)
    duplicate_subject_files={sid:[str(p) for found,p in ids_by_path if found==sid]
                             for sid,count in sorted(duplicate_counts.items()) if count>1}
    unexpected_filenames=[str(p) for _,p in ids_by_path
                          if not re.fullmatch(r'CGMacros-\d{3}\.csv',p.name,re.I)]
    schema_fail=[]
    non_mets_subjects=[]
    unusable_cgm_files=[]
    subject_observation_counts={}
    # Headers alone are not evidence of real glucose measurements: require
    # sufficient distinct time-stamped, physiologically plausible observations.
    for sid,p in ids_by_path:
        cols=pd.read_csv(p,nrows=2).columns
        missing=[name for name,aliases in REQUIRED_CGMACROS_GROUPS.items() if not _has_any(cols,aliases)]
        if missing:
            schema_fail.append({'file':str(p),'missing':missing})
            continue
        if not _has_any(cols,['Mets','METs','mets']):
            non_mets_subjects.append(p.name)
        selected={str(c).strip().lower():c for c in cols}
        tcol=next(selected[a.lower()] for a in REQUIRED_CGMACROS_GROUPS['timestamp']
                  if a.lower() in selected)
        cgm_cols=[selected[a.lower()] for a in REQUIRED_CGMACROS_GROUPS['cgm']
                  if a.lower() in selected]
        # One must remain the preferred single CGM channel. Do not combine
        # interleaved Dexcom/Libre readings just to pass this audit.
        cgm_cols=list(dict.fromkeys(cgm_cols))
        sample=pd.read_csv(p,usecols=list(dict.fromkeys([tcol]+cgm_cols)),low_memory=False)
        timestamps=pd.to_datetime(sample[tcol],errors='coerce')
        valid_counts={c:int(((pd.to_numeric(sample[c],errors='coerce')>=30)
                              &(pd.to_numeric(sample[c],errors='coerce')<=450)
                              &timestamps.notna()).sum()) for c in cgm_cols}
        n_valid=max(valid_counts.values(),default=0)
        distinct_times=int(timestamps.nunique())
        subject_observation_counts[sid]={'best_single_channel_valid_observations':n_valid,
                                         'distinct_timestamps':distinct_times,
                                         'channels':valid_counts}
        if n_valid<500 or distinct_times<500:
            unusable_cgm_files.append({'file':str(p),'subject_id':sid,
                                       'valid_cgm_readings':n_valid,
                                       'distinct_timestamps':distinct_times})
    missing_bio=sorted(file_ids-bio_ids) if bios else sorted(file_ids)
    duplicate_bio_subjects=sorted(bio['subject_id'][bio['subject_id'].duplicated(keep=False)].unique().tolist()) if bio is not None else []
    label_ids=set(); label_counts={}
    if REFERENCE_CGMACROS.exists():
        ref=pd.read_csv(REFERENCE_CGMACROS)
        label_ids={normalize_subject_id(x) for x in ref['person_id'].dropna()}
        label_counts={str(k):int(v) for k,v in ref['diabetes_type'].value_counts().items()}
    missing_labels=sorted(file_ids-label_ids) if label_ids else sorted(file_ids)
    # Re-check the extracted bytes against the per-file manifest when a
    # selective range downloader created one. A CRC/checksum assertion made
    # at download time must not remain valid after the local data is edited.
    member_manifest=root/'csv_only_manifest.json'
    manifest_integrity='NOT_PROVIDED'
    manifest_errors=[]
    if member_manifest.is_file():
        try:
            manifest=json.loads(member_manifest.read_text())
            entries=manifest.get('file_sha256')
            if not isinstance(entries,list) or not entries:
                manifest_integrity='LEGACY_UNVERIFIED'
            else:
                manifest_integrity='VERIFIED'
                observed_files={p.resolve() for p in files+bios}
                recorded=set()
                for entry in entries:
                    name=entry.get('relative_path','')
                    candidate=(root/name).resolve()
                    if not candidate.is_relative_to(root.resolve()) or candidate in recorded:
                        manifest_errors.append({'file':name,'error':'invalid or duplicate manifest path'})
                        continue
                    recorded.add(candidate)
                    if not candidate.is_file() or candidate.stat().st_size != entry.get('bytes'):
                        manifest_errors.append({'file':name,'error':'missing or size mismatch'})
                        continue
                    digest=hashlib.sha256()
                    with candidate.open('rb') as stream:
                        for chunk in iter(lambda:stream.read(1024*1024),b''):
                            digest.update(chunk)
                    if digest.hexdigest()!=entry.get('sha256'):
                        manifest_errors.append({'file':name,'error':'SHA-256 mismatch'})
                if observed_files != recorded:
                    manifest_errors.append({'error':'manifest does not exactly cover 45 subject CSVs and bio.csv',
                                            'uncovered_files':len(observed_files-recorded)})
                if manifest_errors: manifest_integrity='FAILED'
        except (OSError,ValueError,TypeError) as exc:
            manifest_integrity='FAILED'
            manifest_errors.append({'error':type(exc).__name__})
    expected=45
    ready=(len(file_ids)==expected and len(files)==expected and len(bios)==1
           and not missing_bio and not duplicate_bio_subjects
           and not schema_fail and not missing_labels
           and not duplicate_subject_files and not unexpected_filenames
           and not unusable_cgm_files and not manifest_errors)
    return {
        'cohort':'CGMacros','expected_subjects':expected,'subject_files':len(file_ids),
        'bio_found':bool(bios),'bio_csv_files':len(bios),'bio_subjects':len(bio_ids),'subjects_missing_bio':missing_bio,
        'published_label_subjects':len(label_ids),'published_diabetes_type_counts':label_counts,'subjects_missing_published_label':missing_labels,
        'schema_failures':schema_fail,'activity_intensity_only_subjects':non_mets_subjects,
        'duplicate_subject_files':duplicate_subject_files,
        'unexpected_subject_csv_filenames':unexpected_filenames,
        'duplicate_bio_subjects':duplicate_bio_subjects,
        'unusable_cgm_files':unusable_cgm_files,
        'subject_observation_counts':subject_observation_counts,
        'csv_only_manifest_integrity':manifest_integrity,
        'csv_only_manifest_errors':manifest_errors,
        'ready_for_final_primary_training':ready,
        'note':'Final evidence requires the complete official 45-subject multimodal release and published diabetes-type labels.'
    }

def audit_shanghai(root: str|Path, metadata_path: str|Path) -> dict:
    files=discover_shanghai_subject_files(root); meta=load_shanghai_metadata(metadata_path)
    file_ids={f'SH-{int(p.stem)}' for p in files if p.stem.isdigit()}
    meta_ids=set(meta['subject_id'].astype(str))
    expected=100
    ready=(len(file_ids)==expected and len(meta_ids)>=expected and file_ids.issubset(meta_ids))
    return {'cohort':'ShanghaiT2DM','expected_subjects':expected,'subject_files':len(file_ids),
            'metadata_subjects':len(meta_ids),'metadata_missing_for_files':sorted(file_ids-meta_ids),
            'ready_for_external_validation':ready}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--cgmacros-dir'); ap.add_argument('--shanghai-dir'); ap.add_argument('--metadata'); ap.add_argument('--out')
    a=ap.parse_args(); report={}
    if a.cgmacros_dir: report['cgmacros']=audit_cgmacros(a.cgmacros_dir)
    if a.shanghai_dir:
        if not a.metadata: raise SystemExit('--metadata required with --shanghai-dir')
        report['shanghai']=audit_shanghai(a.shanghai_dir,a.metadata)
    text=json.dumps(report,indent=2,allow_nan=False); print(text)
    if a.out:
        p=Path(a.out); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text)
    failed=(a.cgmacros_dir and not report.get('cgmacros',{}).get('ready_for_final_primary_training')) or (a.shanghai_dir and not report.get('shanghai',{}).get('ready_for_external_validation'))
    if failed: raise SystemExit(2)

if __name__=='__main__': main()
