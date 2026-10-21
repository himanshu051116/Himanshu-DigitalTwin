"""Leakage-resistant primary/evidence training for HimanshuDigitalTwin.

Primary deployment model: multimodal CGMacros (same-subject CGM + phenotype + meals + activity).
External-transport model: CGM/phenotype-only feature subset that is actually available in ShanghaiT2DM.

Protocol:
* deterministic subject-stratified 20% locked holdout
* model/hyperparameter selection only on training subjects via GroupKFold
* persistence + linear-trend baselines
* causal context-aware online personalization evaluation on unseen subjects
* OOF uncertainty calibration using training subjects only
* separate onset-risk target: current glucose <=180 and future glucose crosses >180 in 120 min
"""
from __future__ import annotations

import argparse, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score,brier_score_loss,f1_score,mean_absolute_error,mean_squared_error,precision_score,recall_score,roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.cgmacros import discover_subject_files, load_bio, load_cgmacros_subject
from scripts.training_common import personalization_from_oof

HORIZONS=(30,60,120)
FEATURES=[
    'glucose','slope_15','roll30','roll60','cv60',
    'carbs_active_g','minutes_since_meal','activity','heart_rate',
    'hour_sin','hour_cos','age','bmi','hba1c','fasting_glucose',
]
TRANSPORT_FEATURES=['glucose','slope_15','roll30','roll60','cv60','hour_sin','hour_cos','age','hba1c']
REFERENCE_META=Path(__file__).resolve().parents[1]/'data'/'reference'/'cgmacros_dexcom_metadata.csv'
REG_CANDIDATES=[
    {'max_depth':3,'learning_rate':.05,'max_iter':100,'l2_regularization':1.0},
    {'max_depth':5,'learning_rate':.04,'max_iter':130,'l2_regularization':1.0},
]
EVENT_CANDIDATES=[
    {'C':.25,'class_weight':None},
    {'C':.8,'class_weight':None},
    {'C':2.0,'class_weight':None},
]


def glycemic_group(hba1c):
    if pd.isna(hba1c): return 'unknown'
    if hba1c<5.7: return 'ND'
    if hba1c<=6.4: return 'PreD'
    return 'T2D'


def featurize(df: pd.DataFrame) -> pd.DataFrame:
    """Use only genuine CGM observations and consecutive 5-minute sample times.

    No forecast label may bridge a missing/imputed glucose reading or a gap
    between recording sessions. In particular, pandas shift() alone is not a
    temporal-validity guarantee. Auxiliary wearable modalities remain optional.
    """
    x=df.copy().sort_values('timestamp').reset_index(drop=True)
    quality=x['quality'].eq('VALID') if 'quality' in x else x['glucose'].notna()
    valid=quality & x['glucose'].notna()
    consecutive=x['timestamp'].diff().dt.total_seconds().eq(300)
    # A 60-minute lookback needs the current reading and 12 prior readings.
    segment=(~consecutive).cumsum()
    valid_run=(~(consecutive & valid & valid.shift(fill_value=False))).cumsum()
    run=valid.groupby(valid_run).cumsum()
    x['valid_history_60']=valid & run.ge(13)
    clean=x['glucose'].where(valid)
    x['slope_15']=(clean-clean.shift(3))/15.0
    x['roll30']=clean.rolling(6,min_periods=6).mean()
    x['roll60']=clean.rolling(12,min_periods=12).mean()
    std=clean.rolling(12,min_periods=12).std()
    x['cv60']=std/x['roll60'].replace(0,np.nan)
    mins=x['timestamp'].dt.hour*60+x['timestamp'].dt.minute
    x['hour_sin']=np.sin(2*np.pi*mins/1440); x['hour_cos']=np.cos(2*np.pi*mins/1440)
    for h in HORIZONS:
        n=h//5
        # All observations from origin through target must be genuine and in
        # the same continuous 5-minute segment; otherwise label is unknown.
        future_ok=pd.concat([valid.shift(-k,fill_value=False) for k in range(n+1)],axis=1).all(axis=1)
        same_segment=segment.eq(segment.shift(-n))
        x[f'y{h}']=clean.shift(-n).where(x['valid_history_60'] & future_ok & same_segment)
    future=pd.concat([clean.shift(-k) for k in range(1,25)],axis=1)
    event_ok=pd.concat([valid.shift(-k,fill_value=False) for k in range(25)],axis=1).all(axis=1)
    same_segment=segment.eq(segment.shift(-24))
    x['future_max_120']=future.max(axis=1,skipna=False).where(event_ok & same_segment)
    eligible=x['future_max_120'].notna() & x['valid_history_60'] & clean.le(180)
    x['event_120']=np.nan
    x.loc[eligible,'event_120']=(x.loc[eligible,'future_max_120']>180).astype(int)
    return x


def _safe_auc(y,p): return float(roc_auc_score(y,p)) if len(np.unique(y))>1 else None
def _safe_auprc(y,p): return float(average_precision_score(y,p)) if len(np.unique(y))>1 else None

def _new_regressor(params=None, random_state=42):
    p=dict(REG_CANDIDATES[1]); p.update(params or {})
    return Pipeline([
        ('imputer',SimpleImputer(strategy='median')),
        ('model',HistGradientBoostingRegressor(random_state=random_state,**p)),
    ])


def _new_event_model(params=None):
    p={'C':.8,'class_weight':None}; p.update(params or {})
    return Pipeline([
        ('imputer',SimpleImputer(strategy='median')),
        ('scale',StandardScaler()),
        ('clf',LogisticRegression(max_iter=1200,random_state=42,**p)),
    ])


def regression_metrics(y,p): return {'mae':float(mean_absolute_error(y,p)),'rmse':float(mean_squared_error(y,p)**.5)}

def macro_subject_mae(frame,truth_col,pred_col):
    vals=[mean_absolute_error(g[truth_col],g[pred_col]) for _,g in frame.groupby('subject_id',observed=True)]
    return float(np.mean(vals)) if vals else float('nan')


def event_metrics(y,p,threshold=.5):
    label=(p>=threshold).astype(int)
    return {'auroc':_safe_auc(y,p),'auprc':_safe_auprc(y,p),'brier':float(brier_score_loss(y,p)),
            'alert_probability_threshold':float(threshold),
            'precision_at_threshold':float(precision_score(y,label,zero_division=0)),'recall_at_threshold':float(recall_score(y,label,zero_division=0)),
            'f1_at_threshold':float(f1_score(y,label,zero_division=0)),'event_prevalence':float(np.mean(y)),'n':int(len(y))}


def _eligible_rows(frame: pd.DataFrame, target: str) -> pd.DataFrame:
    required=[target,'glucose','slope_15','roll30','roll60']
    return frame.dropna(subset=required).copy()


def _event_oof_probabilities(train_frame: pd.DataFrame, features: list[str], params: dict) -> pd.DataFrame:
    work=_eligible_rows(train_frame,'event_120'); work['event_120']=work['event_120'].astype(int)
    groups=work['subject_id']; n=min(5,groups.nunique()); parts=[]
    for tr,va in GroupKFold(n_splits=n).split(work,groups=groups):
        a=work.iloc[tr]; b=work.iloc[va]
        if a['event_120'].nunique()<2: continue
        m=_new_event_model(params); m.fit(a[features],a['event_120']); prob=m.predict_proba(b[features])[:,1]
        z=b[['subject_id','timestamp','glucose','event_120']].copy(); z['probability']=prob; parts.append(z)
    if not parts: raise ValueError('Could not generate event OOF probabilities.')
    return pd.concat(parts,ignore_index=True).sort_values(['subject_id','timestamp'])


def _select_alert_threshold(oof: pd.DataFrame) -> dict:
    y=oof['event_120'].astype(int).to_numpy(); p=oof['probability'].to_numpy(); best=None
    for t in np.linspace(.05,.95,91):
        pred=(p>=t).astype(int); f=float(f1_score(y,pred,zero_division=0)); prec=float(precision_score(y,pred,zero_division=0)); rec=float(recall_score(y,pred,zero_division=0))
        candidate={'threshold':float(t),'f1':f,'precision':prec,'recall':rec}
        if best is None or (candidate['f1'],candidate['precision'],candidate['threshold'])>(best['f1'],best['precision'],best['threshold']): best=candidate
    best['selection_source']='subject-grouped OOF predictions from training subjects only'
    return best


def _episode_warning_metrics(full_test: pd.DataFrame, eligible_test: pd.DataFrame, probabilities, threshold: float) -> dict:
    """Evaluate measured hyperglycaemic onset *episodes*, not individual rows.

    Onsets require two adjacent, genuine measurements, and repeated threshold
    flickers within two hours count as ONE episode. Detection denominator uses
    only episodes with an available preceding prediction; otherwise an entire
    day without model coverage can silently lower sensitivity. False-alert
    fraction remains a per-negative-window research metric, not an episode
    false-alarm rate or an approved clinical alert.
    """
    pred=eligible_test[['subject_id','timestamp','glucose','event_120']].copy()
    if len(pred)!=len(probabilities):
        raise ValueError('Warning probabilities must align to eligible test rows.')
    pred['probability']=np.asarray(probabilities,dtype=float)
    if not np.isfinite(pred['probability']).all():
        raise ValueError('Warning probabilities must be finite.')
    onsets=[]; suppressed=0
    for sid,g in full_test.sort_values('timestamp').groupby('subject_id',observed=True):
        g=g.sort_values('timestamp').copy()
        cur_ok=g['quality'].eq('VALID') if 'quality' in g else g['glucose'].notna()
        prev=g['glucose'].shift(1)
        prev_ok=cur_ok.shift(1,fill_value=False)
        prior_t=g['timestamp'].shift(1)
        adjacent=(g['timestamp']-prior_t).dt.total_seconds().eq(300)
        crossing=cur_ok & prev_ok & adjacent & g['glucose'].gt(180) & prev.le(180)
        last_episode=None
        for t in g.loc[crossing,'timestamp']:
            if last_episode is not None and (t-last_episode).total_seconds()<=120*60:
                suppressed+=1
                continue
            onsets.append((sid,t));last_episode=t
    leads=[];evaluable=0
    for sid,onset in onsets:
        window=pred[(pred.subject_id==sid)&
            (pred.timestamp>=onset-pd.Timedelta(minutes=120))&
            (pred.timestamp<onset)]
        if window.empty:continue
        evaluable+=1
        alerted=window[window.probability>=threshold]
        if not alerted.empty:
            leads.append(float((onset-alerted.timestamp.min()).total_seconds()/60))
    negative=pred['event_120'].astype(int).eq(0)
    false_alert=pred['probability'].ge(threshold) & negative
    return {'onset_episodes':int(len(onsets)),
            'evaluable_onsets':int(evaluable),
            'unevaluable_onsets':int(len(onsets)-evaluable),
            'refractory_suppressed_crossings':int(suppressed),
            'detected_onsets':int(len(leads)),
            'episode_detection_rate':float(len(leads)/evaluable) if evaluable else None,
            'median_warning_lead_min':float(np.median(leads)) if leads else None,
            'p25_warning_lead_min':float(np.quantile(leads,.25)) if leads else None,
            'p75_warning_lead_min':float(np.quantile(leads,.75)) if leads else None,
            'false_alert_row_fraction_on_negative_windows':float(false_alert.sum()/max(1,int(negative.sum()))),
            'evidence_note':'One onset per 120-min refractory period; only genuine consecutive CGM, evaluated when predictions exist. Not a clinical false-alarm rate.'}


def build_dataset(data_dir):
    files=discover_subject_files(data_dir)
    if not files: raise SystemExit('No CGMacros participant CSVs found.')
    data=pd.concat([featurize(load_cgmacros_subject(f)) for f in files],ignore_index=True).replace([np.inf,-np.inf],np.nan)
    bios=[p for p in Path(data_dir).rglob('*.csv') if p.name.lower()=='bio.csv']
    if not bios: raise SystemExit('bio.csv not found; same-subject phenotype is mandatory.')
    bio=load_bio(bios[0])
    for c in ['age','bmi','hba1c','fasting_glucose']: bio[c]=pd.to_numeric(bio[c],errors='coerce')
    bio['glycemic_group_hba1c_fallback']=bio['hba1c'].map(glycemic_group)
    bio['glycemic_group']=bio['glycemic_group_hba1c_fallback']
    bio['glycemic_group_source']='hba1c-fallback'
    if REFERENCE_META.exists():
        ref=pd.read_csv(REFERENCE_META)
        ref['subject_id']=ref['person_id'].map(lambda x: f"CGM-{int(str(x).split('-')[-1]):03d}")
        mapping={'No diabetes':'ND','Prediabetes':'PreD','T2D':'T2D'}
        ref['published_group']=ref['diabetes_type'].map(mapping)
        labels=ref[['subject_id','published_group']].dropna().drop_duplicates('subject_id')
        bio=bio.merge(labels,on='subject_id',how='left',validate='one_to_one')
        has=bio['published_group'].notna()
        bio.loc[has,'glycemic_group']=bio.loc[has,'published_group']
        bio.loc[has,'glycemic_group_source']='published-CGMacros-metadata'
    data=data.merge(bio[['subject_id','age','bmi','hba1c','fasting_glucose','glycemic_group']],on='subject_id',how='left',validate='many_to_one')
    return data,bio


def split_subjects(bio,test_size=.20,random_state=42):
    """Deterministic stratified subject split that never lets one sparse unknown group disable stratification."""
    table=bio.drop_duplicates('subject_id')[['subject_id','glycemic_group']].copy()
    rng=np.random.default_rng(random_state); test=[]
    for group,g in table.groupby('glycemic_group',observed=True):
        ids=g['subject_id'].to_numpy().copy(); rng.shuffle(ids)
        if len(ids)<2: continue
        n=max(1,int(round(len(ids)*test_size))); n=min(n,len(ids)-1)
        test.extend(ids[:n].tolist())
    test=set(test); train=set(table['subject_id'])-test
    if not test or not train: raise ValueError('Unable to construct subject-level holdout split.')
    return train,test


def _select_regressor(train_frame,target,features):
    work=train_frame.dropna(subset=[target,'subject_id']).copy()
    # Minimal training-only tuning: deterministic evenly-spaced sample per subject.
    # This keeps model selection computationally bounded and reduces row-density domination.
    sampled=[]
    for _,g in work.groupby('subject_id',observed=True):
        if len(g)>120:
            idx=np.linspace(0,len(g)-1,120,dtype=int); sampled.append(g.iloc[idx])
        else: sampled.append(g)
    work=pd.concat(sampled,ignore_index=True); groups=work['subject_id']; n=min(3,groups.nunique())
    if n<2: raise ValueError('Need >=2 subjects for model selection.')
    rows=[]
    for ci,params in enumerate(REG_CANDIDATES):
        subject_scores=[]; pooled_y=[]; pooled_p=[]
        for fold,(tr,va) in enumerate(GroupKFold(n_splits=n).split(work,groups=groups),1):
            m=_new_regressor(params,100+ci*10+fold); m.fit(work.iloc[tr][features],work.iloc[tr][target])
            pred=m.predict(work.iloc[va][features]); valid=work.iloc[va].copy(); valid['_pred']=pred
            pooled_y.extend(valid[target].tolist()); pooled_p.extend(pred.tolist())
            subject_scores.extend([mean_absolute_error(sg[target],sg['_pred']) for _,sg in valid.groupby('subject_id',observed=True)])
        rows.append({'params':params,'macro_subject_mae':float(np.mean(subject_scores)),'pooled_mae':float(mean_absolute_error(pooled_y,pooled_p))})
    rows.sort(key=lambda r:(r['macro_subject_mae'],r['pooled_mae']))
    return rows[0]['params'],rows


def _select_event_model(train_frame,features):
    work=train_frame.dropna(subset=['event_120','subject_id']).copy(); work['event_120']=work['event_120'].astype(int)
    groups=work['subject_id']; n=min(3,groups.nunique())
    rows=[]
    for params in EVENT_CANDIDATES:
        ys=[]; ps=[]
        valid_candidate=True
        for tr,va in GroupKFold(n_splits=n).split(work,groups=groups):
            a=work.iloc[tr]; b=work.iloc[va]
            if a['event_120'].nunique()<2: valid_candidate=False; break
            m=_new_event_model(params); m.fit(a[features],a['event_120']); prob=m.predict_proba(b[features])[:,1]
            ys.extend(b['event_120'].tolist()); ps.extend(prob.tolist())
        if not valid_candidate or len(set(ys))<2: continue
        prevalence=float(np.mean(ys)); auprc=float(average_precision_score(ys,ps)); brier=float(brier_score_loss(ys,ps)); auroc=float(roc_auc_score(ys,ps))
        brier_ref=prevalence*(1-prevalence)
        rows.append({'params':params,'auprc':auprc,'auroc':auroc,'brier':brier,'prevalence':prevalence,'brier_constant_baseline':brier_ref,'calibration_ok':brier<0.90*brier_ref})
    if not rows: raise ValueError('No event model candidate could be evaluated.')
    calibrated=[r for r in rows if r['calibration_ok']]
    pool=calibrated if calibrated else rows
    pool.sort(key=lambda r:(-r['auprc'],r['brier']))
    return pool[0]['params'],rows


def calibrate_interval_oof(train_frame,target,features,params):
    subjects=train_frame['subject_id'].dropna().unique(); n=min(3,len(subjects))
    if n<3: raise ValueError('Need at least 3 training subjects for OOF interval calibration.')
    # Patient-level calibration: avoid allowing subjects with denser CGM
    # recordings to dominate the uncertainty interval. This hierarchical
    # quantile is a conservative *empirical* method, not distribution-free
    # conformal coverage for new people.
    patient_errors={}; groups=train_frame['subject_id']
    for fold,(tr,va) in enumerate(GroupKFold(n_splits=n).split(train_frame,groups=groups),1):
        m=_new_regressor(params,300+fold); m.fit(train_frame.iloc[tr][features],train_frame.iloc[tr][target])
        valid=train_frame.iloc[va]
        pred=m.predict(valid[features])
        errors=np.abs(valid[target].to_numpy(dtype=float)-pred)
        for sid, group in pd.DataFrame({'sid':valid['subject_id'].to_numpy(), 'error':errors}).groupby('sid',observed=True):
            patient_errors.setdefault(sid,[]).extend(group['error'].tolist())
    if len(patient_errors)<3: raise ValueError('Not enough independent patients to calibrate intervals.')
    per_patient_q=[float(np.quantile(v,.80)) for v in patient_errors.values()]
    # Choose the 80th percentile of patient-level widths rather than the
    # pooled row-level percentile. Validation on unseen patients is mandatory.
    return float(np.quantile(per_patient_q,.80)),int(sum(len(v) for v in patient_errors.values()))


def _interval_holdout_metrics(holdout: pd.DataFrame, half_width: float) -> dict:
    """Report patient-level and row-level interval coverage separately.

    An interval calibrated on one cohort is not guaranteed to cover all
    patients. Do not hide poor per-subject coverage behind row counts.
    """
    errors=(holdout['truth']-holdout['prediction']).abs()
    covered=errors.le(half_width)
    by_patient={str(sid):float(covered.loc[g.index].mean()) for sid,g in holdout.groupby('subject_id',observed=True)}
    return {
        'empirical_test_coverage':float(covered.mean()),
        'macro_subject_coverage':float(np.mean(list(by_patient.values()))),
        'holdout_subject_coverage':by_patient,
        'subjects_below_75pct_coverage':int(sum(c<.75 for c in by_patient.values())),
    }


def _bootstrap_subject_gain(frame,iterations=500,seed=42):
    """95% CI for macro-subject MAE gain over each subject's best simple baseline."""
    rows=[]
    for sid,g in frame.groupby('subject_id',observed=True):
        model=mean_absolute_error(g['truth'],g['prediction']); p=mean_absolute_error(g['truth'],g['persistence']); t=mean_absolute_error(g['truth'],g['trend'])
        rows.append((sid,min(p,t)-model))
    if len(rows)<2: return None
    gains=np.asarray([r[1] for r in rows],dtype=float); rng=np.random.default_rng(seed); vals=[]
    for _ in range(iterations): vals.append(float(np.mean(rng.choice(gains,size=len(gains),replace=True))))
    return {'gain_mg_dl':float(np.mean(gains)),'ci95_low':float(np.quantile(vals,.025)),'ci95_high':float(np.quantile(vals,.975)),'subjects':len(rows)}


def _feature_defaults(frame,features):
    out={}
    for c in features:
        s=pd.to_numeric(frame[c],errors='coerce'); m=s.median(); out[c]=float(m) if pd.notna(m) else 0.0
    return out


def train(data_dir,out_dir):
    data,bio=build_dataset(data_dir); out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    train_ids,test_ids=split_subjects(bio); train_df=data[data.subject_id.isin(train_ids)].copy(); test_df=data[data.subject_id.isin(test_ids)].copy()
    results={'design':{'primary_cohort':'CGMacros','split':'locked subject-level ~20% holdout stratified within each glycemic group','train_subjects':sorted(train_ids),'test_subjects':sorted(test_ids),'event_definition':'new glucose excursion >180 mg/dL within 120 minutes while current glucose <=180 mg/dL','event_threshold_source':'standard CGM time-above-range threshold','no_random_row_split':True,'deployment_training_policy':'training-subject-only: saved fitted model is the model evaluated on untouched holdout; no post-evaluation refit on holdout','model_selection':'subject-grouped CV on training subjects only','glycemic_group_source_counts':bio['glycemic_group_source'].value_counts(dropna=False).to_dict()},'forecast':{},'event':{},'transport':{'purpose':'modality-matched CGM/phenotype model for Shanghai external validation','features':TRANSPORT_FEATURES,'forecast':{},'event':{}}}

    for h in HORIZONS:
        cols=list(dict.fromkeys(FEATURES+[f'y{h}','subject_id','glycemic_group','timestamp']))
        tr=_eligible_rows(train_df[cols],f'y{h}'); te=_eligible_rows(test_df[cols],f'y{h}')
        params,selection=_select_regressor(tr,f'y{h}',FEATURES); model=_new_regressor(params).fit(tr[FEATURES],tr[f'y{h}']); pred=model.predict(te[FEATURES])
        persistence=te.glucose.to_numpy(); trend=np.clip(te.glucose.to_numpy()+te.slope_15.fillna(0).to_numpy()*h,40,400)
        keep=['subject_id','timestamp','glucose',f'y{h}','carbs_active_g','activity']; holdout=te[keep].copy(); holdout['prediction']=pred; holdout['persistence']=persistence; holdout['trend']=trend; holdout=holdout.rename(columns={f'y{h}':'truth'})
        imodel=regression_metrics(holdout.truth,holdout.prediction); ibase=regression_metrics(holdout.truth,holdout.persistence)
        half,ncal=calibrate_interval_oof(tr,f'y{h}',FEATURES,params); interval_check=_interval_holdout_metrics(holdout,half)
        res={'selected_params':params,'training_cv_candidates':selection,'model':imodel,'persistence_baseline':ibase,'linear_trend_baseline':regression_metrics(holdout.truth,holdout.trend),'mae_macro_subject':macro_subject_mae(holdout,'truth','prediction'),'persistence_mae_macro_subject':macro_subject_mae(holdout,'truth','persistence'),'trend_mae_macro_subject':macro_subject_mae(holdout,'truth','trend'),'improvement_vs_persistence_pct':float(100*(ibase['mae']-imodel['mae'])/max(1e-9,ibase['mae'])),'macro_subject_gain_vs_best_baseline_ci95':_bootstrap_subject_gain(holdout),'personalization':personalization_from_oof(holdout, horizon_minutes=h),'uncertainty':{'method':'subject-grouped OOF per-patient 80pct residual quantile, 80pct between-patient quantile (empirical; no formal coverage guarantee)','nominal_coverage':.80,'half_width_mg_dl':half,'calibration_n':ncal,**interval_check},'n':int(len(te))}
        t2d=te.glycemic_group=='T2D'
        if t2d.any(): res['t2d_holdout']=regression_metrics(te.loc[t2d,f'y{h}'],pred[t2d.to_numpy()])|{'n':int(t2d.sum()),'subjects':int(te.loc[t2d,'subject_id'].nunique())}
        results['forecast'][str(h)]=res
        deploy=model; defaults=_feature_defaults(tr,FEATURES)
        joblib.dump({'model':deploy,'features':FEATURES,'horizon':h,'feature_defaults':defaults,'training_cohort':'CGMacros','evaluation':'locked subject holdout after training-only grouped model selection','selected_params':params,'deployment_training_policy':'training-subject-only; frozen evaluated fitted model', 'training_subject_ids':sorted(train_ids),'excluded_holdout_subject_ids':sorted(test_ids),'interval_half_width_80':half,'interval_nominal_coverage':.80,'interval_method':'subject-grouped OOF patient-balanced empirical residual quantile on training subjects'},out/f'forecast_{h}.joblib')

        # Modality-matched transport model uses the training-selected complexity from the
        # same horizon. We do not retune on a second feature subset, avoiding redundant
        # optimization and keeping Shanghai fully external.
        tparams=params; tmodel=_new_regressor(tparams).fit(tr[TRANSPORT_FEATURES],tr[f'y{h}']); tpred=tmodel.predict(te[TRANSPORT_FEATURES])
        thalf,tncal=calibrate_interval_oof(tr,f'y{h}',TRANSPORT_FEATURES,tparams); tcheck=_interval_holdout_metrics(pd.DataFrame({'truth':te[f'y{h}'],'prediction':tpred,'subject_id':te.subject_id}),thalf)
        results['transport']['forecast'][str(h)]={'selected_params':tparams,'selection_policy':'reuse primary horizon parameters selected on training subjects','locked_holdout':regression_metrics(te[f'y{h}'],tpred),'persistence':regression_metrics(te[f'y{h}'],persistence),'uncertainty':{'method':'subject-grouped patient-balanced OOF transport residual quantile (empirical; no coverage guarantee)','nominal_coverage':.80,'half_width_mg_dl':thalf,'calibration_n':tncal,'cgmacros_locked_holdout_coverage':tcheck['empirical_test_coverage'],'cgmacros_locked_holdout_macro_subject_coverage':tcheck['macro_subject_coverage']}}
        tdeploy=tmodel
        joblib.dump({'model':tdeploy,'features':TRANSPORT_FEATURES,'horizon':h,'feature_defaults':_feature_defaults(tr,TRANSPORT_FEATURES),'training_cohort':'CGMacros','evaluation':'modality-matched transport model; external target ShanghaiT2DM','selected_params':tparams,'deployment_training_policy':'training-subject-only; frozen evaluated fitted model','training_subject_ids':sorted(train_ids),'excluded_holdout_subject_ids':sorted(test_ids),'interval_half_width_80':thalf,'interval_nominal_coverage':.80,'interval_method':'subject-grouped patient-balanced OOF transport residual quantile on CGMacros training subjects'},out/f'transport_forecast_{h}.joblib')

    ecols=list(dict.fromkeys(FEATURES+['event_120','subject_id','glycemic_group','timestamp'])); etr=_eligible_rows(train_df[ecols],'event_120'); ete=_eligible_rows(test_df[ecols],'event_120')
    eparams,eselection=_select_event_model(etr,FEATURES); eoof=_event_oof_probabilities(etr,FEATURES,eparams); alert_selection=_select_alert_threshold(eoof)
    emodel=_new_event_model(eparams).fit(etr[FEATURES],etr.event_120.astype(int)); p=emodel.predict_proba(ete[FEATURES])[:,1]; y=ete.event_120.astype(int).to_numpy()
    results['event']['selected_params']=eparams; results['event']['training_cv_candidates']=eselection; results['event']['alert_threshold_selection']=alert_selection; results['event']['holdout']=event_metrics(y,p,alert_selection['threshold']); results['event']['holdout']['current_glucose_auroc_baseline']=_safe_auc(y,ete.glucose.to_numpy()); results['event']['episode_warning']=_episode_warning_metrics(test_df,ete,p,alert_selection['threshold'])
    t2d=ete.glycemic_group=='T2D'
    if t2d.any(): results['event']['t2d_holdout']=event_metrics(ete.loc[t2d,'event_120'].astype(int).to_numpy(),p[t2d.to_numpy()])|{'subjects':int(ete.loc[t2d,'subject_id'].nunique())}
    edeploy=emodel
    joblib.dump({'model':edeploy,'features':FEATURES,'feature_defaults':_feature_defaults(etr,FEATURES),'threshold_mg_dl':180,'event_horizon_min':120,'event_definition':'new excursion onset from current glucose <=180 mg/dL','training_cohort':'CGMacros','evaluation':'locked subject holdout after training-only grouped model selection','selected_params':eparams,'deployment_training_policy':'training-subject-only; frozen evaluated fitted model','training_subject_ids':sorted(train_ids),'excluded_holdout_subject_ids':sorted(test_ids),'alert_probability_threshold':alert_selection['threshold'],'alert_threshold_selection':alert_selection},out/'event_120.joblib')

    teparams=eparams; temodel=_new_event_model(teparams).fit(etr[TRANSPORT_FEATURES],etr.event_120.astype(int)); tp=temodel.predict_proba(ete[TRANSPORT_FEATURES])[:,1]
    results['transport']['event']={'selected_params':teparams,'selection_policy':'reuse primary event parameters selected on training subjects','locked_holdout':event_metrics(y,tp,alert_selection['threshold'])}
    tedeploy=temodel
    joblib.dump({'model':tedeploy,'features':TRANSPORT_FEATURES,'feature_defaults':_feature_defaults(etr,TRANSPORT_FEATURES),'threshold_mg_dl':180,'event_horizon_min':120,'event_definition':'new excursion onset from current glucose <=180 mg/dL','training_cohort':'CGMacros','evaluation':'modality-matched transport model; external target ShanghaiT2DM','selected_params':teparams,'deployment_training_policy':'training-subject-only; frozen evaluated fitted model','training_subject_ids':sorted(train_ids),'excluded_holdout_subject_ids':sorted(test_ids),'alert_probability_threshold':alert_selection['threshold']},out/'transport_event_120.joblib')

    (out/'metrics.json').write_text(json.dumps(results,indent=2,allow_nan=False)); return results


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data-dir',required=True); ap.add_argument('--out',default='models/clinical'); args=ap.parse_args(); print(json.dumps(train(args.data_dir,args.out),indent=2,allow_nan=False))
if __name__=='__main__': main()
