"""External transportability validation for HimanshuDigitalTwin artifacts.

The canonical deployment model is multimodal CGMacros. External Shanghai validation uses
a separate CGMacros-trained transport artifact restricted to modalities genuinely available
in Shanghai (CGM dynamics + age/HbA1c). This avoids pretending absent meal/activity/HR data
are observed during external validation.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, roc_auc_score, average_precision_score, brier_score_loss
from sklearn.pipeline import Pipeline

from app.shanghai import discover_shanghai_subject_files, load_shanghai_subject, load_shanghai_metadata, attach_metadata

HORIZONS=(30,60,120)
CADENCE=15


def _matrix(frame: pd.DataFrame, artifact: dict) -> pd.DataFrame:
    defaults=artifact.get('feature_defaults', artifact.get('imputation', {})) or {}
    # If the fitted model is a Pipeline with a train-only imputer, preserving
    # missing values is mandatory for consistent model/serve semantics.
    model=artifact.get('model')
    pipeline_imputes=isinstance(model,Pipeline) and 'imputer' in model.named_steps
    out=pd.DataFrame(index=frame.index)
    for c in artifact['features']:
        if c in frame.columns:
            out[c]=pd.to_numeric(frame[c],errors='coerce')
        elif c=='hba1c_missing':
            out[c]=frame['hba1c'].isna().astype(float) if 'hba1c' in frame else 1.0
        else:
            out[c]=np.nan
        if not pipeline_imputes:
            out[c]=out[c].fillna(float(defaults.get(c,0.0)))
    return out[artifact['features']]


def _featurize(path: Path, metadata: pd.DataFrame) -> pd.DataFrame:
    x=attach_metadata(load_shanghai_subject(path),metadata).sort_values('timestamp').reset_index(drop=True)
    # Interpolated glucose is NOT evaluation truth. A segment must consist of
    # genuinely measured values at consecutive 15-minute timestamps.
    valid=x['glucose'].notna() & x['quality'].eq('VALID')
    consecutive=x['timestamp'].diff().dt.total_seconds().eq(CADENCE*60)
    x['_segment']=(~(valid & consecutive & valid.shift(fill_value=False))).cumsum()
    parts=[]
    for _,g in x.loc[valid].groupby('_segment',observed=True):
        g=g.copy().sort_values('timestamp')
        if len(g)<12: continue
        g['slope_15']=g['glucose'].diff(1)/15.0
        g['roll30']=g['glucose'].rolling(2,min_periods=2).mean()
        g['roll60']=g['glucose'].rolling(4,min_periods=4).mean()
        g['std60']=g['glucose'].rolling(4,min_periods=4).std()
        g['cv60']=g['std60']/g['roll60'].replace(0,np.nan)
        mins=g['timestamp'].dt.hour*60+g['timestamp'].dt.minute
        g['hour_sin']=np.sin(2*np.pi*mins/1440); g['hour_cos']=np.cos(2*np.pi*mins/1440)
        g['hba1c_missing']=g['hba1c'].isna().astype(float)
        # Modalities absent from the harmonized Shanghai stream remain NaN and are
        # replaced only by training-set defaults stored in the artifact.
        for c in ['carbs_active_g','minutes_since_meal','activity','heart_rate','bmi','fasting_glucose']:
            if c not in g: g[c]=np.nan
        for h in HORIZONS:
            k=h//CADENCE
            fut=pd.concat([g['glucose'].shift(-i) for i in range(1,k+1)],axis=1)
            g[f'y{h}']=g['glucose'].shift(-k)
            g[f'valid_y{h}']=fut.notna().all(axis=1)
        fut120=pd.concat([g['glucose'].shift(-i) for i in range(1,120//CADENCE+1)],axis=1)
        future_max=fut120.max(axis=1)
        eligible=fut120.notna().all(axis=1) & g['glucose'].notna() & (g['glucose']<=180)
        g['event120']=np.nan
        g.loc[eligible,'event120']=(future_max.loc[eligible]>180).astype(float)
        parts.append(g)
    return pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()


def _reg(y,p):
    return {'mae':float(mean_absolute_error(y,p)),'rmse':float(mean_squared_error(y,p)**0.5),'n':int(len(y))}


def evaluate(model_dir: str|Path, shanghai_dir: str|Path, metadata_path: str|Path) -> dict:
    model_dir=Path(model_dir)
    files=discover_shanghai_subject_files(shanghai_dir)
    if len(files)<2: raise ValueError('Need at least two Shanghai subjects for external validation.')
    meta=load_shanghai_metadata(metadata_path)
    frames=[_featurize(p,meta) for p in files]
    frames=[f for f in frames if not f.empty]
    data=pd.concat(frames,ignore_index=True).replace([np.inf,-np.inf],np.nan)
    report={'cohort':'ShanghaiT2DM','role':'external modality-matched transportability validation only','subjects':int(data['subject_id'].nunique()),'forecast':{},'model_kind':'CGMacros-trained CGM/phenotype transport artifact','missing_modalities_not_used_by_transport_model':['meal','activity','heart_rate','BMI','fasting_glucose']}
    for h in HORIZONS:
        path=model_dir/f'transport_forecast_{h}.joblib'
        if not path.exists():
            raise FileNotFoundError(f'Missing dedicated Shanghai transport model: {path}')
        art=joblib.load(path)
        # Never silently score a multimodal primary model as transport evidence.
        forbidden={'carbs_active_g','activity','heart_rate','minutes_since_meal'}
        if forbidden.intersection(art.get('features',[])):
            raise ValueError(f'{path.name}: transport artifact contains unavailable Shanghai modalities')
        d=data.loc[data[f'valid_y{h}'] & data[f'y{h}'].notna()].copy()
        pred=art['model'].predict(_matrix(d,art))
        persist=d['glucose'].to_numpy()
        model_m=_reg(d[f'y{h}'],pred); base_m=_reg(d[f'y{h}'],persist)
        subject_mae=[]
        d=d[['subject_id',f'y{h}']].copy(); d['pred']=pred; d['persist']=persist
        for _,g in d.groupby('subject_id',observed=True):
            subject_mae.append((mean_absolute_error(g[f'y{h}'],g['pred']),mean_absolute_error(g[f'y{h}'],g['persist'])))
        width=art.get('interval_half_width_80')
        coverage=float(np.mean(np.abs(d[f'y{h}'].to_numpy()-pred)<=float(width))) if width is not None else None
        report['forecast'][str(h)]={
            'model':model_m,'persistence':base_m,
            'improvement_vs_persistence_pct':float(100*(base_m['mae']-model_m['mae'])/max(1e-9,base_m['mae'])),
            'mae_macro_subject':float(np.mean([x[0] for x in subject_mae])),
            'persistence_mae_macro_subject':float(np.mean([x[1] for x in subject_mae])),
            'prediction_interval_80':{'half_width_mg_dl':float(width) if width is not None else None,'external_empirical_coverage':coverage,'calibrated_on':'CGMacros training subjects only'},
        }
    risk_path=model_dir/'transport_event_120.joblib'
    if not risk_path.exists():
        raise FileNotFoundError(f'Missing dedicated Shanghai transport event artifact: {risk_path}')
    if risk_path.exists():
        art=joblib.load(risk_path); d=data.loc[data['event120'].notna()].copy(); y=d['event120'].astype(int).to_numpy()
        model=art['model']; X=_matrix(d,art)
        p=model.predict_proba(X)[:,1] if hasattr(model,'predict_proba') else np.clip(model.predict(X),0,1)
        report['event_120']={
            'event_rate':float(y.mean()),'n':int(len(y)),
            'auroc':float(roc_auc_score(y,p)) if len(np.unique(y))==2 else None,
            'auprc':float(average_precision_score(y,p)) if len(np.unique(y))==2 else None,
            'brier':float(brier_score_loss(y,p)),
            'current_glucose_auroc_baseline':float(roc_auc_score(y,d['glucose'])) if len(np.unique(y))==2 else None,
        }
    return report


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--model-dir',required=True); ap.add_argument('--shanghai-dir',required=True); ap.add_argument('--metadata',required=True); ap.add_argument('--out',default='reports/external_shanghai.json'); args=ap.parse_args()
    report=evaluate(args.model_dir,args.shanghai_dir,args.metadata)
    out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(report,indent=2,allow_nan=False))

if __name__=='__main__': main()
