"""Leakage-safe ShanghaiT2DM glucose forecasting and event-risk training.

Usage:
  python scripts/train_shanghai.py \
    --data-dir data/raw/shanghai/ShanghaiT2DM_harmonized/ShanghaiT2DM-extracted-glucose-files \
    --metadata data/reference/shanghai_t2dm_metadata.csv \
    --out models/shanghai

Design rules:
- participant IDs are the grouping unit; visits from the same person never cross folds;
- features use current/past data only;
- targets never cross a long missing CGM gap;
- full-record mean glucose is deliberately NOT a feature (it would leak future information);
- missing HbA1c is handled with a missingness indicator and fold-local imputation;
- model performance is compared against glucose persistence;
- a separate 120-minute >180 mg/dL event classifier reports AUROC/AUPRC/Brier;
- personalization is evaluated only on out-of-fold subjects, chronologically.
"""

# RESEARCH SHANGHAI-ONLY UTILITY — final external metrics come from train_submission.py / validate_external.py.
from __future__ import annotations
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier

from app.shanghai import discover_shanghai_subject_files, load_shanghai_subject, load_shanghai_metadata, attach_metadata
from scripts.training_common import (
    grouped_regression_oof,
    grouped_classifier_oof,
    personalization_from_oof,
    fit_and_save_final,
    write_json,
)

HORIZONS = (30, 60, 120)
CADENCE_MIN = 15
FEATURES = [
    'glucose','slope_15','slope_30','roll30','roll60','std60',
    'hour_sin','hour_cos','age','hba1c','hba1c_missing',
]


def _future_matrix(s: pd.Series, steps: int) -> pd.DataFrame:
    return pd.concat([s.shift(-i) for i in range(1, steps + 1)], axis=1)


def featurize_subject(cgm: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    x = attach_metadata(cgm, metadata).sort_values('timestamp').reset_index(drop=True)
    valid = x['glucose'].notna() & x['quality'].ne('MISSING')
    # A new segment begins after any true missing interval. Isolated IMPUTED points remain usable.
    x['_segment'] = (~valid).cumsum()
    parts = []
    for _, g in x.loc[valid].groupby('_segment', observed=True):
        g = g.copy().sort_values('timestamp')
        if len(g) < 12:
            continue
        g['slope_15'] = g['glucose'].diff(1) / 15.0
        g['slope_30'] = g['glucose'].diff(2) / 30.0
        g['roll30'] = g['glucose'].rolling(2, min_periods=2).mean()
        g['roll60'] = g['glucose'].rolling(4, min_periods=3).mean()
        g['std60'] = g['glucose'].rolling(4, min_periods=3).std().fillna(0)
        mins = g['timestamp'].dt.hour * 60 + g['timestamp'].dt.minute
        g['hour_sin'] = np.sin(2*np.pi*mins/1440)
        g['hour_cos'] = np.cos(2*np.pi*mins/1440)
        g['hba1c_missing'] = g['hba1c'].isna().astype(float)
        for h in HORIZONS:
            steps = h // CADENCE_MIN
            fut = _future_matrix(g['glucose'], steps)
            g[f'y{h}'] = g['glucose'].shift(-steps)
            g[f'valid_y{h}'] = fut.notna().all(axis=1)
        fut120 = _future_matrix(g['glucose'], 120 // CADENCE_MIN)
        g['event120'] = (fut120.max(axis=1) > 180).astype(float)
        g.loc[~fut120.notna().all(axis=1), 'event120'] = np.nan
        parts.append(g)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    # Past-only dynamic features must be available; static HbA1c may remain missing by design.
    return out.dropna(subset=['glucose','slope_15','slope_30','roll30','roll60','std60','age'])


def regressor():
    return HistGradientBoostingRegressor(max_iter=220, max_depth=5, learning_rate=.055, l2_regularization=1.2, random_state=42)


def classifier():
    return HistGradientBoostingClassifier(max_iter=220, max_depth=5, learning_rate=.055, l2_regularization=1.2, random_state=42)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', required=True)
    ap.add_argument('--metadata', default='data/reference/shanghai_t2dm_metadata.csv')
    ap.add_argument('--out', default='models/shanghai')
    args = ap.parse_args()

    files = discover_shanghai_subject_files(args.data_dir)
    if len(files) < 2:
        raise SystemExit('Need at least two Shanghai participant CSVs (2000.csv ... 2099.csv).')
    metadata = load_shanghai_metadata(args.metadata)
    frames = [featurize_subject(load_shanghai_subject(p), metadata) for p in files]
    frames = [f for f in frames if not f.empty]
    if not frames:
        raise SystemExit('No valid continuous Shanghai segments after quality filtering.')
    data = pd.concat(frames, ignore_index=True).replace([np.inf,-np.inf], np.nan)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    report = {
        'dataset': 'ShanghaiT2DM',
        'subjects_discovered': len(files),
        'subjects_used': int(data['subject_id'].nunique()),
        'cadence_minutes': CADENCE_MIN,
        'validation': 'GroupKFold by patient; chronological unseen-subject personalization',
        'leakage_controls': [
            'no random row split',
            'no whole-record mean glucose feature',
            'targets remain within continuous non-missing segment',
            'fold-local feature imputation',
        ],
        'forecast': {},
    }
    oof_by_h = {}
    for h in HORIZONS:
        d = data.loc[data[f'valid_y{h}'] & data[f'y{h}'].notna()].copy()
        metrics, oof = grouped_regression_oof(d, FEATURES, f'y{h}', regressor)
        metrics['personalization'] = personalization_from_oof(oof)
        report['forecast'][str(h)] = metrics
        oof_by_h[h] = oof
        fit_and_save_final(
            d, FEATURES, f'y{h}', regressor, out/f'forecast_{h}.joblib',
            horizon=h, source='ShanghaiT2DM', validation='GroupKFold by patient',
            extra={'cadence_minutes': CADENCE_MIN, 'task':'glucose-regression'},
        )
        oof.to_csv(out/f'oof_forecast_{h}.csv', index=False)

    risk_data = data.loc[data['event120'].notna()].copy()
    risk_metrics, risk_oof = grouped_classifier_oof(risk_data, FEATURES, 'event120', classifier)
    report['risk_120'] = {
        **risk_metrics,
        'event_definition': 'any observed CGM glucose >180 mg/dL within the next 120 minutes',
    }
    fit_and_save_final(
        risk_data, FEATURES, 'event120', classifier, out/'risk_120.joblib',
        source='ShanghaiT2DM', validation='GroupKFold by patient',
        extra={'horizon':120, 'cadence_minutes':CADENCE_MIN, 'task':'excursion-classification', 'event_threshold_mg_dl':180},
    )
    risk_oof.to_csv(out/'oof_risk_120.csv', index=False)
    write_json(out/'metrics.json', report)
    print(pd.Series({
        'subjects': report['subjects_used'],
        'mae30': report['forecast']['30']['mae_pooled'],
        'mae60': report['forecast']['60']['mae_pooled'],
        'mae120': report['forecast']['120']['mae_pooled'],
        'risk_auroc': report['risk_120']['auroc'],
        'risk_auprc': report['risk_120']['auprc'],
    }).to_string())

if __name__ == '__main__':
    main()
