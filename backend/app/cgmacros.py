from __future__ import annotations
from pathlib import Path
import re
import pandas as pd
import numpy as np

ALIASES = {
    'timestamp': ['Timestamp','timestamp','Date','date'],
    'dexcom': ['Dexcom GL','Dexcom','dexcom_gl','CGM'],
    'libre': ['Libre GL','Libre','libre_gl'],
    'heart_rate': ['HR','Heart Rate','heart_rate'],
    'mets': ['Mets','METs','mets'],
    'intensity': ['Intensity'],
    'activity_calories': ['Calories (Activity)','Activity Calories','activity_calories'],
    'meal_type': ['Meal Type','meal_type'],
    'calories': ['Calories','Meal Calories','calories'],
    'carbs': ['Carbs','carbs','Carbohydrates'],
    'protein': ['Protein','protein'],
    'fat': ['Fat','fat'],
    'fiber': ['Fiber','fiber'],
    'amount_consumed': ['Amount Consumed','amount_consumed'],
}

BIO_ALIASES = {
    'subject_id':['Subject','subject','Subject ID','subject_id','ID','id','Participant','participant','Participant ID','Unnamed: 0'],
    'age':['Age','age'], 'sex':['Gender','Sex','gender','sex'], 'bmi':['BMI','bmi'],
    'hba1c':['HbA1c','A1c','hba1c','A1c PDL (Lab)'], 'fasting_glucose':['Fasting Glucose','fasting glucose','Fasting glucose','Fasting GLU - PDL (Lab)'],
    'fasting_insulin':['Insulin','Fasting Insulin','fasting insulin'], 'triglycerides':['Triglycerides','triglycerides'],
    'hdl':['HDL','hdl'], 'ldl':['LDL','ldl','LDL (Cal)']
}

def _find_col(df: pd.DataFrame, aliases: list[str], required=False):
    lookup={str(c).strip().lower():c for c in df.columns}
    for a in aliases:
        if a.lower() in lookup: return lookup[a.lower()]
    if required: raise ValueError(f'Missing required column. Tried: {aliases}. Available: {list(df.columns)}')
    return None

def normalize_subject_id(value) -> str:
    digits=re.findall(r'\d+',str(value))
    return f'CGM-{int(digits[-1]):03d}' if digits else str(value).strip()

def load_bio(path: str | Path) -> pd.DataFrame:
    df=pd.read_csv(path)
    out=pd.DataFrame(index=df.index)
    for key,aliases in BIO_ALIASES.items():
        c=_find_col(df,aliases,required=(key=='subject_id'))
        out[key]=df[c] if c else np.nan
    out['subject_id']=out['subject_id'].map(normalize_subject_id)
    return out

def load_cgmacros_subject(csv_path: str | Path, resample='5min') -> pd.DataFrame:
    """Load one official CGMacros participant CSV while preserving subject identity.

    Uses Dexcom when present, falls back to Libre, carries meal events forward through
    a decaying 'carbs_active_g' feature, and resamples to a stable 5-minute twin cadence.
    """
    p=Path(csv_path); raw=pd.read_csv(p)
    cols={k:_find_col(raw,v,required=(k=='timestamp')) for k,v in ALIASES.items()}
    ts=pd.to_datetime(raw[cols['timestamp']],errors='coerce')
    dex=pd.to_numeric(raw[cols['dexcom']],errors='coerce') if cols['dexcom'] else None
    libre=pd.to_numeric(raw[cols['libre']],errors='coerce') if cols['libre'] else None
    # Preserve one sensor per subject; do not splice channels at individual
    # timestamps. Use the published/primary Dexcom channel whenever it has
    # meaningful coverage; a near-empty Dexcom stream is not a usable sensor.
    # The absolute threshold matters on the full official recordings; tiny
    # adapter fixtures still prefer Dexcom whenever both streams are short.
    plausible=lambda s: s.where(s.between(30,450)) if s is not None else None
    dex=plausible(dex)
    libre=plausible(libre)
    ndex=int(dex.notna().sum()) if dex is not None else 0
    nlibre=int(libre.notna().sum()) if libre is not None else 0
    dex_unusable=(nlibre >= 500 and ndex < 500) or (nlibre >= 500 and ndex < .10*nlibre)
    if ndex > 0 and not dex_unusable:
        glucose=dex; cgm_source='Dexcom'
    elif nlibre > 0:
        glucose=libre; cgm_source='Libre'
    else:
        raise ValueError('No plausible CGM readings (30–450 mg/dL) found in either device.')
    out=pd.DataFrame({'timestamp':ts,'glucose':glucose})
    for key in ['heart_rate','mets','activity_calories','calories','carbs','protein','fat','fiber','amount_consumed']:
        out[key]=pd.to_numeric(raw[cols[key]],errors='coerce') if cols[key] else np.nan
    out['meal_type']=raw[cols['meal_type']].astype('string') if cols['meal_type'] else pd.Series(pd.NA,index=raw.index,dtype='string')
    out=out.dropna(subset=['timestamp']).sort_values('timestamp').set_index('timestamp')
    # Preserve meal events during resampling via sum/first instead of averaging them away.
    agg={c:'mean' for c in ['glucose','heart_rate','mets','activity_calories']}
    agg.update({c:'sum' for c in ['calories','carbs','protein','fat','fiber']})
    agg.update({'amount_consumed':'mean','meal_type':'first'})
    # Timestamp is the END of the completed bucket: do not expose later
    # samples or meal records at the beginning of that bucket.
    out=out.resample(resample, label='right', closed='right').agg(agg)
    glucose_missing_before_impute=out['glucose'].isna()
    out['glucose']=out['glucose'].interpolate(limit=2)
    out['heart_rate']=out['heart_rate'].interpolate(limit=2)
    # 'Intensity' is present in some subject files but is not documented
    # as the same numerical METs x10 field. Do not silently mix units.
    out['activity']=((out['mets']-10).clip(lower=0)/70).clip(0,1)
    # Decaying carbohydrate exposure rather than forward-filling the raw meal value.
    active=0.0; active_vals=[]; minutes_since=[]; since=None
    decay=np.exp(-5/80)
    for carbs in out['carbs'].fillna(0):
        active*=decay
        if carbs>0:
            active+=float(carbs); since=0
        elif since is not None:
            since+=5
        active_vals.append(active); minutes_since.append(since)
    out['carbs_active_g']=active_vals; out['minutes_since_meal']=pd.to_numeric(pd.Series(minutes_since,index=out.index),errors='coerce')
    # Data quality label keeps imputed glucose visible to downstream UI.
    still_missing=out['glucose'].isna()
    out['quality']=np.where(still_missing,'MISSING',np.where(glucose_missing_before_impute,'IMPUTED','VALID'))
    out=out.reset_index()
    sid_match=re.findall(r'\d+',p.stem)
    out['subject_id']=f'CGM-{int(sid_match[-1]):03d}' if sid_match else p.stem
    out['cgm_source']=cgm_source
    return out

def discover_subject_files(root: str | Path) -> list[Path]:
    root=Path(root)
    return sorted([p for p in root.rglob('*.csv') if 'cgmacros' in p.name.lower() and 'dictionary' not in p.name.lower()])
