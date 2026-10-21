"""Real-cohort ShanghaiT2DM benchmark for HimanshuDigitalTwin.

This script intentionally evaluates sensor-only baselines. It does NOT claim to validate
CGMacros meal/activity features on Shanghai, because those modalities are not harmonized
into the Glucose-ML Shanghai files. It establishes an honest external benchmark for the
CGM forecasting problem and future transportability tests.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from app.shanghai import discover_shanghai_subject_files, load_shanghai_subject

HORIZONS=(30,60,120)


def reg(y,p):
    return {'mae':float(mean_absolute_error(y,p)),'rmse':float(mean_squared_error(y,p)**0.5),'n':int(len(y))}


def subject_frame(path: Path) -> pd.DataFrame:
    x=load_shanghai_subject(path,resample='15min').copy()
    x=x.sort_values('timestamp')
    x['slope_15']=(x['glucose']-x['glucose'].shift(1))/15.0
    for h in HORIZONS:
        k=h//15
        x[f'y{h}']=x['glucose'].shift(-k)
    future=pd.concat([x['glucose'].shift(-k) for k in range(1,9)],axis=1)
    x['future_max_120']=future.max(axis=1,skipna=False)
    x['event_120']=np.where(x['future_max_120'].notna(),(x['future_max_120']>180).astype(int),np.nan)
    return x


def benchmark(root: str|Path) -> dict:
    files=discover_shanghai_subject_files(root)
    if not files:
        raise SystemExit('No harmonized Shanghai subject CSVs found (expected 2000.csv ... 2099.csv).')
    all_frames=[]; per_subject={}
    for f in files:
        x=subject_frame(f); all_frames.append(x)
        sid=x['subject_id'].iloc[0]
        per_subject[sid]={}
        for h in HORIZONS:
            q=x.dropna(subset=['glucose','slope_15',f'y{h}'])
            if q.empty: continue
            persist=q['glucose'].to_numpy(); trend=np.clip(q['glucose'].to_numpy()+q['slope_15'].to_numpy()*h,40,400)
            per_subject[sid][str(h)]={'persistence':reg(q[f'y{h}'],persist),'linear_trend':reg(q[f'y{h}'],trend)}
    data=pd.concat(all_frames,ignore_index=True)
    result={'subjects':len(files),'cohort':'ShanghaiT2DM','cadence_min':15,'baseline_metrics':{},'event_definition':'glucose >180 mg/dL within next 120 minutes','per_subject':per_subject}
    for h in HORIZONS:
        q=data.dropna(subset=['glucose','slope_15',f'y{h}'])
        persist=q['glucose'].to_numpy(); trend=np.clip(q['glucose'].to_numpy()+q['slope_15'].to_numpy()*h,40,400)
        result['baseline_metrics'][str(h)]={'persistence':reg(q[f'y{h}'],persist),'linear_trend':reg(q[f'y{h}'],trend)}
    e=data['event_120'].dropna()
    result['event_prevalence']=float(e.mean()) if len(e) else None
    result['eligible_event_rows']=int(len(e))
    return result


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data-dir',required=True); ap.add_argument('--out',default='reports/shanghai_baseline.json'); args=ap.parse_args()
    r=benchmark(args.data_dir); out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(r,indent=2)); print(json.dumps({k:v for k,v in r.items() if k!='per_subject'},indent=2))

if __name__=='__main__': main()
