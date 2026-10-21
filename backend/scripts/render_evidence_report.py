"""Render canonical HimanshuDigitalTwin evidence JSON into a reviewer-readable Markdown report."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def fnum(v,d=2):
    if v is None: return '—'
    try: return f'{float(v):.{d}f}'
    except (TypeError,ValueError): return str(v)


def render(evidence: dict, gate: dict) -> str:
    primary=evidence.get('primary') or {}; forecast=primary.get('forecast') or {}; event=primary.get('event') or {}
    audit=evidence.get('data_preflight') or {}; cg=audit.get('cgmacros') or {}; sh=audit.get('shanghai') or {}
    lines=[
        '# HimanshuDigitalTwin — Evidence Report','',
        '> Research prototype evidence only. This report is not clinical validation and does not justify diagnosis, dosing, or treatment recommendations.','',
        '## Evidence status','',
        f"- Primary CGMacros promotion gate: **{gate.get('status','NOT RUN')}**",
        f"- Primary runtime promotion allowed: **{gate.get('runtime_promotion_allowed',False)}**",
        f"- Shanghai transport gate: **{(gate.get('external_summary') or {}).get('status','NOT RUN')}**",
        f"- Shanghai runtime transport allowed: **{gate.get('runtime_external_transport_allowed',False)}**",
        f"- External interval validation: **{gate.get('external_interval_validated',False)}**",'',
        '## Cohort integrity','',
        f"- CGMacros subjects: **{cg.get('subject_files','—')} / {cg.get('expected_subjects','—')}**",
        f"- Published CGMacros diabetes labels available: **{cg.get('published_label_subjects','—')}**",
        f"- CGMacros final-primary preflight: **{cg.get('ready_for_final_primary_training','—')}**",
        f"- Shanghai subjects: **{sh.get('subject_files','—')} / {sh.get('expected_subjects','—')}**",
        f"- Shanghai external-validation preflight: **{sh.get('ready_for_external_validation','—')}**",'',
        '## Locked primary forecast evaluation','',
        '| Horizon | Model MAE | Persistence MAE | Trend MAE | Best-baseline gain | Macro-subject MAE | T2D holdout rows | 80% interval coverage | Personalization gain |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|---:|'
    ]
    for h in ('30','60','120'):
        r=forecast.get(h) or {}; model=r.get('model') or {}; p=r.get('persistence_baseline') or {}; t=r.get('linear_trend_baseline') or {}; unc=r.get('uncertainty') or {}; pers=r.get('personalization') or {}; t2d=r.get('t2d_holdout') or {}
        vals=[x for x in [p.get('mae'),t.get('mae')] if x is not None]; best=min(vals) if vals else None
        gain=(100*(best-model.get('mae'))/best) if best and model.get('mae') is not None else None
        lines.append(f"| {h} min | {fnum(model.get('mae'))} | {fnum(p.get('mae'))} | {fnum(t.get('mae'))} | {fnum(gain)}% | {fnum(r.get('mae_macro_subject'))} | {t2d.get('n','—')} | {fnum((unc.get('empirical_test_coverage') or 0)*100)}% | {fnum(pers.get('improvement_pct_pooled'))}% |")
    eh=event.get('holdout') or {}; ep=event.get('episode_warning') or {}; th=event.get('alert_threshold_selection') or {}
    lines += ['', '## 120-minute new-excursion onset model','',
        f"- Event definition: **{(primary.get('design') or {}).get('event_definition','—')}**",
        f"- AUROC: **{fnum(eh.get('auroc'),3)}**",
        f"- AUPRC: **{fnum(eh.get('auprc'),3)}** (event prevalence {fnum((eh.get('event_prevalence') or 0)*100)}%)",
        f"- Brier score: **{fnum(eh.get('brier'),4)}**",
        f"- Alert probability threshold: **{fnum((eh.get('alert_probability_threshold') or 0)*100,1)}%**; selected only from training-subject OOF predictions",
        f"- Recall at locked threshold: **{fnum((eh.get('recall_at_threshold') or 0)*100,1)}%**",
        f"- Precision at locked threshold: **{fnum((eh.get('precision_at_threshold') or 0)*100,1)}%**",
        f"- Onset episodes detected: **{ep.get('detected_onsets','—')} / {ep.get('onset_episodes','—')}**",
        f"- Median warning lead time: **{fnum(ep.get('median_warning_lead_min'),1)} min**",
        f"- False-alert row fraction on negative windows: **{fnum((ep.get('false_alert_row_fraction_on_negative_windows') or 0)*100,1)}%**",'',
        '## External ShanghaiT2DM transportability','',
        '| Horizon | Transport MAE | Persistence MAE | Improvement | External 80% interval coverage |',
        '|---:|---:|---:|---:|---:|']
    ext=evidence.get('external') or {}
    for h in ('30','60','120'):
        r=(ext.get('forecast') or {}).get(h) or {}; pi=r.get('prediction_interval_80') or {}
        lines.append(f"| {h} min | {fnum((r.get('model') or {}).get('mae'))} | {fnum((r.get('persistence') or {}).get('mae'))} | {fnum(r.get('improvement_vs_persistence_pct'))}% | {fnum((pi.get('external_empirical_coverage') or 0)*100)}% |")
    er=ext.get('event_120') or {}
    lines += ['',
        f"- External event AUROC: **{fnum(er.get('auroc'),3)}**",
        f"- Current-glucose AUROC baseline: **{fnum(er.get('current_glucose_auroc_baseline'),3)}**",
        f"- External event Brier: **{fnum(er.get('brier'),4)}**",'',
        '## Claims policy','',
        '- Patient-level train/test leakage is prohibited; all recording periods stay with the same subject.',
        '- Hyperparameter selection uses training subjects only; the locked test subjects are untouched until final evaluation.',
        '- Personalization is evaluated causally on unseen subjects using only prior observations.',
        '- Shanghai is never merged with CGMacros subjects and has a separate runtime gate.',
        '- India epidemiology establishes relevance only; it is not presented as Indian patient-level model validation.',
        '- Clinical validation: **NO**. Indian population validation: **NO**.',''
    ]
    return '\n'.join(lines)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--evidence',default='reports/evidence_manifest.json'); ap.add_argument('--gate',default='reports/submission_gate.json'); ap.add_argument('--out',default='reports/EVIDENCE_REPORT.md'); a=ap.parse_args()
    evidence=json.loads(Path(a.evidence).read_text()); gate=json.loads(Path(a.gate).read_text()); text=render(evidence,gate); out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(text,encoding='utf-8'); print(out)
if __name__=='__main__': main()
