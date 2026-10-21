"""Keep the submission's public reproduction check useful and fail-closed."""
from scripts.verify_judge_submission import verify

def test_judge_trace_matches_live_synthetic_api():
    result = verify()
    assert result['verdict'] == 'PASS', [x for x in result['checks'] if not x['passed']]
    assert result['passed'] == result['total']
    assert 'clinical efficacy' in result['not_verified']
