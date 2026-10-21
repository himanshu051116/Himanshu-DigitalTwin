from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

META_RENAME = {
    'person_id':'subject_id',
    'hba1c_%':'hba1c',
    'average_glucose_level_mg_dl':'mean_glucose',
    'glucose_level_record_count':'record_count',
    'count_days_with_CGM_data':'days_with_cgm',
}


def load_shanghai_metadata(path: str | Path) -> pd.DataFrame:
    """Load the harmonized ShanghaiT2DM metadata table.

    Keeps the original participant identifier and adds a stable HDT-prefixed ID for UI use.
    Missing HbA1c is preserved rather than silently imputed.
    """
    df = pd.read_csv(path)
    df = df.rename(columns=META_RENAME)
    required = {'subject_id','age','gender','hba1c','mean_glucose','record_count','days_with_cgm'}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f'Missing Shanghai metadata columns: {sorted(missing)}')
    for col in ['age','hba1c','mean_glucose','record_count','days_with_cgm']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['source_subject_id'] = df['subject_id'].astype('Int64')
    df['subject_id'] = df['source_subject_id'].map(lambda x: f'SH-{int(x)}' if pd.notna(x) else pd.NA)
    return df


def discover_shanghai_subject_files(root: str | Path) -> list[Path]:
    root = Path(root)
    files = []
    for p in root.rglob('*.csv'):
        stem = p.stem.strip()
        if stem.isdigit() and 2000 <= int(stem) <= 2099:
            files.append(p)
    return sorted(files, key=lambda p: int(p.stem))


def load_shanghai_subject(path: str | Path, resample: str = '15min') -> pd.DataFrame:
    """Load one harmonized ShanghaiT2DM CGM series from Glucose-ML.

    Expected columns: timestamp, glucose_value_mg_dl.
    Short gaps (one interval) are interpolated but explicitly marked IMPUTED.
    Longer gaps remain MISSING and are not fabricated.
    """
    p = Path(path)
    raw = pd.read_csv(p)
    aliases = {str(c).strip().lower(): c for c in raw.columns}
    if 'timestamp' not in aliases or 'glucose_value_mg_dl' not in aliases:
        raise ValueError(f'{p.name}: expected timestamp and glucose_value_mg_dl columns')
    ts = pd.to_datetime(raw[aliases['timestamp']], errors='coerce')
    glucose = pd.to_numeric(raw[aliases['glucose_value_mg_dl']], errors='coerce')
    out = pd.DataFrame({'timestamp': ts, 'glucose': glucose}).dropna(subset=['timestamp']).sort_values('timestamp')
    # Label measurements at the end of their bucket, matching CGMacros and
    # preventing future samples being represented at the start of an interval.
    out = out.drop_duplicates('timestamp').set_index('timestamp').resample(resample,label='right',closed='right').mean()
    missing_before = out['glucose'].isna()
    out['glucose'] = out['glucose'].interpolate(limit=1, limit_area='inside')
    still_missing = out['glucose'].isna()
    out['quality'] = np.where(still_missing, 'MISSING', np.where(missing_before, 'IMPUTED', 'VALID'))
    out = out.reset_index()
    out['subject_id'] = f'SH-{int(p.stem)}' if p.stem.isdigit() else p.stem
    return out


def attach_metadata(cgm: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    """Join only metadata belonging to the same Shanghai subject."""
    return cgm.merge(metadata, on='subject_id', how='left', validate='many_to_one')


def cohort_profile(metadata: pd.DataFrame) -> dict:
    h = metadata['hba1c']
    g = metadata['mean_glucose']
    return {
        'subjects': int(metadata['subject_id'].nunique()),
        'age': {'min': float(metadata['age'].min()), 'median': float(metadata['age'].median()), 'max': float(metadata['age'].max())},
        'gender_counts': {str(k): int(v) for k, v in metadata['gender'].value_counts(dropna=False).items()},
        'hba1c': {'available': int(h.notna().sum()), 'missing': int(h.isna().sum()), 'mean': float(h.mean()), 'median': float(h.median())},
        'mean_glucose_mg_dl': {'min': float(g.min()), 'median': float(g.median()), 'mean': float(g.mean()), 'max': float(g.max())},
        'total_cgm_records_reported': int(metadata['record_count'].sum()),
        'days_with_cgm': {'median': float(metadata['days_with_cgm'].median()), 'max': int(metadata['days_with_cgm'].max())},
        'data_quality_flags': {
            'missing_hba1c_subjects': metadata.loc[metadata['hba1c'].isna(), 'subject_id'].tolist(),
            'mean_glucose_below_70_subjects': metadata.loc[metadata['mean_glucose'] < 70, 'subject_id'].tolist(),
            'mean_glucose_above_200_subjects': metadata.loc[metadata['mean_glucose'] > 200, 'subject_id'].tolist(),
        },
    }
