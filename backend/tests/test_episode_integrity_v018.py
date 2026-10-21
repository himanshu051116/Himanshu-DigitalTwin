"""v0.18: episode and sensor-adapter adversarial regression tests."""
import numpy as np
import pandas as pd
import pytest
from app.cgmacros import load_cgmacros_subject
from scripts.train_clinical import _episode_warning_metrics


def _subject_csv(tmp_path, dex, libre):
    p=tmp_path/'CGMacros-039.csv'
    n=len(dex)
    pd.DataFrame({'Timestamp':pd.date_range('2026-01-01',periods=n,freq='1min'),
                  'Dexcom GL':dex,'Libre GL':libre,'HR':[70]*n,'METs':[12]*n,
                  'Carbs':[0]*n}).to_csv(p,index=False)
    return p


def test_sparse_dexcom_uses_complete_libre(tmp_path):
    n=750; d=[np.nan]*n; d[0]=400
    p=_subject_csv(tmp_path,d,[120]*n)
    x=load_cgmacros_subject(p)
    assert set(x.cgm_source)=={'Libre'}
    assert x.glucose.between(119,121).all()


def test_plausibility_filter_rejects_sensor_outlier(tmp_path):
    d=[120]*22;d[9]=9999
    p=_subject_csv(tmp_path,d,[np.nan]*22)
    x=load_cgmacros_subject(p,resample='1min')
    row=x.iloc[9]
    assert row.quality=='IMPUTED'
    assert row.glucose<200


def test_both_sensor_streams_invalid_fail_closed(tmp_path):
    p=_subject_csv(tmp_path,[900]*30,[1]*30)
    with pytest.raises(ValueError,match='No plausible CGM'):
        load_cgmacros_subject(p)


def test_never_splice_libre_into_dexcom_gap(tmp_path):
    d=[105,109,np.nan,113,115]
    p=_subject_csv(tmp_path,d,[170]*5)
    x=load_cgmacros_subject(p,resample='1min')
    assert set(x.cgm_source)=={'Dexcom'}
    assert x.loc[2,'quality']=='IMPUTED'
    assert x.loc[2,'glucose']!=170


def _frames(values,quality=None,probs=None):
    n=len(values);t=pd.date_range('2026-04-01 08:00',periods=n,freq='5min')
    g=pd.DataFrame({'subject_id':['s1']*n,'timestamp':t,'glucose':values,
                    'quality':quality if quality is not None else ['VALID']*n})
    indices=list(range(n))
    if probs is None:probs=[.1]*n
    eligible=g.iloc[indices].copy()
    eligible['event_120']=0
    return g,eligible,np.array(probs)


def test_no_onset_if_interpolated_crosses_threshold():
    g,e,p=_frames([120,150,185,195],['VALID','VALID','IMPUTED','VALID'],[.9]*4)
    z=_episode_warning_metrics(g,e,p,.5)
    assert z['onset_episodes']==0
    assert z['episode_detection_rate'] is None


def test_episode_count_suppresses_rapid_recrossing():
    g,e,p=_frames([170,181,179,190,177,188],[ 'VALID']*6,[.8]*6)
    z=_episode_warning_metrics(g,e,p,.5)
    assert z['onset_episodes']==1
    assert z['refractory_suppressed_crossings']==2
    assert z['evaluable_onsets']==1
    assert z['detected_onsets']==1


def test_episode_denominator_requires_prediction_window():
    g,e,p=_frames([170,181,200],probs=[.1,.1,.1])
    e=e.iloc[2:];p=p[2:]
    z=_episode_warning_metrics(g,e,p,.5)
    assert z['onset_episodes']==1
    assert z['evaluable_onsets']==0
    assert z['unevaluable_onsets']==1
    assert z['episode_detection_rate'] is None


def test_crossing_requires_five_minute_adjacency():
    g,e,p=_frames([165,185])
    g.loc[1,'timestamp']=g.loc[0,'timestamp']+pd.Timedelta(minutes=25)
    e.loc[1,'timestamp']=g.loc[1,'timestamp']
    assert _episode_warning_metrics(g,e,p,.5)['onset_episodes']==0


def test_invalid_probability_refused():
    g,e,p=_frames([165,185])
    with pytest.raises(ValueError,match='finite'):
        _episode_warning_metrics(g,e,[.1,np.nan],.5)
    with pytest.raises(ValueError,match='align'):
        _episode_warning_metrics(g,e,[.1],.5)


def test_interval_label_cannot_be_approved_without_population_gate(tmp_path):
    from app.artifacts import ArtifactForecaster, verify_promotion_gate
    import joblib, json
    from sklearn.dummy import DummyRegressor
    X=pd.DataFrame({'glucose':[100,120]}); m=DummyRegressor().fit(X,[105,125])
    for h in (30,60,120):
        joblib.dump({'model':m,'horizon':h,'features':['glucose'],
                     'interval_half_width_80':15.0},tmp_path/f'forecast_{h}.joblib')
    p={'status':'FAIL','runtime_promotion_allowed':False,
       'runtime_interval_allowed':True,'runtime_personalization_allowed':True}
    (tmp_path/'promotion.json').write_text(json.dumps(p))
    loaded=ArtifactForecaster(tmp_path)
    assert loaded.interval_half_width(30) is None
    assert loaded.interval_label=='heuristic-fallback-uncalibrated'
    assert loaded.promotion['runtime_interval_allowed'] is False
    assert loaded.personalization_enabled is False


def test_manual_github_workflow_is_fail_closed_and_no_raw_data_upload():
    from pathlib import Path
    import yaml
    path=Path(__file__).resolve().parents[2]/'.github/workflows/cgmacros-primary.yml'
    w=yaml.safe_load(path.read_text())
    job=w['jobs']['primary']; steps=job['steps']
    assert True in w or 'on' in w  # PyYAML YAML-1.1 treats "on" as true
    assert len([s for s in steps if 'scripts/train_submission.py' in s.get('run','')])==1
    assert any(s.get('id')=='train' and s.get('continue-on-error') for s in steps)
    assert any('steps.train.outcome !=' in s.get('if','') and 'exit 1' in s.get('run','') for s in steps)
    for step in steps:
        if step.get('uses','').startswith('actions/upload-artifact'):
            content=step['with']['path']
            assert 'data/raw' not in content
            assert '.csv' not in content


def test_training_marker_overrides_stale_primary_pass_flag(tmp_path):
    from app.artifacts import verify_promotion_gate
    inconsistent={'status':'TRAINING','runtime_promotion_allowed':True,
                  'runtime_interval_allowed':True,'runtime_personalization_allowed':True}
    out=verify_promotion_gate(tmp_path,inconsistent)
    assert out['runtime_promotion_allowed'] is False
    assert out['runtime_personalization_allowed'] is False
    assert out['runtime_interval_allowed'] is False
