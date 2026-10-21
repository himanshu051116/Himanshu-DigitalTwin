"""v0.16 fail-closed training and no-risk-on-stale-sensor regressions."""
import json
import pandas as pd
import pytest

from app.data import generate_demo_patients
from app.engine import ReplaySession
from scripts.submission_gate import evaluate_evidence
from scripts.train_submission import run
from test_submission_gate import _evidence


def _stream(values):
    base=generate_demo_patients()['HDT-027']
    t=pd.date_range('2026-10-12 09:00',periods=len(values),freq='5min')
    stream=[]
    for timestamp,value in zip(t,values):
        stream.append({'timestamp':timestamp.isoformat(),'quality':'VALID' if value is not None else 'MISSING',
            'glucose':value,'carbs_active_g':0.,'activity':0.,'heart_rate':75.,'minutes_since_meal':None,
            'steps_5m':10,'provenance':{'stream':'unit-test'}})
    return ReplaySession('TEST',base.profile,stream)


def test_stale_glucose_abstains_and_does_not_emit_false_zero_risk():
    s=_stream([125]+[None]*6)
    a=s.step(4)  # 15 minutes from the genuine observation: still allowed with low confidence.
    assert a['forecast_status']=='AVAILABLE'
    b=s.step(1)  # 20 minutes: no forecast or risk supported.
    assert b['forecast_status']=='ABSTAINED'
    assert b['excursion_risk'] is None
    assert b['risk_mode']=='sensor-stale'
    assert b['forecasts']==[]
    assert b['reading']['glucose'] is None
    assert b['explanations']==[]
    assert b['minutes_since_last_valid_glucose']==20
    assert b['sync_status']=='DEGRADED'
    assert b['alert_state']=='SENSOR STALE — UNAVAILABLE'
    assert s.scenario(carbs_g=60)==([],[])
    count=len(s.pending)
    s.step(1)
    assert len(s.pending)==count  # Don't issue new forecasts with stale glucose.


def test_stale_sensor_recovers_without_reusing_missed_glucose_truth():
    s=_stream([115]+[None]*5+[132,135])
    lost=s.step(6)
    assert lost['forecast_status']=='ABSTAINED'
    recovered=s.step(1)
    assert recovered['forecast_status']=='AVAILABLE'
    assert recovered['minutes_since_last_valid_glucose']==0
    assert recovered['reading']['quality']=='VALID'
    assert len(recovered['forecasts'])==3


def test_no_initial_valid_reading_abstains():
    s=_stream([None]*5)
    a=s.step()
    assert a['forecast_status']=='ABSTAINED'
    assert a['excursion_risk'] is None
    assert a['forecasts']==[]
    assert a['minutes_since_last_valid_glucose'] is None


def test_active_hyperglycemia_is_not_future_event_probability():
    s=_stream([195,200])
    a=s.step()
    assert a['alert_state']=='ACTIVE EXCURSION'
    assert a['risk_mode']=='active-excursion'
    assert a['excursion_risk'] is None
    assert len(a['forecasts'])==3
    assert s.snapshot()['excursion_risk'] is None


def test_failed_primary_preflight_revokes_old_promotion(tmp_path):
    out=tmp_path/'models'; out.mkdir()
    (out/'promotion.json').write_text(json.dumps({'status':'PASS','runtime_promotion_allowed':True}))
    with pytest.raises(ValueError,match='preflight failed'):
        run(tmp_path/'missing-cgmacros',out,tmp_path/'reports'/'evidence.json')
    marker=json.loads((out/'promotion.json').read_text())
    assert marker['status']=='TRAINING'
    assert marker['runtime_promotion_allowed'] is False
    assert marker['runtime_external_transport_allowed'] is False


def test_personalization_is_not_globally_approved_from_one_horizon():
    e=_evidence()
    e['primary']['forecast']['30']['personalization']['subjects_improved_fraction']=0.3
    gate=evaluate_evidence(e)
    assert gate['runtime_promotion_allowed'] is True
    assert gate['runtime_personalization_allowed'] is False


def _external_evidence():
    e=_evidence()
    e['external']={'subjects':100,'forecast':{
        str(h):{'improvement_vs_persistence_pct':8,'mae_macro_subject':12,
                 'persistence_mae_macro_subject':15,
                 'prediction_interval_80':{'external_empirical_coverage':0.8}}
        for h in (30,60,120)},
        'event_120':{'auroc':0.75,'current_glucose_auroc_baseline':0.65,
                     'event_rate':0.2,'brier':0.12}}
    return e


def test_external_gate_requires_external_preflight_even_if_metrics_good():
    e=_external_evidence()
    gate=evaluate_evidence(e)
    assert gate['runtime_promotion_allowed'] is True
    assert gate['runtime_external_transport_allowed'] is False
    assert any(c['name']=='complete_real_external_cohort' and not c['passed']
               for c in gate['external_summary']['checks'])
    e['data_preflight']['shanghai']={'ready_for_external_validation':True}
    good=evaluate_evidence(e)
    assert good['runtime_external_transport_allowed'] is True
    e['development_smoke_override_used']=True
    assert evaluate_evidence(e)['runtime_external_transport_allowed'] is False


def test_external_gate_rejects_bad_primary_preflight_even_when_external_complete():
    e=_external_evidence()
    e['data_preflight']['shanghai']={'ready_for_external_validation':True}
    e['data_preflight']['cgmacros']={'ready_for_final_primary_training':False}
    gate=evaluate_evidence(e)
    assert gate['runtime_external_transport_allowed'] is False


def test_trained_forecaster_requires_consecutive_60min_warmup():
    from app.model import PopulationForecaster
    s=_stream([112.]*14)
    trained=PopulationForecaster(); trained.is_trained=True
    s.model=trained
    early=s.step(12)
    assert early['forecast_status']=='ABSTAINED'
    assert early['risk_mode']=='warmup'
    assert early['confidence']=='LOW'
    assert early['alert_state']=='WARMING UP — UNAVAILABLE'
    assert early['consecutive_valid_glucose_samples']==12
    assert early['forecasts']==[]
    assert early['reading']['glucose'] is None
    ready=s.step(1)
    assert ready['consecutive_valid_glucose_samples']==13
    assert ready['forecast_status']=='AVAILABLE'
    assert len(ready['forecasts'])==3


def test_trained_forecaster_restarts_warmup_after_missing_and_timestamp_gap():
    from app.model import PopulationForecaster
    s=_stream([112.]*14+[None]+[113.]*14)
    trained=PopulationForecaster(); trained.is_trained=True
    s.model=trained
    s.step(13)
    assert s.snapshot()['forecast_status']=='AVAILABLE'
    s.step(1)  # 14th good sample
    broken=s.step(1)
    assert broken['forecast_status']=='ABSTAINED'
    assert broken['consecutive_valid_glucose_samples']==0
    first=s.step(1)
    assert first['forecast_status']=='ABSTAINED' and first['consecutive_valid_glucose_samples']==1
    recovered=s.step(12)
    assert recovered['forecast_status']=='AVAILABLE'
    assert recovered['consecutive_valid_glucose_samples']==13
    # Force a clock gap despite all glucose values being valid.
    later=_stream([112.]*15)
    later.model=trained
    later.stream[13]['timestamp']='2026-10-12T10:09:00'
    later.stream[14]['timestamp']='2026-10-12T10:14:00'
    later.step(13)
    assert later.snapshot()['forecast_status']=='AVAILABLE'
    later.step()
    assert later.snapshot()['forecast_status']=='ABSTAINED'


def test_shanghai_imputed_glucose_never_becomes_external_truth(tmp_path):
    import numpy as np
    from scripts.validate_external import _featurize
    from app.shanghai import load_shanghai_metadata
    t=pd.date_range('2026-01-01 00:00',periods=55,freq='15min')
    g=115+np.sin(np.arange(55)/5)*15
    g[20]=np.nan  # single missing sample is interpolated in adapter
    pd.DataFrame({'timestamp':t,'glucose_value_mg_dl':g}).to_csv(tmp_path/'2000.csv',index=False)
    meta=load_shanghai_metadata(__import__('pathlib').Path(__file__).resolve().parents[1]/'data/reference/shanghai_t2dm_metadata.csv')
    z=_featurize(tmp_path/'2000.csv',meta)
    gap=t[20]
    assert gap not in set(z['timestamp'])
    # No labelled example with 120-minute target crossing an interpolated gap.
    before=z[(z.timestamp>=gap-pd.Timedelta(minutes=120))&(z.timestamp<gap)]
    assert before['valid_y120'].fillna(False).sum()==0
    assert before['event120'].notna().sum()==0
    assert z['event120'].notna().any()


def test_external_validation_refuses_multimodal_fallback(tmp_path):
    from pathlib import Path
    from scripts.validate_external import evaluate
    metadata=Path(__file__).resolve().parents[1]/'data/reference/shanghai_t2dm_metadata.csv'
    data=tmp_path/'shanghai'; data.mkdir()
    times=pd.date_range('2026-01-01',periods=45,freq='15min')
    for sid in (2000,2001):
        pd.DataFrame({'timestamp':times,'glucose_value_mg_dl':[125.]*45}).to_csv(data/f'{sid}.csv',index=False)
    with pytest.raises(FileNotFoundError,match='dedicated Shanghai transport model'):
        evaluate(tmp_path/'models',data,metadata)


def test_external_pipeline_does_not_preimpute_missing_modalities():
    import numpy as np
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.dummy import DummyRegressor
    from scripts.validate_external import _matrix
    art={'features':['age','hba1c'],
         'feature_defaults':{'age':57,'hba1c':7.2},
         'model':Pipeline([('imputer',SimpleImputer(strategy='median')),('model',DummyRegressor())])}
    frame=pd.DataFrame({'age':[40], 'hba1c':[np.nan]})
    x=_matrix(frame,art)
    assert pd.isna(x.loc[0,'hba1c'])
    legacy={**art,'model':DummyRegressor()}
    assert _matrix(frame,legacy).loc[0,'hba1c']==7.2
