# Architecture, model boundaries, and implementation map

This document describes the code in this repository, **not** a deployed clinical system. The working judge demonstration is a synthetic replay with a heuristic forecaster. Independent model training and benchmarks do not automatically replace the demo model.

![Runtime architecture diagram](assets/system-architecture.svg)

## 1. Two paths with different evidence standards

| Path | Source of truth | What it establishes | What it does not establish |
|---|---|---|---|
| **Interactive demo** | `backend/app/main.py`, `engine.py`, `model.py`, `backend/static/` | A repeatable patient-specific state, quality checks, illustrative forecasts, later verification and audit history | Clinical accuracy, calibrated risk or clinical utility |
| **Research training** | `backend/scripts/`, `backend/app/artifacts.py`, `backend/reports/research/` | Training/evaluation components, model-artifact handling and separately reported CGMacros findings | That independent benchmark weights are the ones serving predictions in the demo |
| **Alternate UI** | `frontend/app/page.tsx`, `frontend/package.json` | Additional Next.js/React dashboard source | That the Next.js app is required for or deployed with the default FastAPI demo |

## 2. Data → patient state → forecast or abstention

1. **Profile and observations.** `backend/app/data.py` creates synthetic patient streams. `backend/app/real_replay.py` contains separately gated real-cohort adapters when data is legitimately available locally. No private cohort data is required for the synthetic judge walkthrough.
2. **Synchronized state.** `ReplaySession` in `backend/app/engine.py` maintains timestamps, history, version, prediction reconciliation and an event timeline.
3. **Sensor quality.** If glucose is missing, out-of-date, or otherwise unreliable, the replay does **not** invent a valid reading. The canonical judge sensor-gap case returns a null glucose, an empty forecast array, and no excursion risk, with `forecast_status=ABSTAINED`.
4. **Active prediction.** In the default environment the simulation uses the `demo-heuristic` forecaster from `backend/app/model.py`; three time horizons are presented at +30, +60 and +120 minutes. **Demo risk percentages and forecast intervals are not calibrated medical estimates.**
5. **Reconciliation.** When a later synthetic observation has reached the horizon of a pending forecast, the engine can record the deviation, update replay-specific residual information and preserve audit events. This does not establish real-world personalized benefit.
6. **Model promotion.** `backend/app/artifacts.py` and model-status checks restrict what trained artifacts may replace the default runtime. Passing software tests alone never promotes a research candidate.

## 3. Key endpoints

| Endpoint | Purpose |
|---|---|
| `GET /` | Default browser prototype (FastAPI-served HTML/CSS/JS) |
| `GET /api/health` | Service health |
| `GET /api/patients` | Available demo patient profiles |
| `POST /api/replay/{patient_id}/reset` | Reset one replay |
| `POST /api/replay/{patient_id}/step?steps=1` | Advance recorded synthetic observations |
| `GET /api/demo/chapters` | Enumerate six guided synthetic checkpoints |
| `POST /api/demo/chapter/{chapter_id}` | Reproduce a named demo checkpoint |
| `POST /api/scenario` | Explore changed hypothetical inputs without prescribing an intervention |
| `GET /api/model/status` | Current model, promotion and external-validation gate status |
| `GET /api/research/evidence` | Read the separately reported independent CGMacros evidence |
| `GET /api/evidence` | Structured evidence and safety assumptions |
| `POST /api/fhir/ingest` | Parse FHIR phenotype inputs under the implemented API contract |

Real-cohort load endpoints exist, but only operate if legitimately obtained input files are available and correctly formatted locally. They are **not** required or claimed as ready for clinical use.

## 4. Exact stack

![Technology stack showing default and separate toolchains](assets/technology-stack.svg)

The default judge workflow uses **Python (3.11+), FastAPI, Pydantic, Uvicorn, NumPy, pandas, plain HTML, CSS and JavaScript**. The research code uses **scikit-learn and joblib**. Tests use **pytest and httpx**. An **optional** `frontend/` tree has **Next.js 16.0.0, React 19.2.0 and TypeScript 5.9.x** in its committed manifest.

There is no evidence that a medical-device platform, hospital EHR, continuously live production CGM source, or cloud deployment is configured by these dependency lists.

## 5. Model details and the evidence boundary

The canonical research training approach specifies **`HistGradientBoostingRegressor`** for the three regression horizons and **`LogisticRegression`** for the onset-event research target. Participant-grouped validation avoids leaking adjacent rows from the same patient across train and test. Artifact-integrity checks and promotion gates exist; do not label them as clinical certification.

### Independent reported CGMacros findings

![Independent study comparison](assets/research-evidence.svg)

| Horizon | Persistence MAE (mg/dL) | Separate study ML MAE (mg/dL) |
|---|---:|---:|
| 30 minutes | 14.82 | 13.09 |
| 60 minutes | 22.94 | 20.77 |
| 120 minutes | 32.46 | 27.67 |

The primary held-out evaluation included **10 participants**, of whom **3** had Type-2 diabetes. Those pooled results do not represent a validated Type-2 diabetes-only model or the active heuristic UI. Original training artifacts and participant datasets from the independent study are not reproduced in this repository. The canonical training workflow has not yet reproduced that benchmark; external Shanghai validation is incomplete.

## 6. Reproduce what is actually verifiable

From the repository root:

```bash
python -m pip install -r backend/requirements.txt
python backend/scripts/verify_judge_submission.py
python -m pytest backend/tests -q
```

Then start the app:

```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`, select **Guided judge demo** and visit the **Sensor gap** chapter. It should show a withheld forecast rather than replacing unavailable glucose with a confidently presented number.

For submission metadata, run `python backend/scripts/submission_readiness.py` from the root. A `NOT_READY` report is expected while team registration, an accessible minimum-20-minute video, and competition-platform submission remain unconfirmed. The checker validates local inventory and self-attestations, not actual portal acceptance.

## 7. Security, licensing and scope

- Keep identifiable medical data, private CGM exports, credentials, and protected third-party datasets out of the public repo.
- The [MIT LICENSE](../LICENSE) covers the repository software and documentation; upstream datasets retain their original terms.
- Hypothetical changes in meals or activity in the Scenario Lab are **not** causal treatment-effect estimates.
- Never use the forecasts, intervals, risk percentages or chart graphics here for patient care.
- The vector diagrams in `docs/assets/` are editable visual descriptions of this codebase, **not screenshots or independent clinical evidence**.

[Back to project overview](../README.md) · [Judge evidence index](../submission/JUDGE_EVIDENCE_INDEX.md) · [Acceptance checklist](../SUBMISSION_CHECKLIST.md)
