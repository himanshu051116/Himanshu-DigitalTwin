"""Canonical evidence pipeline for the HimanshuDigitalTwin submission.

1. Train/evaluate the primary multimodal model on CGMacros with an untouched subject holdout.
2. Optionally evaluate the frozen CGMacros artifacts on independent ShanghaiT2DM subjects.
3. Write one evidence_manifest.json consumed by reviewers and CI.

Do not use the legacy training scripts for final submission metrics.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.train_clinical import train
from scripts.validate_external import evaluate
from scripts.submission_gate import evaluate_evidence, stamp_artifact_hashes
from scripts.preflight_data import audit_cgmacros, audit_shanghai


def run(cgmacros_dir, out_dir, report_path, shanghai_dir=None, metadata=None, allow_incomplete_primary=False, allow_incomplete_external=False):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    rp=Path(report_path)
    rp.parent.mkdir(parents=True,exist_ok=True)
    # Never let an interrupted or rejected retrain leave behind the previous
    # run's evidence JSON and PASS report. These are data products, not caches.
    rp.unlink(missing_ok=True)
    (rp.parent/'submission_gate.json').unlink(missing_ok=True)
    # Fail closed *before* preflight: even a missing/incomplete cohort must
    # invalidate an older approval before any potentially failing I/O occurs.
    (out/'promotion.json').write_text(json.dumps({
        'status':'TRAINING', 'runtime_promotion_allowed':False,
        'runtime_personalization_allowed':False,
        'runtime_interval_allowed':False,
        'runtime_external_transport_allowed':False,
        'external_interval_validated':False,
        'note':'Attempted retraining/preflight: all earlier promotions invalid until a fresh gate passes.'
    },indent=2))
    data_audit={'cgmacros':audit_cgmacros(cgmacros_dir)}
    if not data_audit['cgmacros']['ready_for_final_primary_training'] and not allow_incomplete_primary:
        raise ValueError('CGMacros preflight failed: final evidence requires the complete official 45-subject multimodal cohort. Use --allow-incomplete-primary only for development smoke tests.')
    if shanghai_dir:
        if not metadata: raise ValueError('--metadata is required with --shanghai-dir')
        data_audit['shanghai']=audit_shanghai(shanghai_dir,metadata)
        if not data_audit['shanghai']['ready_for_external_validation'] and not allow_incomplete_external:
            raise ValueError('Shanghai preflight failed: final external validation requires all 100 public subjects. Use --allow-incomplete-external only for development smoke tests.')
    primary=train(cgmacros_dir,out)
    evidence={
        'project':'HimanshuDigitalTwin',
        'pipeline':'canonical-submission-v1',
        'primary':primary,
        'external':None,
        'data_preflight':data_audit,
        'development_smoke_override_used':bool(allow_incomplete_primary or allow_incomplete_external),
        'claims_policy':{
            'primary':'same-subject multimodal CGMacros research validation',
            'external':'ShanghaiT2DM transportability via separate CGM/phenotype-only model; no missing meal/activity fabricated',
            'clinical_validation':False,
            'indian_population_validation':False,
        },
    }
    if shanghai_dir:
        evidence['external']=evaluate(out,shanghai_dir,metadata)
    rp=Path(report_path); rp.parent.mkdir(parents=True,exist_ok=True); rp.write_text(json.dumps(evidence,indent=2,allow_nan=False))
    gate=stamp_artifact_hashes(evaluate_evidence(evidence),out)
    gate_path=rp.parent/'submission_gate.json'
    gate_path.write_text(json.dumps(gate,indent=2,allow_nan=False))
    (out/'promotion.json').write_text(json.dumps(gate,indent=2,allow_nan=False))
    evidence['promotion_gate']=gate
    return evidence


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cgmacros-dir',required=True)
    ap.add_argument('--out',default='models/submission')
    ap.add_argument('--report',default='reports/evidence_manifest.json')
    ap.add_argument('--shanghai-dir')
    ap.add_argument('--metadata')
    ap.add_argument('--allow-incomplete-primary',action='store_true',help='Development smoke tests only; final evidence requires all 45 CGMacros subjects.')
    ap.add_argument('--allow-incomplete-external',action='store_true',help='Development smoke tests only; final external validation requires all 100 Shanghai subjects.')
    args=ap.parse_args()
    evidence=run(args.cgmacros_dir,args.out,args.report,args.shanghai_dir,args.metadata,args.allow_incomplete_primary,args.allow_incomplete_external)
    summary={'primary_cohort':evidence['primary']['design']['primary_cohort'],'external_complete':evidence['external'] is not None,'artifact_dir':args.out,'report':args.report,'promotion_status':evidence.get('promotion_gate',{}).get('status')}
    print(json.dumps(summary,indent=2))
    if evidence.get('promotion_gate',{}).get('status') != 'PASS':
        raise SystemExit(2)

if __name__=='__main__': main()
