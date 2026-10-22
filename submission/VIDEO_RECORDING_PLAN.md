# Minimum 20-minute demonstration video guide

**Project:** HimanshuDigitalTwin  
**Team:** himanshusubh1510  
**Presenter:** Himanshu Shukla  
**Institution:** MITS Gwalior

**Video status: NO VERIFIED VIDEO URL IN THE REPOSITORY.** This document is a recording plan, **not** an actual video.

The [official competition guidelines](https://unstop.com/hackathons/crp-digital-twin-challenge-2026-happiest-health-1757873) specify **a minimum 20-minute** video, not an upper limit of 20 minutes. Record the real browser and terminal experience, upload the result to YouTube as **Unlisted**, then add its complete accessible video URL to both the repository root `README.md` and `submission/submission_metadata.json`. Check that the final duration is **at least 20 minutes** (aim for approximately 21 minutes of substantive recording rather than an exactly 20:00 cut) and the link plays without permissions or sign-in from a separate browser session.

| Timeline | Show on screen | Explain accurately |
|---|---|---|
| 00:00–01:15 | Title slide and team details | Healthcare problem; current system is a research prototype |
| 01:15–03:00 | Six-slide presentation problem/use-case pages | Why patient context and glucose history matter for near-term forecasts |
| 03:00–04:30 | Architecture PDF | How phenotype, CGM, meals and activity become a synchronized patient state |
| 04:30–09:15 | Guided baseline, meal and prediction chapters | Actual recorded **synthetic** replay values, time stamps and forecast horizons |
| 09:15–12:00 | Sensor-gap and recovery chapters | Clear demonstration of missing/stale CGM and forecast/risk **abstention** |
| 12:00–13:45 | Dashboard explanation and historical verification | Show sensor/data confidence, state changes and later observed outcomes |
| 13:45–16:30 | Evidence & Safety and research report | The independent 45-subject CGMacros cohort, MAE versus baseline, and its limits |
| 16:30–18:15 | Repository and code/demo launch | Public README, architecture, presentation and reproducible app startup |
| 18:15–20:45 | Live reproducibility checks, questions addressed, and limitations | Show the model-status endpoint, attempt the replay verification script, distinguish the separate CGMacros study from the active demo, then close with the limitations and exact next validation steps |

## Recording quality and claims

- Use the **actual application** and real repository, not fabricated or AI-redrawn interfaces.
- Record at 1080p or higher with legible cursor, text and charts; verify audio/video before uploading.
- Label synthetic forecasts and risk percentages clearly. Never imply they are calibrated probabilities or medical recommendations.
- When presenting the 45-person CGMacros findings, identify them as **independent research evidence**, not live-demo model performance.
- Avoid showing private personal data, medical records, API keys or account credentials.
- If screen recording cannot be finished, **do not enter a placeholder link** or claim requirement #7 is complete.

## Publication action

After a genuine video of **at least 20 minutes** is uploaded:

1. Copy its full `https://www.youtube.com/watch?v=...` or `https://youtu.be/...` link.
2. Insert the link under the root README's **Demonstration video** heading.
3. Update `submission/submission_metadata.json` with `demo_video_url`, actual `demo_video_duration_minutes`, and `video_link_access_confirmed` only after personally checking accessibility.
4. Change requirement #7 in `SUBMISSION_CHECKLIST.md` to complete only after verifying the above.
