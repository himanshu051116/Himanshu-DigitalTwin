from pathlib import Path
import joblib
import pandas as pd
from sklearn.dummy import DummyRegressor, DummyClassifier
from app.artifacts import ArtifactForecaster

FEATURES=['glucose','slope_15','roll30','roll60','std60','carbs_active_g','activity','hour_sin','hour_cos','age','bmi','hba1c','fasting_glucose']

def test_artifact_forecaster_contract(tmp_path):
    x=pd.DataFrame([{f:1.0 for f in FEATURES},{f:2.0 for f in FEATURES}])
    for h,value in [(30,130),(60,145),(120,160)]:
        m=DummyRegressor(strategy='constant',constant=value).fit(x,[value,value])
        joblib.dump({'model':m,'features':FEATURES,'horizon':h,'imputation':{f:0 for f in FEATURES},'source':'unit-test','validation':'grouped'},tmp_path/f'forecast_{h}.joblib')
    risk=DummyClassifier(strategy='constant',constant=1).fit(x,[0,1])
    joblib.dump({'model':risk,'features':FEATURES,'imputation':{f:0 for f in FEATURES},'source':'unit-test','validation':'grouped'},tmp_path/'risk_120.joblib')
    model=ArtifactForecaster(tmp_path)
    features={'glucose':120,'slope_15':0,'roll30':120,'roll60':120,'std60':2,'carbs_active_g':20,'activity':.1,'hour_sin':0,'hour_cos':1}
    profile={'age':50,'bmi':30,'hba1c':8,'fasting_glucose':120}
    assert round(model.forecast(features,profile,60))==145
    p=model.excursion_probability([130,145,160],features,profile)
    assert 0 <= p <= 1

def test_hba1c_missing_indicator_handles_nan(tmp_path):
    features=['glucose','hba1c','hba1c_missing']
    x=pd.DataFrame([[120,7,0],[150,8,0]],columns=features)
    for h in (30,60,120):
        m=DummyRegressor(strategy='mean').fit(x,[130,160])
        joblib.dump({'model':m,'features':features,'horizon':h,'imputation':{'glucose':120,'hba1c':7.5,'hba1c_missing':0},'source':'unit','validation':'grouped'},tmp_path/f'forecast_{h}.joblib')
    model=ArtifactForecaster(tmp_path)
    row=model._row(model.forecast_artifacts[30],{'glucose':130},{'hba1c':float('nan')})
    assert row.iloc[0]['hba1c_missing']==1.0


def test_transport_artifact_forecaster_uses_transport_files(tmp_path):
    from app.artifacts import TransportArtifactForecaster
    features=['glucose','slope_15','roll30','roll60','cv60','hour_sin','hour_cos','age','hba1c']
    x=pd.DataFrame([{f:1.0 for f in features},{f:2.0 for f in features}])
    for h,value in [(30,131),(60,146),(120,161)]:
        m=DummyRegressor(strategy='constant',constant=value).fit(x,[value,value])
        joblib.dump({'model':m,'features':features,'horizon':h,'feature_defaults':{f:0 for f in features},'training_cohort':'CGMacros','evaluation':'transport','interval_half_width_80':12.0},tmp_path/f'transport_forecast_{h}.joblib')
    risk=DummyClassifier(strategy='constant',constant=1).fit(x,[0,1])
    joblib.dump({'model':risk,'features':features,'feature_defaults':{f:0 for f in features},'alert_probability_threshold':.35},tmp_path/'transport_event_120.joblib')
    model=TransportArtifactForecaster(tmp_path)
    assert model.personalization_enabled is False
    assert model.interval_label=='heuristic-fallback-uncalibrated'
    assert model.interval_half_width(60) is None
    assert model.alert_probability_threshold==.35
    pred=model.forecast({'glucose':120,'slope_15':0,'roll30':120,'roll60':120,'cv60':.05,'hour_sin':0,'hour_cos':1},{'age':50,'hba1c':8},60)
    assert round(pred)==146


def test_external_interval_can_be_enabled_without_primary_interval_gate(tmp_path):
    from app.artifacts import TransportArtifactForecaster
    f=['glucose']
    from sklearn.dummy import DummyRegressor
    x=pd.DataFrame({'glucose':[120,130,140]})
    y=[121,131,141]
    for h in (30,60,120):
        m=DummyRegressor().fit(x,y)
        joblib.dump({'model':m,'features':f,'horizon':h,'interval_half_width_80':9.},tmp_path/f'transport_forecast_{h}.joblib')
    import hashlib
    risk=DummyClassifier(strategy='constant',constant=1).fit(x,[0,1,1])
    joblib.dump({'model':risk,'features':f},tmp_path/'transport_event_120.joblib')
    names=[f'transport_forecast_{h}.joblib' for h in (30,60,120)]+['transport_event_120.joblib']
    (tmp_path/'promotion.json').write_text(__import__('json').dumps({
        'status':'PASS','runtime_promotion_allowed':False,
        'runtime_interval_allowed':False,
        'runtime_external_transport_allowed':True,
        'external_interval_validated':True,
        'artifact_sha256':{n:hashlib.sha256((tmp_path/n).read_bytes()).hexdigest() for n in names}
    }))
    m=TransportArtifactForecaster(tmp_path)
    assert m.interval_half_width(60)==9.0
    assert m.interval_label=='empirical-80pct-CGMacros-transport-calibrated'


def test_integrity_guard_rejects_changed_model_even_with_pass_marker(tmp_path):
    from app.artifacts import verify_promotion_gate
    from scripts.submission_gate import stamp_artifact_hashes
    names=[f'forecast_{h}.joblib' for h in (30,60,120)]+['event_120.joblib']
    for name in names: (tmp_path/name).write_bytes(('original '+name).encode())
    gate=stamp_artifact_hashes({'status':'PASS','runtime_promotion_allowed':True,
                                'runtime_personalization_allowed':True,'runtime_interval_allowed':True},tmp_path)
    assert verify_promotion_gate(tmp_path,gate)['runtime_promotion_allowed'] is True
    (tmp_path/'forecast_60.joblib').write_bytes(b'changed after approval')
    blocked=verify_promotion_gate(tmp_path,gate)
    assert blocked['status']=='INVALID_INTEGRITY'
    assert blocked['runtime_promotion_allowed'] is False
    assert blocked['runtime_personalization_allowed'] is False
    assert blocked['runtime_interval_allowed'] is False

def test_integrity_guard_rejects_unhashed_legacy_pass_marker(tmp_path):
    from app.artifacts import verify_promotion_gate
    old_gate={'status':'PASS','runtime_promotion_allowed':True}
    blocked=verify_promotion_gate(tmp_path,old_gate)
    assert blocked['status']=='INVALID_INTEGRITY'
    assert blocked['runtime_promotion_allowed'] is False
