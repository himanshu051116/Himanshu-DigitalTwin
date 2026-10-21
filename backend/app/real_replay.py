from __future__ import annotations
from pathlib import Path
import math
import pandas as pd

from .shanghai import discover_shanghai_subject_files, load_shanghai_subject, load_shanghai_metadata
from .cgmacros import discover_subject_files, load_cgmacros_subject, load_bio, normalize_subject_id


def _none_if_nan(value):
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, 'item'):
        try:
            return value.item()
        except Exception:
            return value
    return value


def find_shanghai_file(root: str | Path, subject_id: str | int) -> Path:
    digits = ''.join(ch for ch in str(subject_id) if ch.isdigit())
    if not digits:
        raise FileNotFoundError(f'Invalid Shanghai subject ID: {subject_id}')
    wanted = int(digits)
    for p in discover_shanghai_subject_files(root):
        if p.stem.isdigit() and int(p.stem) == wanted:
            return p
    raise FileNotFoundError(f'Shanghai subject {wanted} not found under {root}')


def build_shanghai_replay(subject_file: str | Path, metadata_file: str | Path) -> tuple[dict, list[dict], int]:
    p = Path(subject_file)
    cgm = load_shanghai_subject(p)
    metadata = load_shanghai_metadata(metadata_file)
    pid = f'SH-{int(p.stem)}'
    row = metadata.loc[metadata['subject_id'] == pid]
    if row.empty:
        raise ValueError(f'Metadata not found for {pid}')
    row = row.iloc[0]
    profile = {
        'patient_id': pid,
        'source_subject_id': int(row['source_subject_id']),
        'data_source': 'ShanghaiT2DM',
        'age': int(row['age']) if pd.notna(row['age']) else None,
        'sex': _none_if_nan(row['gender']),
        'bmi': None,
        'hba1c': _none_if_nan(row['hba1c']),
        'fasting_glucose': None,
        'phenotype_note': 'Shanghai harmonized replay: age/sex/HbA1c available; BMI and fasting glucose are not fabricated.',
    }
    stream = []
    for r in cgm.itertuples(index=False):
        stream.append({
            'timestamp': pd.Timestamp(r.timestamp).isoformat(),
            'glucose': _none_if_nan(r.glucose),
            'truth_glucose': _none_if_nan(r.glucose),
            'heart_rate': None,
            'steps_5m': None,
            'activity': None,
            'carbs_active_g': None,
            'minutes_since_meal': None,
            'quality': r.quality,
            'provenance': {
                'stream': 'real-research-replay',
                'dataset': 'ShanghaiT2DM',
                'subject_id': pid,
                'glucose': 'harmonized ShanghaiT2DM CGM',
                'activity': 'not available in harmonized replay',
                'meal': 'not available in harmonized replay',
            },
        })
    # Drop leading truly-missing rows; never invent the first observation.
    while stream and stream[0]['glucose'] is None:
        stream.pop(0)
    if not stream:
        raise ValueError(f'No usable CGM observations for {pid}')
    return profile, stream, 15


def find_cgmacros_file(root: str | Path, subject_id: str | int) -> Path:
    wanted = normalize_subject_id(subject_id)
    for p in discover_subject_files(root):
        sid = normalize_subject_id(p.stem)
        if sid == wanted:
            return p
    raise FileNotFoundError(f'CGMacros subject {wanted} not found under {root}')


def _find_bio(root: str | Path) -> Path:
    candidates = [p for p in Path(root).rglob('*.csv') if p.name.lower() == 'bio.csv']
    if not candidates:
        raise FileNotFoundError(f'bio.csv not found under {root}')
    return candidates[0]


def build_cgmacros_replay(subject_file: str | Path, data_root: str | Path) -> tuple[dict, list[dict], int]:
    p = Path(subject_file)
    series = load_cgmacros_subject(p)
    bio = load_bio(_find_bio(data_root))
    pid = series['subject_id'].iloc[0]
    row = bio.loc[bio['subject_id'] == pid]
    if row.empty:
        raise ValueError(f'CGMacros phenotype not found for {pid}')
    row = row.iloc[0]
    profile = {
        'patient_id': pid,
        'data_source': 'CGMacros',
        'age': _none_if_nan(row['age']),
        'sex': _none_if_nan(row['sex']),
        'bmi': _none_if_nan(row['bmi']),
        'hba1c': _none_if_nan(row['hba1c']),
        'fasting_glucose': _none_if_nan(row['fasting_glucose']),
        'fasting_insulin': _none_if_nan(row['fasting_insulin']),
        'triglycerides': _none_if_nan(row['triglycerides']),
        'hdl': _none_if_nan(row['hdl']),
        'ldl': _none_if_nan(row['ldl']),
    }
    stream = []
    for r in series.itertuples(index=False):
        stream.append({
            'timestamp': pd.Timestamp(r.timestamp).isoformat(),
            'glucose': _none_if_nan(r.glucose),
            'truth_glucose': _none_if_nan(r.glucose),
            'heart_rate': _none_if_nan(r.heart_rate),
            'steps_5m': None,
            'activity': _none_if_nan(r.activity),
            'carbs_active_g': _none_if_nan(r.carbs_active_g),
            'minutes_since_meal': _none_if_nan(r.minutes_since_meal),
            'quality': r.quality,
            'provenance': {
                'stream': 'real-research-replay',
                'dataset': 'CGMacros',
                'subject_id': pid,
                'glucose': 'CGMacros Dexcom with Libre fallback',
                'activity': 'CGMacros Fitbit-derived activity',
                'meal': 'CGMacros meal/macronutrient log',
            },
        })
    while stream and stream[0]['glucose'] is None:
        stream.pop(0)
    if not stream:
        raise ValueError(f'No usable observations for {pid}')
    return profile, stream, 5
