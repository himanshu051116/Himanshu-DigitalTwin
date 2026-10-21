# HimanshuDigitalTwin

**Team:** himanshusubh1510  
**Presenter:** Himanshu Shukla  
**Institution:** Madhav Institute of Technology and Science (MITS), Gwalior  
**Challenge:** Happiest Health Digital Twin Challenge 2026

HimanshuDigitalTwin is a research prototype for short-term blood-glucose forecasting. It combines baseline patient information with incoming glucose, meal and activity observations to maintain a patient-specific state, show 30-, 60- and 120-minute forecast scenarios, and withhold predictions when the sensor data is unreliable.

## Run the demonstrator

Requirements: Python 3.11+ recommended.

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. In the dashboard, choose the **Guided judge demo** chapters to replay the synthetic patient journey, including valid readings, sensor-data loss and recovery. The demonstration does not require downloading patient data.

## What to inspect

| Deliverable | Location |
|---|---|
| Six-slide hackathon presentation | [PDF](submission/HimanshuDigitalTwin_Presentation.pdf) · [PPTX](submission/HimanshuDigitalTwin_Presentation.pptx) |
| System architecture | [PDF](submission/architecture.pdf) · [PPTX](submission/architecture.pptx) |
| Demo and recording outline | [Walkthrough](submission/DEMO_RUNBOOK.md) · [Video plan](submission/VIDEO_RECORDING_PLAN.md) |
| Claim-to-evidence guide | [Evidence index](submission/JUDGE_EVIDENCE_INDEX.md) |
| Independent CGMacros evidence | `backend/reports/research/` and `GET /api/research/evidence` |
| Research and API source | `backend/app/`, `backend/scripts/`, `backend/tests/` |

### Verify the synthetic replay

From the repository root:

```bash
python backend/scripts/verify_judge_submission.py
python -m pytest backend/tests -q
```

These checks verify software behaviour, **not clinical efficacy**.

## Research results and limitations

A **separate independent experiment** used the CGMacros research cohort (45 participants, including 14 with Type-2 diabetes). On its primary patient-grouped holdout, forecast mean absolute errors (MAE, mg/dL) were **13.09 / 20.77 / 27.67** at **30 / 60 / 120 minutes**, versus a last-observation persistence baseline of **14.82 / 22.94 / 32.46**. This evidence is reported in the included research materials. The standalone benchmark models are **not the model running in the interactive demonstration**, and its independent benchmark results have not been reproduced by the canonical application trainer.

The default interactive demo uses **simulated patient records and uncalibrated predictions**. Its risk percentages must not be used for clinical decisions. Personalized adaptation and trained uncertainty intervals have **not passed approval gates**; external Shanghai-cohort validation has not been completed. The prototype is **not approved for diagnosis, treatment, insulin dosing or clinical deployment**.

## Technology

FastAPI and Python for the API and model/evidence pipeline; HTML, CSS and JavaScript for the clinician-oriented dashboard; NumPy, pandas and scikit-learn in the research workflow. The included tests exercise replay determinism, sensor-data validation, predictions, submission evidence and model-promotion safeguards.

## Status

Code, presentation and architecture are provided in this repository once published. A recorded demonstration video and confirmed Unstop submission receipt must be supplied separately; neither is claimed by this README.

## License

See [LICENSE](LICENSE).
