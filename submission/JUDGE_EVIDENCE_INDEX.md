# HimanshuDigitalTwin — judge verification index

**Project:** HimanshuDigitalTwin · **Team:** himanshusubh1510 · **Presenter:** Himanshu Shukla

This index distinguishes features a judge can **execute**, research findings reported from a **separate study**, and important **unverified** claims. Nothing here certifies a clinical device.

**Visual verification aids:** [system architecture](../docs/assets/system-architecture.svg) · [technology stack](../docs/assets/technology-stack.svg) · [independent benchmark chart](../docs/assets/research-evidence.svg). The images are original schematic representations and are **not** screenshots or live model evidence.

## Verify the working prototype (no real patient dataset required)

From the public repository **root**:

```bash
python -m pip install -r backend/requirements.txt
python backend/scripts/verify_judge_submission.py --out submission/trace_reproduction_v022.json
python -m pytest backend/tests -q
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` and navigate the six **Guided judge demo** checkpoints, especially **Sensor gap**. Run `node --check backend/static/app.js` to check frontend syntax if Node is available.

| Claim shown | Judge-accessible evidence | What a PASS establishes |
|---|---|---|
| Six synthetic patient checkpoints are reproducible | `submission/judge_verified_demo_trace.json`; `backend/scripts/verify_judge_submission.py` | The bundled demo API reproduces those six artificial states and the recorded forecast fields |
| A stale or invalid sensor triggers abstention | `POST /api/demo/chapter/sensor_gap`; `backend/tests/test_safety_v016.py` | The synthetic gap yields `quality=IMPUTED`, `glucose=null`, `risk=null`, `forecasts=[]`, and `forecast_status=ABSTAINED` |
| State versioning and later forecast reconciliation exist | `POST /api/demo/chapter/verification`; `backend/app/engine.py`; `backend/tests/test_judge_demo_v019.py` | The replay maintains a versioned state and a running audit; it is **not a clinical performance result** |
| Real 45-participant study was reported | `backend/reports/research/cgmacros_45_2026-10-12.json` and dated study report | Documentation of a *separate* experiment; not independent reproduction of that experiment |
| Population model is not silently activated | `GET /api/model/status` and `backend/tests/test_artifacts.py` | Unapproved trained candidates remain unpromoted in this packaged runtime |
| Submission completeness | `backend/scripts/submission_readiness.py` with `submission/submission_metadata.json` | Local file inventory and self-attested link fields **only**; not verification that Unstop accepted the entry |

## Browser replay state

The default FastAPI app now keeps separate ephemeral synthetic replay states per browser cookie. The test file `backend/tests/test_browser_session_isolation.py` and the judge verification script check that two clients maintain independent replay versions. This is not authentication, persistence, or clinical-data security.

## Scientific metrics: interpret with explicit limitations

The independent CGMacros experiment involved **45 participants**: 15 with no diabetes, 16 with prediabetes and 14 with Type-2 diabetes. The primary participant-held-out split contained **35 training / 10 holdout participants**, of whom **3 holdout participants had T2D**.

| Horizon | Independent ML MAE | Persistence MAE | Relative improvement | Holdout coverage of nominal 80% interval |
|---|---:|---:|---:|---:|
| 30 min | 13.09 mg/dL | 14.82 mg/dL | 11.65% | 77.10% |
| 60 min | 20.77 mg/dL | 22.94 mg/dL | 9.47% | 73.68% |
| 120 min | 27.67 mg/dL | 32.46 mg/dL | 14.76% | 70.92% |

**Never claim:** these are T2D-only results, the fitted research model is serving forecasts in the demo, the interval attains nominal coverage, patient adaptation is clinically beneficial, Shanghai validation has passed, or the product is safe for diagnosis, insulin dosing or therapy decisions. The study's original independent training scripts and CGMacros participant data are not included in this repository; the canonical trainer has not reproduced that experiment.

## What still requires the team leader's direct action

- Confirm the team roster and registration on Unstop.
- Keep the public repository accessible to judges and verify the README, runnable source, presentation and architecture files using a signed-out browser.
- Upload the minimum-duration demo video **as specified in the participant dashboard**; open the video link in a signed-out browser.
- Enter the public GitHub URL, leader details and submission form fields in Unstop; capture the actual platform acknowledgement.

These tasks are **not** represented as complete merely because PDFs and slides exist. Keep private phone/email on the competition form rather than in public repository files.
