# HimanshuDigitalTwin — reproducible jury demonstration

**Presenting team:** himanshusubh1510. **Presenter:** Himanshu Shukla (as documented in the repository). Official team roster, registered leader and registration status still require verification against the Unstop entry.

**Scope:** Happiest Health Digital Twin Challenge 2026. This six-chapter story runs entirely on deterministic **simulated** patients. It does **not** use the independent CGMacros study's fitted research models in the live demo. The app never recommends insulin or treatment.

## Before recording

Run `run_local.bat` on Windows or `cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`; navigate to `http://127.0.0.1:8000` and verify the model status says **demo heuristic** and **not promoted**. Use an incognito/private browser window to verify a public repository and unlisted-video link before submitting. Do not upload real patient records or sensor CSVs into GitHub.

## Guided story (the selector above the replay buttons)

| Chapter | What to show | Honest commentary |
|---|---|---|
| Baseline | Age, BMI, HbA1c, CGM, heart-rate and versioned time | Static phenotype + dynamic simulated stream become one replay state. |
| Breakfast | Meal-associated changes and 30/60/120-minute trajectories | A forecast is generated at a specific timestamp; it is not a clinical prescription. |
| Lunch | The glucose chart and changing directional factors | Streaming updates synchronize the virtual state; show evidence labels. |
| Verification | Population vs personalized error and forecast resolutions | Only predictions whose due time has passed can be scored. This adaptation is a **demo mechanism**; independent research did not approve automatic real-world personalization. |
| Sensor gap | Quality label `IMPUTED`, absent forecast and risk, `DEGRADED` state | The system withholds predictions when genuine CGM history is too old. |
| Recovery | Forecast display resumes once genuine observations return | Versioned replay continues and all sensor-quality events remain auditable. |

Click **Show chapter** after choosing each chapter. All checkpoints reset and replay the same `HDT-027` synthetic stream. Repeat any chapter for reproducible results.

## The independent REAL research evidence (separate tab)

Open `Evidence & safety`. Explain CGMacros has 45 real anonymized participants, while the **independent** held-out benchmark produced forecast MAE of **13.09 / 20.77 / 27.67 mg/dL** over 30 / 60 / 120 minutes, versus persistence **14.82 / 22.94 / 32.46 mg/dL**. Real-data onset AUROC was **0.727** versus **0.665** current-glucose-only. The independent study is not the fitted live-demo model; the revised canonical trainer has not completed a real-cohort run.

## A scenario (non-causal)

Open `Scenario lab`, move carbohydrate and activity controls, then click `Run exploratory scenario`. State explicitly that the two forecasts are model-based estimates under changed inputs, not intervention outcomes, validated treatments or dosing instructions.

## Evidence and failure handling

Open `/api/model/status` to show honest `runtime_promotion_allowed=false`. A formal approval requires a real-data canonical pipeline and locked holdout, not the passing software test suite. Explain that automatic personalization and 80% calibrated intervals were **not approved** by the earlier independent experiment.

## Required final verification

Record the demo and commentary video; publish the repository and verify the public URL. Fill `submission/submission_metadata.json`, run `python backend/scripts/submission_readiness.py --out submission/readiness.json`, and only submit to Unstop when the gate is READY. A successful readiness gate records manual attestations but **does not** replace checking the live Unstop entry confirmation.
