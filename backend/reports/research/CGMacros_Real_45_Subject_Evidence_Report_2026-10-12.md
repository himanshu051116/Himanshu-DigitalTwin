# HimanshuDigitalTwin — real CGMacros evidence report

**Run date:** 12 October 2026  
**Evidence status:** REAL, participant-held-out research evaluation; **not clinical validation, not production promotion**.  
**Scope:** An independent reproducible benchmark executed in an isolated Vercel cloud sandbox. The original application's canonical `train_submission.py` and Shanghai external validation were **not** run in this execution. Synthetic data were **not** used to generate the metrics below.

## 1. Data acquisition and integrity

- Source: [CGMacros PhysioNet v1.0.0](https://physionet.org/content/cgmacros/1.0.0/) (DOI 10.13026/3z8q-x658).
- Access: PhysioNet's public S3 mirror, using HTTP `206 Partial Content` byte ranges. Extracted actual compressed ZIP members with Python `zipfile`; each member read to EOF with its ZIP CRC checked.
- Retrieved: **45 participant CSVs + 1 `bio.csv`**, approximately **46,741,716 bytes** of extracted CSV measurements. The full 657,187,340-byte ZIP was not transferred; accordingly, its **whole-archive SHA-256 was not verified**.
- Cohort: 15 no diabetes, 16 prediabetes, 14 type-2 diabetes. Groups follow the published participant labels rather than inferring diagnosis from HbA1c alone.
- Dexcom CGM was the evaluation target. Meal records, carbs, protein, fat, HR, activity and clinical phenotypes were considered as model features when present. Not all patient CSVs expose identical activity schemas: missing METs were retained as missing, not interpreted as zero activity.
- Glucose/meal/sensor 5-minute bins were **right-labelled and right-closed** so each origin-time feature was available by that timestamp. Records required a contiguous prior 60-minute CGM window and a contiguous observed future horizon. The research source's one-minute harmonization is a limitation that warrants native 5-minute Dexcom cross-checking.

## 2. Method and leakage safeguards

- Primary patient-grouped split: **35 people for training, 10 entirely unseen people for testing** (3 no diabetes / 4 prediabetes / 3 T2D). Test subject numbers were `003, 018, 021, 023, 029, 030, 033, 038, 041, 045`.
- Horizons: 30 / 60 / 120 minutes; no random CGM row split. Forecast model: HistGradientBoostingRegressor with a median imputer fitted on training subjects only, plus the same dynamic/static feature schema at holdout prediction.
- Baselines: glucose persistence and 15-minute-slope linear extrapolation. Improvement is versus the **better** simple baseline, not a weak strawman.
- Robustness: **five deterministic patient-stratified holdout seeds**; tests across seeds overlap and are **not** five independent trials. No test-subject hyperparameter tuning was performed in this independent benchmark.
- Event target: current glucose ≤180 mg/dL, crossing above 180 within the following 120 minutes with valid contiguous future CGM. Event probability was evaluated separately with a gradient-boosting classifier.
- Uncertainty: 80% absolute-residual width from three subject-grouped OOF training folds, applied without re-calibration to the untouched test subjects. Observed holdout coverage is reported.
- Personalization: prospective EMA residual adjustment, with context (baseline / meal / activity), only after a previous forecast becomes due. The first 30% of each holdout subject's timeline acts as calibration; the last 70% is evaluated. This approximates but **does not exactly reproduce** the app's production adapter.

## 3. Main holdout — actual results

| Horizon | Holdout forecast pairs | Persistence MAE | Linear-trend MAE | ML MAE | ML RMSE | Improvement vs better baseline | Subjects beating persistence |
|---|---:|---:|---:|---:|---:|---:|---:|
| 30 min | 28,109 | 14.82 | 20.08 | **13.09** | 20.03 | **11.65%** | 9/10 |
| 60 min | 28,031 | 22.94 | 38.93 | **20.77** | 31.24 | **9.47%** | 8/10 |
| 120 min | 27,875 | 32.46 | 67.21 | **27.67** | 39.99 | **14.76%** | 7/10 |

All glucose errors are measured in **mg/dL**. Forecast-pair counts are temporally correlated; they are not independent patient samples. The subject-level mean MAE gain over persistence was +1.72 mg/dL (30 min), +2.16 (60 min), and +4.80 (120 min). Subject-resampling bootstrap 95% intervals were approximately [0.96, 2.34], [0.27, 3.83] and [1.00, 8.54] mg/dL, respectively. These intervals come from only ten held-out subjects and should not be read as clinical certainty.

## 4. Five held-out subject splits — robustness

| Horizon | Split 1 | Split 2 | Split 3 | Split 4 | Split 5 | Mean gain | Range |
|---|---:|---:|---:|---:|---:|---:|---:|
| 30 min | 11.65% | 13.31% | 12.35% | 8.97% | 6.60% | 10.58% | 6.60–13.31% |
| 60 min | 9.47% | 11.68% | 11.81% | 9.27% | 9.11% | 10.27% | 9.11–11.81% |
| 120 min | 14.76% | 14.84% | 9.68% | 11.68% | 13.06% | 12.80% | 9.68–14.84% |

The ML forecaster beat the better baseline in every tested horizon/split. This improves confidence that the primary result was not simply a lucky subject split, but **the sample still includes only 45 people, of whom 14 have T2D**.

## 5. New high-glucose onset event — research evaluation

- Eligible origins: observed glucose ≤180 mg/dL, valid uninterrupted upcoming 120-minute CGM.
- Train origins: **82,785**; test origins: **23,131**.
- Positive-label prevalence: train **12.94%**, holdout **23.39%** (material shift).
- Model AUROC: **0.727**; current-glucose-only AUROC: **0.665**.
- Model AUPRC: **0.475**, compared with test event prevalence **0.234**.
- Model Brier score: **0.1654**, versus constant training-prevalence baseline **0.1901**.
- Across five holdout splits, onset AUROC ranged about **0.727–0.826**.

This is **not** a calibrated clinical alarm. The prevalence shift, missing event-episode lead-time metrics, small patient count and lack of clinical action thresholds prevent such a claim.

## 6. Failed safety/evidence gates

| Horizon | OOF 80% half-width (mg/dL) | Actual untouched-holdout coverage | Subject count helped by adaptation | Mean subject personalization MAE gain |
|---|---:|---:|---:|---:|
| 30 min | 18.20 | **77.10%** | **2/10** | **-0.55 mg/dL** |
| 60 min | 25.45 | **73.68%** | **3/10** | **-0.50 mg/dL** |
| 120 min | 32.37 | **70.92%** | **5/10** | **+1.65 mg/dL** |

**Decision:** The forecast population models have promising held-out results, but the **80% intervals under-cover** and the **60-minute adaptive layer worsens mean error**. Neither the 80% certainty claim nor automatic online personalization should be promoted into the live real-data model yet. The official production gate is not being marked PASS.

## 7. What this study establishes — and does not

**Established:** actual acquisition and integrity-checked extraction of the full 45-participant multimodal CSV cohort; leakage-resistant subject-held-out glucose forecasting; baseline comparisons; 120-minute event-onset discrimination; five-split robustness; OOF uncertainty evaluation; chronological residual adaptation experiment.

**Not established:** the unmodified v0.13.0 `train_submission.py` pipeline finishing on real data; ShanghaiT2DM external transportability; nominal uncertainty calibration; validated personalization; prospective episode lead times; native un-interpolated CGM replication; India-specific clinical validation; diagnosis, clinical treatment, or medication dosing safety.

## 8. Recommended next technical decision

Keep the population forecasting approach as an experimental candidate and rerun the canonical production pipeline with the corrected timestamp alignment and activity aliases. **Do not promote real online personalization or 80% uncertainty intervals.** Calibrate uncertainty more conservatively (prefer calibration subjects not used for interval performance claims), test adaptation strategies against no-adaptation across multiple stratified subject folds, verify event episode-level performance and external Shanghai transport, then apply the original fail-closed promotion gate.

## 9. Provenance and license

Remote execution: isolated Vercel Sandbox in Mumbai (`bom1`); Python 3.14.4, pandas 3.0.6, NumPy 2.5.4, scikit-learn 1.9.1. Independent source SHA-256: evaluation `7f9919f175540906a7e33daee2cb01a4b2a2265d4a0b589110c0e56bcd6fa5c3`; validation `ca7540f4c87c1409357684e4409fbbb3f06da5711b91d7bbc70dc386155ed77e`. License of the official CGMacros release: **CC BY-NC-SA 4.0**. No raw subject files or food photographs are redistributed with this report.

## 10. Cloud-side trained weights and exact reproducibility bundle

The **exact trained `.joblib` files, real-data integrity manifest, study Python scripts, seed-specific JSON results, and calibration evidence** were collected in the Vercel cloud workspace as `CGMacros_45_REAL_REPRODUCIBILITY_BUNDLE.zip` (373,886 bytes; SHA-256 `71bd0dee8a8d59e33f30da153d63220822131b955cb288fa09f537af05b8e602`). A restorable **Vercel Sandbox snapshot** preserves that bundle and the 45 CSVs under ID `snap_TNPIjoHxCA7YPFC972z61HAaNq3N` (region `bom1`, source project `v0-project`). The snapshot expires automatically about seven days after creation on 12 October 2026. These cloud files are **not** included in the local download ZIP, because this chat's file-transfer bridge could not import the binary cloud outputs; the downloadable ZIP contains the verified research summary, not deployed model weights.

The snapshot is not a permanent model registry or evidence repository. Restore/export it before expiration if the exact weights or source need to be kept. The default production model remains unchanged and is **not promoted**.
