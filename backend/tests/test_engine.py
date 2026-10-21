from app.data import generate_demo_patients
from app.engine import ReplaySession

def make_session():
    p=generate_demo_patients()['HDT-027']
    return ReplaySession('HDT-027',p.profile,p.stream)

def test_twin_version_increments():
    s=make_session(); a=s.step(1); b=s.step(2)
    assert a['twin_version']==1
    assert b['twin_version']==3

def test_forecast_horizons_and_intervals():
    s=make_session(); snap=s.step(8)
    assert [x['horizon_min'] for x in snap['forecasts']]==[30,60,120]
    assert all(x['lower'] <= x['personalized'] <= x['upper'] for x in snap['forecasts'])

def test_missing_sensor_degrades_not_crashes():
    s=make_session(); snap=s.step(88)  # reaches missing region around 14:10
    assert snap['reading']['glucose'] is not None
    assert snap['reading']['quality'] in {'VALID','MISSING','IMPUTED','OUTLIER'}

def test_online_adapter_resolves_forecasts():
    s=make_session(); snap=s.step(40)
    assert snap['model_metrics']['resolved_forecasts'] > 0
    assert snap['model_metrics']['population_mae'] != 'collecting'

def test_scenario_does_not_mutate_twin_version():
    s=make_session(); snap=s.step(20); version=snap['twin_version']
    base, changed=s.scenario(carbs_g=100,activity=.05)
    assert s.twin_version==version
    assert base != changed

def test_snapshot_preserves_degraded_confidence():
    s=make_session(); snap=s.step(88)
    # snapshot() must not overwrite sensor-quality-derived confidence with an unconditional HIGH.
    again=s.snapshot()
    if again['reading']['quality']=='MISSING':
        assert again['confidence']=='LOW'

def test_runtime_feature_schema_contains_training_variability_features():
    s=make_session(); s.step(15)
    f=s._features(s.history[-1])
    assert 'std60' in f and 'cv60' in f and 'heart_rate' in f and 'minutes_since_meal' in f

def test_personal_adapter_never_learns_from_missing_due_observation():
    p=generate_demo_patients()['HDT-027']
    # Force the exact 30-minute verification point after the first forecast to be missing.
    stream=[dict(x) for x in p.stream]
    stream[6]=dict(stream[6], glucose=None, truth_glucose=None, quality='MISSING')
    s=ReplaySession('HDT-027',p.profile,stream,cadence_min=5)
    s.step(7)
    due=[x for x in s.pending if x.issued_index==0 and x.horizon==30][0]
    assert due.resolved is True
    assert due.resolution_status=='SKIPPED_QUALITY'
    assert due.observed is None
    assert due.residual is None
    assert s.adapter.counts['baseline'][30] + s.adapter.counts['postmeal'][30] + s.adapter.counts['active'][30] == 0
