# Judge quick start — HimanshuDigitalTwin

**Team:** himanshusubh1510 · **Presenter:** Himanshu Shukla · **College:** MITS Gwalior  
**Goal:** Inspect a reproducible **synthetic** glucose digital twin and its explicit sensor-data abstention behavior.

![Readable architecture diagram](docs/assets/system-architecture.svg)

## Run the working default prototype

Requirements: Python 3.11+.

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**, then use **Guided judge demo** (the FastAPI-served application; the optional Next.js source is not needed).

| Checkpoint | What to inspect |
|---|---|
| Baseline | A synthetic patient profile and versioned state |
| Breakfast | Input context and forecast changes |
| Lunch | Timestamped observation and 30/60/120-minute predictions |
| Verification | Previous forecast resolution against later synthetic observations |
| **Sensor gap** | Withheld glucose, no valid prediction, no risk percentage |
| Recovery | Valid observation returns; forecasting becomes available |

The sensor gap should produce `quality=IMPUTED`, `glucose=null`, `forecast_status=ABSTAINED`, `excursion_risk=null` and an empty `forecasts` array. A missing reading must **never** be presented as 0% risk.

## Replay isolation check

Use two browser profiles to verify that one profile's synthetic replay changes do not affect the other. Two tabs within a single profile share the same cookie. Automated checks are in `backend/tests/test_browser_session_isolation.py`. These temporary demo sessions are not accounts or persistent storage.

## Independently check software behavior

From the **repository root**:

```bash
python backend/scripts/verify_judge_submission.py
python -m pytest backend/tests -q
```

Tests demonstrate software consistency and guardrails. They do **not** validate clinical efficacy or reproduce the original independent CGMacros model training.

## Find the evidence

- [Architecture PDF](submission/architecture.pdf) · [editable architecture SVG](docs/assets/system-architecture.svg)
- [Technology stack figure](docs/assets/technology-stack.svg) · [technical reference](docs/ARCHITECTURE_AND_MODELS.md)
- [Six-slide presentation PDF](submission/HimanshuDigitalTwin_Presentation.pdf) · [PPTX](submission/HimanshuDigitalTwin_Presentation.pptx)
- [Separate 45-participant CGMacros evidence and limits](submission/JUDGE_EVIDENCE_INDEX.md)
- [Submission checklist](SUBMISSION_CHECKLIST.md) — video, registered team roster and Unstop acceptance still unconfirmed

**Medical safety notice:** The running default forecaster is a heuristic/synthetic demonstrator. The separate CGMacros benchmark results are not active-runtime performance. No diagnosis, treatment, insulin dosing, or clinical monitoring should rely on this prototype.
