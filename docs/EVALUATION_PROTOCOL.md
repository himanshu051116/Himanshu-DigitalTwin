# HimanshuDigitalTwin — Evaluation Protocol v0.16

## 1. Primary cohort
Use **CGMacros** because phenotype, CGM, food/macronutrients and activity belong to the same research participant. Published cohort labels are used: No diabetes / Prediabetes / T2D. HbA1c thresholding is fallback only.

## 2. Split policy
Use one deterministic locked subject-level holdout (~20%), stratified independently within the published glycemic groups. Adjacent CGM rows are never randomly split across train/test. All data for one person stays in one split.

Model/hyperparameter selection happens only on training subjects via GroupKFold. Test subjects remain untouched until the final evaluation. The fitted model evaluated on the holdout **must be the model saved as the deployment candidate**. Do not silently refit on the locked holdout afterward; such a refit requires a separate independent evaluation.

## 3. Forecast targets
Predict glucose at +30, +60 and +120 minutes. Evaluation rows require a valid current glucose and sufficient recent glucose history.

Report per horizon:
- MAE / RMSE;
- macro-subject MAE;
- persistence baseline;
- linear-trend baseline;
- gain versus the best simple baseline;
- T2D-only holdout metrics;
- subject-bootstrap confidence interval for macro MAE gain.

## 4. Personalization
Population predictions must already be out-of-fold by subject. Personalization then simulates the deployed context-aware online residual adapter (`baseline`, `postmeal`, `active`) causally: prediction first, observation second, update third.

The first 30% of each unseen subject establishes adaptation; later predictions are evaluated while updates continue using only prior observations. Only genuine `VALID` sensor observations may update the runtime adapter.

## 5. Adverse event
Event definition:

`current glucose <=180 mg/dL AND glucose crosses >180 mg/dL within the next 120 minutes`

Rows already above 180 are excluded from future-event training. The probability operating threshold is selected from subject-grouped OOF predictions on training subjects only and locked before test evaluation.

Report:
- AUROC / AUPRC / Brier score;
- current-glucose AUROC baseline;
- constant-prevalence Brier baseline;
- locked-threshold precision / recall / F1;
- event prevalence;
- onset-episode detection rate;
- median warning lead time;
- false-alert fraction on negative windows.

## 6. Uncertainty
Primary forecast interval calibration is patient balanced: obtain subject-grouped OOF residuals on training subjects, take an 80th-percentile absolute-error width **per training patient**, and choose the 80th-percentile patient width. Never use the locked holdout to set these widths. Report row-weighted and **macro-subject** coverage, plus the fraction of subjects with undercoverage on the untouched test.

This nested empirical quantile is not a mathematical conformal prediction guarantee. It can still under- or over-cover under cohort shift. Automatic interval use requires both row-level and macro-subject empirical coverage to fall within the preregistered evaluation band; failing intervals are hidden from the trained-model runtime.

## 7. External transportability
ShanghaiT2DM is never merged with CGMacros. A separate **transport artifact** is trained on CGMacros using only modalities available in Shanghai: CGM dynamics, circadian variables, age and HbA1c.

Shanghai reports:
- forecast MAE/RMSE vs persistence;
- macro-subject MAE;
- external coverage of the CGMacros-calibrated transport interval;
- event AUROC/AUPRC/Brier and current-glucose baseline.

External transport has a separate promotion gate. A primary CGMacros PASS does not imply Shanghai transport success.

## 8. Promotion gates
Primary runtime promotion requires non-trivial locked-holdout performance, T2D holdout representation and event discrimination/calibration. Population promotion does NOT require personalization or interval evidence to pass: those capabilities have independent optional gates. A runtime PASS is bound to exact model files by SHA-256 fingerprints; any mismatch or legacy unhashed PASS prevents automatic promotion.

Shanghai transport promotion separately requires 30/60-minute forecast improvement over persistence at pooled and macro-subject levels. Interval/event transport checks are reported independently.

## 9. Canonical runner

```bash
python scripts/train_submission.py \
  --cgmacros-dir <CGMacros folder> \
  --shanghai-dir <Shanghai glucose folder> \
  --metadata data/reference/shanghai_t2dm_metadata.csv \
  --out models/submission \
  --report reports/evidence_manifest.json
```

On Windows use `run_final_evidence.ps1`, which performs acquisition, checksum verification, fail-closed preflight, training, external validation, gating and Markdown evidence rendering.

Only real-cohort metrics from `reports/evidence_manifest.json` / `reports/EVIDENCE_REPORT.md` may be copied into the final judging deck.

## Added in v0.16: operational and external-transport fail-closed rules

1. Invalidate the old promotion marker **before** cohort preflight, since a missing dataset is a failed retraining attempt.
2. Accept only measured (`VALID`) 15-minute Shanghai glucose as truth; require consecutive timestamps across every labelled future horizon. Imputation never creates an evaluation outcome.
3. Shanghai transport validation must find dedicated CGM/phenotype-only artifacts. No fallback to the multimodal CGMacros model is permitted; externally unavailable modalities may not appear in the artifact's feature list.
4. Training and runtime demand all three horizon-level adaptation checks, not 60 minutes alone, before global online personalization can activate.
5. Runtime abstains if glucose is missing/no genuine reading within 15 minutes or, for trained models, until a full 60 minutes of uninterrupted valid five-minute CGM observations are present (13 samples including the current observation).
6. Active glucose above 180 mg/dL is a *current* excursion, not a computed 100% probability of a *new future* excursion.
7. Real-data re-execution and true external transport metrics are still required: software tests and synthetic smoke studies do not constitute prospective or clinical validation.
