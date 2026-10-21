from pathlib import Path
import joblib
import numpy as np
import pandas as pd

from app.artifacts import ArtifactForecaster
from scripts.train_clinical import train


def _write_subject(root: Path, sid: int, hba1c: float, phase: float):
    n = 220
    ts = pd.date_range('2026-01-01 06:00', periods=n, freq='5min')
    t = np.arange(n)
    base = 105 + (hba1c - 5.5) * 10
    # reproducible meal-like excursions; high-HbA1c subjects cross 180.
    glucose = base + 10*np.sin(t/18 + phase) + 55*np.exp(-((t-55)/15)**2) + 62*np.exp(-((t-150)/18)**2)
    carbs = np.zeros(n); carbs[48] = 55 + sid % 10; carbs[143] = 70
    mets = 12 + 15*np.exp(-((t-100)/20)**2)
    hr = 68 + (mets-10)*0.8
    df = pd.DataFrame({
        'Timestamp': ts,
        'Dexcom GL': glucose,
        'HR': hr,
        'Mets': mets,
        'Calories (Activity)': 0.2,
        'Meal Type': [pd.NA]*n,
        'Calories': np.where(carbs>0, 500, 0),
        'Carbs': carbs,
        'Protein': np.where(carbs>0, 25, 0),
        'Fat': np.where(carbs>0, 18, 0),
        'Fiber': np.where(carbs>0, 7, 0),
        'Amount Consumed': np.where(carbs>0, 100, np.nan),
    })
    df.loc[48, 'Meal Type'] = 'Breakfast'; df.loc[143, 'Meal Type'] = 'Lunch'
    d = root / f'CGMMacros-{sid:03d}'; d.mkdir(parents=True, exist_ok=True)
    df.to_csv(d / f'CGMacros-{sid:03d}.csv', index=False)


def test_train_and_runtime_artifacts(tmp_path):
    rows=[]
    hbas=[5.2,5.4,5.5,5.6,5.8,6.0,6.2,6.4,7.0,7.5,8.0,8.5,9.0,9.5,10.0]
    for sid,h in enumerate(hbas, start=1):
        _write_subject(tmp_path, sid, h, sid/5)
        rows.append({'Subject':sid,'Age':30+sid,'Gender':'M' if sid%2 else 'F','BMI':23+sid*.5,'HbA1c':h,'Fasting Glucose':95+(h-5)*10})
    pd.DataFrame(rows).to_csv(tmp_path/'bio.csv', index=False)
    out=tmp_path/'models'
    metrics=train(tmp_path,out)
    assert metrics['design']['no_random_row_split'] is True
    assert metrics['design']['deployment_training_policy'].startswith('training-subject-only')
    assert (out/'forecast_30.joblib').exists()
    # The *saved* candidate must be exactly the fitted model used to evaluate
    # untouched test subjects, not a post-evaluation refit on the test people.
    from scripts.train_clinical import build_dataset,split_subjects,_eligible_rows,FEATURES
    from sklearn.metrics import mean_absolute_error
    data,bio=build_dataset(tmp_path)
    training,test=split_subjects(bio)
    for horizon in (30,60,120):
        art=joblib.load(out/f'forecast_{horizon}.joblib')
        assert set(art['training_subject_ids'])==training
        assert set(art['excluded_holdout_subject_ids'])==test
        work=_eligible_rows(data[data.subject_id.isin(test)],f'y{horizon}')
        pred=art['model'].predict(work[FEATURES])
        assert abs(mean_absolute_error(work[f'y{horizon}'],pred)-metrics['forecast'][str(horizon)]['model']['mae'])<1e-8
        ci=metrics['forecast'][str(horizon)]['uncertainty']
        assert len(ci['holdout_subject_coverage'])==len(test)
        assert 0<=ci['macro_subject_coverage']<=1
    assert (out/'event_120.joblib').exists()
    assert (out/'transport_forecast_60.joblib').exists()
    assert (out/'transport_event_120.joblib').exists()
    assert metrics['design']['glycemic_group_source_counts'].get('published-CGMacros-metadata',0) > 0
    assert metrics['transport']['forecast']['60']['uncertainty']['half_width_mg_dl'] > 0
    from sklearn.metrics import brier_score_loss
    from scripts.train_clinical import FEATURES
    arisk=joblib.load(out/'event_120.joblib')
    erows=_eligible_rows(data[data.subject_id.isin(test)],'event_120')
    event_prob=arisk['model'].predict_proba(erows[FEATURES])[:,1]
    assert abs(brier_score_loss(erows['event_120'].astype(int),event_prob) - metrics['event']['holdout']['brier'])<1e-8
    assert set(arisk['excluded_holdout_subject_ids'])==test
    runtime=ArtifactForecaster(out)
    assert runtime.is_trained
    assert runtime.metadata()['mode']=='real-data-trained'
    assert runtime.interval_label=='heuristic-fallback-uncalibrated'
    assert runtime.personalization_enabled is False  # no promotion evidence marker in this unit test
    assert runtime.interval_half_width(60) is None  # holdout interval gate not approved
    features={'glucose':150,'slope_15':0.4,'roll30':145,'roll60':140,'cv60':0.08,'carbs_active_g':35,'minutes_since_meal':25,'activity':0.2,'heart_rate':80,'hour_sin':0.5,'hour_cos':0.5}
    profile={'age':55,'bmi':30,'hba1c':8.0,'fasting_glucose':130}
    pred=runtime.forecast(features,profile,60)
    risk=runtime.excursion_probability([pred],features,profile)
    assert 45 <= pred <= 400
    assert 0 <= risk <= 1


def test_interval_calibration_balances_subjects_not_rows(monkeypatch):
    import scripts.train_clinical as tc
    from sklearn.dummy import DummyRegressor
    monkeypatch.setattr(tc,'_new_regressor',lambda *args,**kwargs: DummyRegressor(strategy='constant',constant=0.))
    df=pd.DataFrame({
        'subject_id':['large']*1000+['medium']*20+['small']*20,
        'glucose':[1.]*1040,
        'truth':[0.]*1000+[10.]*20+[20.]*20,
    })
    width,n=tc.calibrate_interval_oof(df,'truth',['glucose'],{})
    assert n==len(df)
    assert width>12  # pooled row-wise 80% quantile would be zero
