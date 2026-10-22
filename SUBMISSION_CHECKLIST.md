# Hackathon submission acceptance checklist

**Project:** HimanshuDigitalTwin  
**Team:** himanshusubh1510  
**Presenter:** Himanshu Shukla  
**Institution:** Madhav Institute of Technology and Science (MITS), Gwalior  
**Public source:** https://github.com/himanshu051116/Himanshu-DigitalTwin

This checklist follows the 12 submission requirements supplied by the participant. A tick means there is a **specific published artifact**; it does not imply organizer acceptance. **As of 23 October 2026: 9 fully documented, 3 pending verification/completion.**

- [ ] **1. Team details — PARTIAL.** The team name and presenter are in [README](README.md), but the officially registered leader, full roster and registration identifiers have not been independently confirmed. Do not invent additional members.
- [x] **2. College / incubator information.** MITS Gwalior is specified in the [README](README.md). No incubator is claimed because none is confirmed.
- [x] **3. Project title.** HimanshuDigitalTwin appears in the [README](README.md) and [presentation](submission/HimanshuDigitalTwin_Presentation.pdf).
- [x] **4. Problem statement.** See [The problem](README.md#the-problem): a single glucose reading lacks contextual near-term forecasting and sensor reliability can invalidate predictions.
- [x] **5. Healthcare use case.** Type-2 diabetes / glucose-excursion research with 30/60/120-minute forecasts; see [Healthcare use case](README.md#the-problem). **Not a clinical decision tool.**
- [x] **6. Technical stack.** FastAPI/Python backend, HTML/CSS/JavaScript demonstrator, scikit-learn research models, pandas/NumPy, optional Next.js frontend; see [Technical stack](README.md#technical-stack).
- [ ] **7. 15–20-minute unlisted YouTube demo with link in README — MISSING.** No actual video URL is supplied. The [recording plan](submission/VIDEO_RECORDING_PLAN.md) is **not** a substitute. Record/upload, check accessible unlisted status, then add URL to README and `submission/submission_metadata.json`.
- [x] **8. AI/ML framework and model details.** See [AI / ML models](README.md#ai--ml-models-and-framework) and [research evidence](backend/reports/research/). Canonical training specifies histogram gradient boosting for regression and logistic regression for event classification; current interactive model is simulated, **not** a promoted research artifact.
- [x] **9. Open-source licence.** [MIT LICENSE](LICENSE) is present. This does not relicense third-party CGMacros or Shanghai datasets.
- [x] **10. Architecture PDF/PPT.** [architecture.pdf](submission/architecture.pdf) is committed.
- [x] **11. Presentation PDF/PPT with project and outcomes.** [Six-slide PDF](submission/HimanshuDigitalTwin_Presentation.pdf), [PPTX](submission/HimanshuDigitalTwin_Presentation.pptx), and [overview](submission/PRESENTATION_OVERVIEW.md) are committed.
- [ ] **12. All files and links accessible without additional permissions — PARTIAL.** The repository is marked **public** and source, PDF/PPTX, and licence paths resolve through the connected GitHub service. Anonymous download verification has not independently succeeded in this environment, and there is no YouTube link to check. Verify in a private/incognito browser.

## Final publication checks

1. Confirm the full registered team roster and leader against the Unstop entry.
2. Upload **the actual 15–20-minute demonstration** as **Unlisted** to YouTube.
3. Paste its complete URL into the README and metadata; test it in an incognito window. Unlisted videos are link-accessible, but private videos are not.
4. Open the public repository, [architecture PDF](submission/architecture.pdf) and [presentation PDF](submission/HimanshuDigitalTwin_Presentation.pdf) without authentication.
5. Check whether the competition portal accepts a late submission or has issued an extension; its originally stated **20 October 2026** deadline has passed. Record the actual portal submission receipt if successful.

## Evidence boundary

The interactive showcase uses a synthetic patient and heuristic/uncalibrated risk. The separate 45-subject CGMacros experiment reports research-only results; it is **not** the deployed forecast model. A checked code/documentation requirement must never be interpreted as proof of clinical validation.
