"""Leakage-safe multimodal CGMacros training for HimanshuDigitalTwin.

Uses participant-grouped validation, persistence baselines, a separately validated
120-minute excursion classifier, and out-of-fold chronological personalization testing.
"""

# RESEARCH CROSS-VALIDATION UTILITY — final submission metrics come from train_submission.py.
from __future__ import annotations
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier

from app.cgmacros import discover_subject_files, load_cgmacros_subject, load_bio
from scripts.training_common import (
    grouped_regression_oof, grouped_classifier_oof, personalization_from_oof,
    fit_and_save_final, write_json,
)

HORIZONS=(30,60,120)
CADENCE_MIN=5
FEATURES=['glucose','slope_15','roll30','roll60','std60','cv60','carbs_active_g','minutes_since_meal','activity','heart_rate','hour_sin','hour_cos','age','bmi','hba1c','fasting_glucose']


def _future_matrix(s: pd.Series, steps: int) -> pd.DataFrame:
    return pd.concat([s.shift(-i) for i in range(1, steps + 1)], axis=1)


def featurize(df: pd.DataFrame) -> pd.DataFrame:
    x=df.sort_values('timestamp').copy()
    # Do not let targets jump across true sensor outages.
    valid=x['glucose'].notna() & x['quality'].ne('MISSING')
    x['_segment']=(~valid).cumsum()
    parts=[]
    for _,g in x.loc[valid].groupby('_segment', observed=True):
        g=g.copy().sort_values('timestamp')
        if len(g)<30: continue
        g['slope_15']=(g['glucose']-g['glucose'].shift(3))/15
        g['roll30']=g['glucose'].rolling(6,min_periods=4).mean()
        g['roll60']=g['glucose'].rolling(12,min_periods=6).mean()
        g['std60']=g['glucose'].rolling(12,min_periods=6).std().fillna(0)
        g['cv60']=(g['std60']/g['roll60'].replace(0,np.nan)).fillna(0)
        mins=g['timestamp'].dt.hour*60+g['timestamp'].dt.minute
        g['hour_sin']=np.sin(2*np.pi*mins/1440); g['hour_cos']=np.cos(2*np.pi*mins/1440)
        for h in HORIZONS:
            steps=h//CADENCE_MIN; fut=_future_matrix(g['glucose'],steps)
            g[f'y{h}']=g['glucose'].shift(-steps); g[f'valid_y{h}']=fut.notna().all(axis=1)
        fut120=_future_matrix(g['glucose'],120//CADENCE_MIN)
        g['event120']=(fut120.max(axis=1)>180).astype(float)
        g.loc[~fut120.notna().all(axis=1),'event120']=np.nan
        parts.append(g)
    return pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()


def regressor():
    return HistGradientBoostingRegressor(max_iter=220,max_depth=5,learning_rate=.055,l2_regularization=1.2,random_state=42)


def classifier():
    return HistGradientBoostingClassifier(max_iter=220,max_depth=5,learning_rate=.055,l2_regularization=1.2,random_state=42)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data-dir',required=True); ap.add_argument('--out',default='models/real'); args=ap.parse_args()
    files=discover_subject_files(args.data_dir)
    if not files: raise SystemExit('No CGMacros participant CSVs found. Expected filenames such as CGMacros-001.csv.')
    frames=[featurize(load_cgmacros_subject(f)) for f in files]
    frames=[f for f in frames if not f.empty]
    data=pd.concat(frames,ignore_index=True).replace([np.inf,-np.inf],np.nan)
    bio_candidates=[p for p in Path(args.data_dir).rglob('*.csv') if p.name.lower()=='bio.csv']
    if not bio_candidates: raise SystemExit('bio.csv not found. Static phenotype must come from the same CGMacros subjects.')
    bio=load_bio(bio_candidates[0])
    for c in ['age','bmi','hba1c','fasting_glucose']: bio[c]=pd.to_numeric(bio[c],errors='coerce')
    data=data.merge(bio[['subject_id','age','bmi','hba1c','fasting_glucose']],on='subject_id',how='left',validate='many_to_one')
    data=data.dropna(subset=['glucose','slope_15','roll30','roll60','std60','subject_id'])
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    report={'dataset':'CGMacros','subjects_used':int(data['subject_id'].nunique()),'cadence_minutes':CADENCE_MIN,'validation':'GroupKFold by participant','forecast':{}}
    for h in HORIZONS:
        d=data.loc[data[f'valid_y{h}'] & data[f'y{h}'].notna()].copy()
        metrics,oof=grouped_regression_oof(d,FEATURES,f'y{h}',regressor)
        metrics['personalization']=personalization_from_oof(oof)
        report['forecast'][str(h)]=metrics
        fit_and_save_final(d,FEATURES,f'y{h}',regressor,out/f'forecast_{h}.joblib',horizon=h,source='CGMacros',validation='GroupKFold by participant',extra={'cadence_minutes':CADENCE_MIN,'task':'multimodal-glucose-regression'})
        oof.to_csv(out/f'oof_forecast_{h}.csv',index=False)
    risk_data=data.loc[data['event120'].notna()].copy()
    risk_metrics,risk_oof=grouped_classifier_oof(risk_data,FEATURES,'event120',classifier)
    report['risk_120']={**risk_metrics,'event_definition':'any observed CGM glucose >180 mg/dL within next 120 minutes'}
    fit_and_save_final(risk_data,FEATURES,'event120',classifier,out/'risk_120.joblib',source='CGMacros',validation='GroupKFold by participant',extra={'horizon':120,'cadence_minutes':CADENCE_MIN,'task':'excursion-classification','event_threshold_mg_dl':180})
    risk_oof.to_csv(out/'oof_risk_120.csv',index=False)
    write_json(out/'metrics.json',report)
    print(f"subjects={report['subjects_used']} | 30m MAE={report['forecast']['30']['mae_pooled']:.2f} | 60m MAE={report['forecast']['60']['mae_pooled']:.2f} | 120m MAE={report['forecast']['120']['mae_pooled']:.2f} | risk AUROC={report['risk_120']['auroc']}")

if __name__=='__main__': main()
