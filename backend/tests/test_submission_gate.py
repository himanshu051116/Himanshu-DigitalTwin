from scripts.submission_gate import evaluate_evidence


def _evidence(improvement=10.0, event_good=True):
    forecast={}
    for h in (30,60,120):
        persistence=20.0
        model=persistence*(1-improvement/100)
        forecast[str(h)]={
            'model':{'mae':model},
            'persistence_baseline':{'mae':persistence},
            'linear_trend_baseline':{'mae':persistence*1.05},
            'mae_macro_subject':model,
            'persistence_mae_macro_subject':persistence,
            't2d_holdout':{'n':100},
            'uncertainty':{'empirical_test_coverage':0.79,'macro_subject_coverage':0.79},
            'personalization':{'improvement_pct_pooled':5.0,'subjects_improved_fraction':0.7},
        }
    event={'holdout':{
        'n':1000,'auroc':0.78 if event_good else 0.52,
        'auprc':0.55 if event_good else 0.15,
        'event_prevalence':0.25,'brier':0.14 if event_good else 0.24,
        'current_glucose_auroc_baseline':0.70,
    }}
    return {'primary':{'forecast':forecast,'event':event},'external':None,
            'data_preflight':{'cgmacros':{'ready_for_final_primary_training':True}},
            'claims_policy':{'clinical_validation':False,'indian_population_validation':False}}


def test_submission_gate_passes_nontrivial_evidence():
    gate=evaluate_evidence(_evidence())
    assert gate['status']=='PASS'
    assert gate['runtime_promotion_allowed'] is True


def test_submission_gate_blocks_weak_event_model():
    gate=evaluate_evidence(_evidence(event_good=False))
    assert gate['status']=='FAIL'
    assert gate['runtime_promotion_allowed'] is False


def test_submission_gate_blocks_short_horizon_worse_than_persistence():
    ev=_evidence()
    ev['primary']['forecast']['30']['model']['mae']=22
    gate=evaluate_evidence(ev)
    assert gate['status']=='FAIL'


def test_incomplete_smoke_run_never_promotes():
    ev=_evidence()
    ev['development_smoke_override_used']=True
    gate=evaluate_evidence(ev)
    assert gate['runtime_promotion_allowed'] is False
    assert gate['status']=='FAIL'


def test_population_pass_does_not_enable_unproven_personalization_or_intervals():
    ev=_evidence()
    ev['primary']['forecast']['60']['personalization']={'improvement_pct_pooled':-1.,'subjects_improved_fraction':.30}
    ev['primary']['forecast']['120']['uncertainty']['empirical_test_coverage']=.71
    gate=evaluate_evidence(ev)
    assert gate['runtime_promotion_allowed'] is True
    assert gate['runtime_personalization_allowed'] is False
    assert gate['runtime_interval_allowed'] is False


def test_missing_preflight_cannot_promote():
    ev=_evidence(); del ev['data_preflight']
    assert evaluate_evidence(ev)['status']=='FAIL'


def test_uncertainty_cannot_pass_if_patient_macro_coverage_fails():
    ev=_evidence()
    ev['primary']['forecast']['60']['uncertainty']['macro_subject_coverage']=0.61
    gate=evaluate_evidence(ev)
    assert gate['runtime_promotion_allowed'] is True
    assert gate['runtime_interval_allowed'] is False
