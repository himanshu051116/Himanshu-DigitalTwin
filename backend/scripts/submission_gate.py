"""Evidence-based promotion gate for HimanshuDigitalTwin.

The runtime must not silently promote trained artifacts merely because files exist.
This module checks whether the primary real-cohort evidence beats simple baselines and
whether the adverse-event model has non-trivial discrimination before writing a
promotion.json marker consumed by the API/runtime.

External Shanghai validation is reported but does not block primary promotion because
Shanghai lacks several CGMacros modalities by design.
"""
from __future__ import annotations
import argparse, json, hashlib
from pathlib import Path

HORIZONS=(30,60,120)


def _pct(a,b):
    return 100.0*(b-a)/max(1e-9,b)


def evaluate_evidence(evidence: dict) -> dict:
    primary=evidence.get('primary') or {}
    forecast=primary.get('forecast') or {}
    event=(primary.get('event') or {}).get('holdout') or {}
    checks=[]
    primary_preflight=((evidence.get('data_preflight') or {}).get('cgmacros') or {})

    def add(name, passed, detail, level='required'):
        checks.append({'name':name,'passed':bool(passed),'level':level,'detail':detail})

    add('complete_real_primary_cohort',
        primary_preflight.get('ready_for_final_primary_training') is True
        and not evidence.get('development_smoke_override_used',False),
        f"45-subject complete cohort preflight={primary_preflight.get('ready_for_final_primary_training')}; "
        f"smoke_override={evidence.get('development_smoke_override_used',False)}")

    # Forecast gates: short horizons must beat persistence. The 120-minute model may be
    # slightly worse (<=5%) without invalidating the whole twin, but that weakness is surfaced.
    for h in HORIZONS:
        r=forecast.get(str(h)) or {}
        mm=(r.get('model') or {}).get('mae')
        pm=(r.get('persistence_baseline') or {}).get('mae')
        macro=r.get('mae_macro_subject')
        pmacro=r.get('persistence_mae_macro_subject')
        t2d=(r.get('t2d_holdout') or {}).get('n',0)
        unc=r.get('uncertainty') or {}
        if mm is None or pm is None:
            add(f'forecast_{h}_available',False,'missing model/persistence MAE')
            continue
        trend=((r.get('linear_trend_baseline') or {}).get('mae'))
        best_baseline=min([v for v in (pm,trend) if v is not None])
        improvement=100*(best_baseline-mm)/max(1e-9,best_baseline)
        minimum=0.0 if h in (30,60) else -5.0
        add(f'forecast_{h}_vs_best_simple_baseline',improvement>=minimum,
            f'improvement={improvement:.2f}% vs best MAE={best_baseline:.3f} (required >= {minimum:.1f}%)')
        if h in (30,60):
            add(f'forecast_{h}_macro_subject',
                macro is not None and pmacro is not None and macro<=pmacro,
                f'macro_model={macro}, macro_persistence={pmacro}')
        personalization=r.get('personalization') or {}
        p_imp=personalization.get('improvement_pct_pooled')
        p_frac=personalization.get('subjects_improved_fraction')
        level='quality'  # adaptation is a separate optional runtime capability
        add(f'personalization_{h}',p_imp is not None and p_imp>0 and p_frac is not None and p_frac>=0.50,
            f'pooled_improvement={p_imp}, subjects_improved_fraction={p_frac}',level=level)
        add(f'forecast_{h}_t2d_holdout',t2d>0,f'T2D holdout rows={t2d}')
        cov=unc.get('empirical_test_coverage')
        add(f'forecast_{h}_independent_interval_check',
            cov is not None and 0.75 <= cov <= 0.95
            and unc.get('macro_subject_coverage') is not None
            and 0.75 <= unc['macro_subject_coverage'] <= 0.95,
            f'row_coverage={cov}, patient_macro_coverage={unc.get("macro_subject_coverage")}; each required in [0.75,0.95]', level='quality')

    prevalence=event.get('event_prevalence')
    auroc=event.get('auroc'); auprc=event.get('auprc'); brier=event.get('brier')
    add('event_model_available', bool(event), f'n={event.get("n")}')
    add('event_auroc',auroc is not None and auroc>=0.60,f'AUROC={auroc} (required >=0.60)')
    current_auc=event.get('current_glucose_auroc_baseline')
    add('event_auroc_vs_current_glucose',
        auroc is not None and current_auc is not None and auroc>=current_auc,
        f'model_AUROC={auroc}, current_glucose_AUROC={current_auc}')
    add('event_auprc_vs_prevalence',
        auprc is not None and prevalence is not None and auprc>prevalence,
        f'AUPRC={auprc}, prevalence={prevalence}')
    # Constant-prevalence Brier is p(1-p); require the model to beat it.
    brier_ref=(prevalence*(1-prevalence)) if prevalence is not None else None
    add('event_brier_vs_constant',
        brier is not None and brier_ref is not None and brier<brier_ref,
        f'Brier={brier}, constant-prevalence baseline={brier_ref}')

    claims=(evidence.get('claims_policy') or {})
    add('no_clinical_validation_claim', claims.get('clinical_validation') is False,
        f'clinical_validation={claims.get("clinical_validation")}')
    add('no_indian_validation_claim', claims.get('indian_population_validation') is False,
        f'indian_population_validation={claims.get("indian_population_validation")}')

    required=[c for c in checks if c['level']=='required']
    passed=all(c['passed'] for c in required)
    check_map={c['name']:c['passed'] for c in checks}
    # Population forecasting, residual adaptation, and reported uncertainty are
    # independent claims. Never promote adaptive corrections or interval labels
    # merely because the population model passed its baselines.
    # Live adapter corrects all three horizons: approval at 60 min alone
    # cannot authorize unvalidated 30/120-min adaptations.
    adaptation_ok=passed and all(check_map.get(f'personalization_{h}',False) for h in HORIZONS)
    uncertainty_ok=passed and all(check_map.get(f'forecast_{h}_independent_interval_check',False) for h in HORIZONS)
    external=evidence.get('external')
    ext_summary=None
    ext_checks=[]
    external_allowed=False
    external_interval_validated=False
    if external:
        def eadd(name,passed,detail,level='required'):
            ext_checks.append({'name':name,'passed':bool(passed),'level':level,'detail':detail})
        for h in (30,60):
            r=(external.get('forecast',{}).get(str(h),{}) or {})
            imp=r.get('improvement_vs_persistence_pct'); macro=r.get('mae_macro_subject'); pmacro=r.get('persistence_mae_macro_subject')
            eadd(f'external_forecast_{h}_beats_persistence',imp is not None and imp>=0,f'improvement={imp}%')
            eadd(f'external_forecast_{h}_macro_subject',macro is not None and pmacro is not None and macro<=pmacro,f'macro_model={macro}, macro_persistence={pmacro}')
        covs=[]
        for h in HORIZONS:
            cov=(((external.get('forecast',{}).get(str(h),{}) or {}).get('prediction_interval_80') or {}).get('external_empirical_coverage'))
            if cov is not None: covs.append(cov)
            eadd(f'external_interval_{h}_coverage',cov is not None and 0.60<=cov<=0.95,f'coverage={cov}',level='quality')
        er=external.get('event_120') or {}; eau=er.get('auroc'); ebase=er.get('current_glucose_auroc_baseline'); eprev=er.get('event_rate'); ebrier=er.get('brier')
        eadd('external_event_discrimination',eau is not None and eau>=0.60,f'AUROC={eau}',level='quality')
        eadd('external_event_vs_current_glucose',eau is not None and ebase is not None and eau>=ebase,f'model_AUROC={eau}, current_glucose_AUROC={ebase}',level='quality')
        eadd('external_event_brier',ebrier is not None and eprev is not None and ebrier<eprev*(1-eprev),f'Brier={ebrier}, constant={eprev*(1-eprev) if eprev is not None else None}',level='quality')
        ext_preflight=((evidence.get('data_preflight') or {}).get('shanghai') or {})
        eadd('complete_real_external_cohort',
             ext_preflight.get('ready_for_external_validation') is True
             and primary_preflight.get('ready_for_final_primary_training') is True
             and not evidence.get('development_smoke_override_used',False),
             f"Shanghai complete={ext_preflight.get('ready_for_external_validation')}; "
             f"CGMacros complete={primary_preflight.get('ready_for_final_primary_training')}; "
             f"smoke_override={evidence.get('development_smoke_override_used',False)}")
        external_allowed=all(c['passed'] for c in ext_checks if c['level']=='required')
        external_interval_validated=(external_allowed and len(covs)==len(HORIZONS)
                                     and all(0.75<=c<=0.95 for c in covs))
        ext_summary={
            'status':'PASS' if external_allowed else 'FAIL',
            'runtime_external_transport_allowed':external_allowed,
            'external_interval_validated':external_interval_validated,
            'subjects':external.get('subjects'),
            'checks':ext_checks,
            'forecast_improvement_vs_persistence_pct':{h:(external.get('forecast',{}).get(str(h),{}) or {}).get('improvement_vs_persistence_pct') for h in HORIZONS},
            'event_auroc':er.get('auroc'),
            'note':'External transport has a separate gate and never controls primary CGMacros promotion.'
        }
    return {
        'status':'PASS' if passed else 'FAIL',
        'runtime_promotion_allowed':passed,
        'runtime_personalization_allowed':adaptation_ok,
        'runtime_interval_allowed':uncertainty_ok,
        'runtime_external_transport_allowed':external_allowed,
        'external_interval_validated':external_interval_validated,
        'checks':checks,
        'external_summary':ext_summary,
        'policy':'Population forecasting, personalization, intervals and Shanghai transport have independent evidence gates; incomplete smoke cohorts never promote.',
    }


def stamp_artifact_hashes(gate: dict, model_dir: str | Path) -> dict:
    """Bind a PASS decision to the exact fitted model files it evaluated.

    A gate copied to another directory or left behind after a partial retrain
    must never authorize a different set of research artifacts.
    """
    model_dir=Path(model_dir)
    if not gate.get('runtime_promotion_allowed') and not gate.get('runtime_external_transport_allowed'):
        gate['artifact_sha256']={}
        return gate
    paths=([f'forecast_{h}.joblib' for h in HORIZONS]+['event_120.joblib']) if gate.get('runtime_promotion_allowed') else []
    if gate.get('runtime_external_transport_allowed'):
        paths += [f'transport_forecast_{h}.joblib' for h in HORIZONS]+['transport_event_120.joblib']
    fingerprints={}
    for name in paths:
        p=model_dir/name
        if not p.is_file():
            raise FileNotFoundError(f'Missing promoted model artifact: {p}')
        fingerprints[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    gate['artifact_sha256']=fingerprints
    gate['integrity_policy']='SHA-256 digest verification required before model promotion; trusted local artifacts only'
    return gate


def write_gate(evidence_path: str|Path, model_dir: str|Path, out_path: str|Path):
    evidence=json.loads(Path(evidence_path).read_text())
    gate=stamp_artifact_hashes(evaluate_evidence(evidence),model_dir)
    out=Path(out_path); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(gate,indent=2,allow_nan=False))
    model_dir=Path(model_dir); model_dir.mkdir(parents=True,exist_ok=True)
    (model_dir/'promotion.json').write_text(json.dumps(gate,indent=2,allow_nan=False))
    return gate


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--evidence',default='reports/evidence_manifest.json')
    ap.add_argument('--model-dir',default='models/submission')
    ap.add_argument('--out',default='reports/submission_gate.json')
    args=ap.parse_args()
    gate=write_gate(args.evidence,args.model_dir,args.out)
    print(json.dumps(gate,indent=2))
    raise SystemExit(0 if gate['runtime_promotion_allowed'] else 2)

if __name__=='__main__': main()
