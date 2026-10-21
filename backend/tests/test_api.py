from fastapi.testclient import TestClient
from app.main import app
c=TestClient(app)

def test_health_and_patients():
    assert c.get('/api/health').status_code==200
    p=c.get('/api/patients').json(); assert len(p)>=3

def test_replay_and_scenario():
    r=c.post('/api/replay/HDT-027/reset'); assert r.status_code==200
    s=c.post('/api/replay/HDT-027/step?steps=24').json(); assert s['twin_version']==25
    sc=c.post('/api/scenario',json={'patient_id':'HDT-027','carbs_g':120,'activity':0.1}); assert sc.status_code==200
    assert 'Not a treatment recommendation' in sc.json()['note']

def test_fhir_endpoint():
    b={'resourceType':'Bundle','entry':[{'resource':{'resourceType':'Patient','id':'abc','gender':'female'}}]}
    r=c.post('/api/fhir/ingest',json=b); assert r.status_code==200 and r.json()['phenotype']['patient_id']=='abc'

def test_static_prototype_assets():
    home=c.get('/'); assert home.status_code==200 and 'HimanshuDigitalTwin' in home.text
    assert c.get('/prototype/app.js').status_code==200
    assert c.get('/prototype/styles.css').status_code==200

def test_websocket_replay_emits_snapshot():
    with c.websocket_connect('/ws/replay/HDT-041') as ws:
        msg=ws.receive_json()
        assert msg['patient']['patient_id']=='HDT-041'
        assert msg['twin_version'] >= 1

def test_model_status_and_evidence_are_honest():
    status=c.get('/api/model/status'); assert status.status_code==200
    payload=status.json(); assert 'active_model' in payload and 'real_artifacts_active' in payload
    evidence=c.get('/api/evidence').json()
    assert 'persistence' in ' '.join(evidence['evaluation_rules']).lower()
    assert 'planned' not in str(evidence).lower()

def test_real_subject_inventory_endpoint_is_safe_when_datasets_absent():
    r=c.get('/api/real/subjects')
    assert r.status_code==200
    payload=r.json()
    assert set(payload)=={'shanghai','cgmacros'}
    assert isinstance(payload['shanghai'],list) and isinstance(payload['cgmacros'],list)


def test_model_status_uses_active_artifact_promotion_as_runtime_truth(tmp_path, monkeypatch):
    import json
    import app.main as main
    promotion={
        'status':'PASS',
        'runtime_promotion_allowed':True,
        'runtime_external_transport_allowed':False,
        'external_interval_validated':False,
    }
    import hashlib
    filenames=[f'forecast_{h}.joblib' for h in (30,60,120)]+['event_120.joblib']
    for name in filenames: (tmp_path/name).write_bytes(('test-artifact:'+name).encode())
    promotion['artifact_sha256']={name:hashlib.sha256((tmp_path/name).read_bytes()).hexdigest() for name in filenames}
    (tmp_path/'promotion.json').write_text(json.dumps(promotion))
    monkeypatch.setattr(main,'ACTIVE_MODEL_DIR',tmp_path)
    monkeypatch.setattr(main,'MODEL_LABEL','trained-test; promoted')
    payload=main.model_status()
    assert payload['runtime_promotion_allowed'] is True
    assert payload['runtime_external_transport_allowed'] is False


def test_model_status_never_inherits_approval_from_stale_packaged_report(tmp_path,monkeypatch):
    import app.main as main
    monkeypatch.setattr(main,'ACTIVE_MODEL_DIR',tmp_path)
    monkeypatch.setattr(main,'MODEL_LABEL','explicit research artifact (unpromoted)')
    # No promotion file exists at this candidate path; do not imply approval
    # from a report for a different model in a different directory.
    j=main.model_status()
    assert j['runtime_promotion_allowed'] is False
    assert j['runtime_personalization_allowed'] is False
    assert j['runtime_external_transport_allowed'] is False
