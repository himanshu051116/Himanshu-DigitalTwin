"""Critical public claim disclosures must remain visible next to the metric."""
from pathlib import Path

STATIC=Path(__file__).parents[1]/"static"

def test_uncalibrated_risk_label_is_in_same_card_as_probability():
    page=(STATIC/"index.html").read_text()
    risk_card=page.split('id="riskModelFlag"')[0][-120:]
    assert 'SIMULATED · UNCALIBRATED RISK' in page
    assert '2-hour excursion risk' in risk_card
    assert 'id="confidence"' in page

def test_risk_mode_label_is_updated_from_model_provenance():
    js=(STATIC/"app.js").read_text()
    assert "isResearchModel=Boolean(snap.model_info?.trained)" in js
    assert "$('#riskModelFlag').textContent" in js
    assert 'RESEARCH MODEL · NOT FOR CLINICAL USE' in js
    assert 'Sensor/data confidence:' in js

def test_demo_trace_remains_explicitly_simulated():
    import json
    path=Path(__file__).parents[2]/"submission/judge_verified_demo_trace.json"
    data=json.loads(path.read_text())
    assert 'Synthetic' in data['provenance']
    chapters={e['chapter']:e for e in data['chapters']}
    assert chapters['sensor_gap']['forecast_status']=='ABSTAINED'
    assert chapters['sensor_gap']['risk'] is None
    assert chapters['recovery']['forecast_status']=='AVAILABLE'
