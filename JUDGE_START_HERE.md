# Judge quick start

**HimanshuDigitalTwin** · **Team himanshusubh1510** · **Presenter Himanshu Shukla** · MITS Gwalior

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Visit http://127.0.0.1:8000 and choose the guided synthetic demo: baseline → lunch → verification → sensor gap → recovery. In the sensor-gap chapter, missing or stale glucose must cause the system to **withhold** forecasts and risk. Synthetic output is never presented as a clinically calibrated prediction.

The six-slide pitch is `submission/HimanshuDigitalTwin_Presentation.pdf`, architecture is `submission/architecture.pdf`, and supporting research information is in `backend/reports/research/`.

Run `python backend/scripts/verify_judge_submission.py` and `python -m pytest backend/tests -q` from the repository root to reproduce the software checks. These do not reproduce the separate independent CGMacros benchmark or establish clinical validation.
