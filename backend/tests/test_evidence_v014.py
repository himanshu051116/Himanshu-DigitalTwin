import json
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from app.artifacts import ArtifactForecaster
from scripts.train_clinical import featurize
from scripts.training_common import personalization_from_oof
from app.main import app
from fastapi.testclient import TestClient


def test_future_labels_refuse_imputed_cgm_and_gaps():
    ts=pd.date_range('2026-01-01',periods=120,freq='5min')
    glucose=np.full(len(ts),125.,dtype=float)
    quality=['VALID']*len(ts)
    quality[60]='IMPUTED'
    x=featurize(pd.DataFrame({'timestamp':ts,'glucose':glucose,'quality':quality}))
    assert pd.isna(x.loc[40,'y120'])  # future crosses the imputed glucose
    assert pd.isna(x.loc[60,'y30'])   # a prediction cannot originate on imputed glucose
    assert pd.isna(x.loc[65,'y30'])   # missing genuine CGM lookback
    assert pd.notna(x.loc[90,'y30'])
    # A 2-hour observation gap must not be treated as one 5-minute shift.
    ts2=ts.copy().to_series().reset_index(drop=True)
    ts2.iloc[70:]+=pd.Timedelta(hours=2)
    y=featurize(pd.DataFrame({'timestamp':ts2,'glucose':glucose,'quality':['VALID']*len(ts)}))
    assert pd.isna(y.loc[69,'y30'])
    assert pd.isna(y.loc[70,'y30'])
    assert pd.notna(y.loc[100,'y30'])


def test_personalization_does_not_learn_future_truth_at_origin():
    ts=pd.date_range('2026-01-01',periods=65,freq='5min')
    # Current observed glucose stays 100, but future truth in offline labels is
    # extremely high. An incorrect causal replay would learn +35 immediately.
    d=pd.DataFrame({'subject_id':['SUBJECT-A']*65,'timestamp':ts,'glucose':[100.]*65,
                    'truth':[250.]*65,'prediction':[100.]*65,
                    'carbs_active_g':[0.]*65,'activity':[0.]*65})
    z=personalization_from_oof(d,horizon_minutes=120)
    assert z['subjects_evaluated']==1
    assert z['personalized_mae_pooled']==z['population_mae_pooled']


def test_personalization_does_not_match_skipped_due_timestamp():
    ts=pd.date_range('2026-01-01',periods=70,freq='5min')
    ts=list(ts[:25])+list(ts[26:])  # missing exact 25th observation
    d=pd.DataFrame({'subject_id':['A']*len(ts),'timestamp':ts,
                    'glucose':[110.]*len(ts),'truth':[140.]*len(ts),
                    'prediction':[100.]*len(ts),'carbs_active_g':[0.]*len(ts),'activity':[0.]*len(ts)})
    z=personalization_from_oof(d,horizon_minutes=120)
    assert z['subjects_evaluated']==1


def test_trained_pipeline_preserves_nan_until_its_own_imputer(tmp_path):
    X=pd.DataFrame({'glucose':[1.,3.,5.],'optional':[1.,3.,5.]})
    model=Pipeline([('imputer',SimpleImputer(strategy='median')),('regressor',LinearRegression())]).fit(X,[1.,3.,5.])
    art={'model':model,'features':['glucose','optional'],'feature_defaults':{'glucose':999.,'optional':999.},'interval_half_width_80':12.}
    for h in (30,60,120):joblib.dump({**art,'horizon':h},tmp_path/f'forecast_{h}.joblib')
    runtime=ArtifactForecaster(tmp_path)
    row=runtime._row(art,{'glucose':5,'optional':None},{})
    assert np.isnan(row.loc[0,'optional'])
    assert runtime.interval_half_width(30) is None


def test_research_evidence_does_not_activate_model():
    c=TestClient(app)
    a=c.get('/api/research/evidence')
    assert a.status_code==200
    z=a.json()
    assert z['research_only'] is True
    assert z['active_model_unchanged'] is True
    assert z['data']['participant_files']==45
    assert z['data']['not_the_canonical_training_pipeline'] is True
    status=c.get('/api/model/status').json()
    assert status['independent_research_evidence_available'] is True
    assert status['runtime_promotion_allowed'] is False


def test_resampling_does_not_move_meals_or_future_glucose_backward(tmp_path):
    from app.cgmacros import load_cgmacros_subject
    p=tmp_path/'CGMacros-003.csv'
    pd.DataFrame({
        'Timestamp':['2026-01-01 08:00','2026-01-01 08:04','2026-01-01 08:06'],
        'Dexcom GL':[100,140,170],
        'HR':[70,73,80],
        'Mets':[11,14,20],
        'Carbs':[0,48,0],
    }).to_csv(p,index=False)
    d=load_cgmacros_subject(p)
    first=d.loc[d.timestamp==pd.Timestamp('2026-01-01 08:00')].iloc[0]
    second=d.loc[d.timestamp==pd.Timestamp('2026-01-01 08:05')].iloc[0]
    later=d.loc[d.timestamp==pd.Timestamp('2026-01-01 08:10')].iloc[0]
    assert first.glucose==100
    assert first.carbs_active_g==0
    assert second.glucose==140
    assert second.carbs_active_g>=48
    assert later.glucose==170


def test_intensity_only_activity_is_flagged_not_treated_as_mets(tmp_path):
    from scripts.preflight_data import audit_cgmacros
    from app.cgmacros import load_cgmacros_subject
    p=tmp_path/'CGMacros-033.csv'
    pd.DataFrame({'Timestamp':['2026-01-01 08:00','2026-01-01 08:05'],
                  'Dexcom GL':[120,125],'HR':[70,72], 'Intensity':[10,20],
                  'Carbs':[0,0]}).to_csv(p,index=False)
    audit=audit_cgmacros(tmp_path)
    assert audit['schema_failures']==[]
    assert 'CGMacros-033.csv' in audit['activity_intensity_only_subjects']
    df=load_cgmacros_subject(p)
    assert df.activity.isna().all()


def test_retraining_fails_closed_after_exception(tmp_path,monkeypatch):
    import pytest
    from scripts import train_submission as sub
    monkeypatch.setattr(sub,'audit_cgmacros',lambda root: {'ready_for_final_primary_training':True})
    def train_fail(*args,**kwargs): raise RuntimeError('aborted before model publication')
    monkeypatch.setattr(sub,'train',train_fail)
    out=tmp_path/'models';out.mkdir();(out/'promotion.json').write_text('{'+'"status":"PASS","runtime_promotion_allowed":true'+'}')
    with pytest.raises(RuntimeError,match='aborted'):
        sub.run(tmp_path,out,tmp_path/'evidence.json')
    state=json.loads((out/'promotion.json').read_text())
    assert state['status']=='TRAINING'
    assert state['runtime_promotion_allowed'] is False
