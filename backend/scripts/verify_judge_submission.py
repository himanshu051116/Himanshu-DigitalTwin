"""Recheck the bundled synthetic judge replay and research-provenance guardrails.

Offline only; this does not validate any clinical model, external GitHub link,
competition registration or research benchmark reproducibility.
"""
from __future__ import annotations
import argparse
import json
import math
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'backend'))
from fastapi.testclient import TestClient
from app.main import app


def verify(expected_file: Path | None = None) -> dict:
    path = expected_file or BASE/'submission'/'judge_verified_demo_trace.json'
    expected = json.loads(path.read_text(encoding='utf-8'))
    client = TestClient(app)
    checks = []
    def check(label, result):
        checks.append({'check': label, 'passed': bool(result)})
    check('trace_is_explicitly_synthetic', 'Synthetic' in expected.get('provenance', ''))
    chapters_resp = client.get('/api/demo/chapters')
    check('six_simulated_chapters_declared', chapters_resp.status_code == 200 and
          chapters_resp.json().get('simulation_only') is True and
          len(chapters_resp.json().get('chapters', [])) == 6)
    records = {}
    for row in expected['chapters']:
        name = row['chapter']
        resp = client.post('/api/demo/chapter/' + name)
        check(name+'_responds', resp.status_code == 200 and resp.json().get('simulation_only') is True)
        if resp.status_code != 200:
            continue
        snap = resp.json()['snapshot']
        records[name] = snap
        reading = snap['reading']
        expected_forecasts = {int(x['horizon']): float(x['value']) for x in row['forecasts']}
        observed_forecasts = {int(x['horizon_min']): float(x['personalized']) for x in snap['forecasts']}
        check(name+'_trace_matches', all([
            row['timestamp'] == snap['timestamp'],
            row['twin_version'] == snap['twin_version'],
            row['quality'] == reading['quality'],
            row['forecast_status'] == snap['forecast_status'],
            row['resolved_forecasts'] == snap['model_metrics']['resolved_forecasts'],
            reading['glucose'] == row['glucose'],
            snap['excursion_risk'] == row['risk'],
            expected_forecasts == observed_forecasts,
        ]))
    gap = records.get('sensor_gap', {})
    check('gap_abstains_without_glucose_or_risk', bool(gap) and
          gap['reading']['glucose'] is None and
          gap['reading']['quality'] == 'IMPUTED' and
          gap['forecast_status'] == 'ABSTAINED' and
          gap['excursion_risk'] is None and gap['forecasts'] == [])
    recovery = records.get('recovery', {})
    check('recovery_restores_synthetic_forecasts', bool(recovery) and
          recovery['forecast_status'] == 'AVAILABLE' and bool(recovery['forecasts']))
    st = client.get('/api/model/status')
    check('trained_runtime_not_promoted', st.status_code == 200 and
          st.json().get('runtime_promotion_allowed') is False)
    evidence = client.get('/api/research/evidence')
    check('independent_evidence_is_informational_only', evidence.status_code == 200 and
          'cgmacros' in evidence.text.lower())
    count = sum(a['passed'] for a in checks)
    return {'kind': 'synthetic_demo_consistency_check', 'passed': count,
            'total': len(checks), 'verdict': 'PASS' if count == len(checks) else 'FAIL',
            'checks': checks,
            'not_verified': ['clinical efficacy', 'original independent training-script reproduction',
                             'registration', 'public GitHub visibility', 'external video accessibility']}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path)
    args = ap.parse_args()
    result = verify()
    print(json.dumps(result, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
