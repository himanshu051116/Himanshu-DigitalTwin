"""Submission walkthrough must be deterministic, bounded and honestly synthetic."""
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)


def test_demo_chapters_are_public_and_synthetic():
    r=c.get('/api/demo/chapters')
    assert r.status_code == 200
    data=r.json()
    assert data['simulation_only'] is True
    assert len(data['chapters']) == 6
    assert data['chapters'][0]['id'] == 'baseline'


def test_guided_replay_is_deterministic_and_does_not_promote_models():
    first=c.post('/api/demo/chapter/lunch').json()
    second=c.post('/api/demo/chapter/lunch').json()
    assert first['simulation_only'] and second['simulation_only']
    assert first['snapshot']['timestamp'] == second['snapshot']['timestamp']
    assert first['snapshot']['reading'] == second['snapshot']['reading']
    assert first['snapshot']['twin_version'] == second['snapshot']['twin_version']
    assert first['snapshot']['patient']['patient_id'] == 'HDT-027'
    assert c.get('/api/model/status').json()['runtime_promotion_allowed'] is False


def test_guided_replay_shows_valid_future_audit_and_sensor_quality():
    replay=c.post('/api/demo/chapter/verification').json()['snapshot']
    assert replay['model_metrics']['resolved_forecasts'] > 0
    gap=c.post('/api/demo/chapter/sensor_gap').json()['snapshot']
    assert gap['reading']['quality'] == 'IMPUTED'
    assert gap['forecast_status'] == 'ABSTAINED'
    assert gap['excursion_risk'] is None
    assert gap['forecasts'] == []
    recovery=c.post('/api/demo/chapter/recovery').json()['snapshot']
    assert recovery['forecast_status'] == 'AVAILABLE'


def test_demo_chapters_deny_real_patient_and_unknown_chapter():
    assert c.post('/api/demo/chapter/unknown').status_code == 404
    assert c.post('/api/demo/chapter/lunch?patient_id=CGM-001').status_code == 400
