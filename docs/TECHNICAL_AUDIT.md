# Technical readiness audit — 23 October 2026

**Repository:** [Himanshu-DigitalTwin](https://github.com/himanshu051116/Himanshu-DigitalTwin)  
**Scope:** The actual default FastAPI browser demo, optional Next.js frontend, synthetic replay engine, documentation, submission artifacts, and test infrastructure.

This document distinguishes **confirmed source-code observations** from **changes made** and **verification not yet completed**. It does not certify runtime deployment, research validity, or hackathon acceptance.

## Priority findings and corrections

| Severity | Evidence in repository | Confirmed finding | Corrective work | Status |
|---|---|---|---|---|
| Critical | `backend/app/engine.py`, `backend/static/app.js` | Internally carried glucose values were included in the exposed observed timeline, and older chart logic could draw them as observed glucose. | Public `recent_history` now removes glucose values for non-`VALID` samples; both charts draw only verified observations and break on gaps; tests added. | **Code committed; full CI not confirmed** |
| High | `backend/static/app.js`, `frontend/app/page.tsx` | Forecast x positions used array indices, misleadingly spacing 30-, 60-, and 120-minute horizons equally. | Both charts now use timestamps and horizon minutes as real horizontal coordinates. | **Code committed; browser screenshots not yet verified** |
| High | `backend/app/main.py` previous global `SESSIONS` | Multiple browsers previously mutated the same synthetic patient state. | Replaced with anonymous browser-isolated ephemeral sessions, per-session locks, WebSocket cookie checks and expiration; added isolation tests. | **Code committed; full CI not yet confirmed; still not production identity/persistence** |
| Medium | `backend/static/app.js` initialization | Failure of optional cohort/status requests could abort demo startup. | Synthetic demo is loaded first; ancillary endpoints settle independently with explanatory fallbacks. | **Code committed; runtime test not yet confirmed** |
| Medium | `backend/static/app.js` replay mutation paths | Autoplay, manual steps and chapter loads could overlap; failed autoplay previously could leave ambiguous controls. | Replay mutation queue, serialized chapter/data loads and visible error state. | **Code committed; stress test not yet confirmed** |
| Medium | `frontend/app/page.tsx` | Optional UI lacked guided judge chapters and clear API error feedback. | Added six-chapter selection, explicit errors, and sensor-aware chart labels. | **Code committed; Next.js build not yet confirmed** |
| Medium | `backend/static/index.html`, `backend/static/styles.css` | No concise live explanation of observation quality to forecast eligibility. | Added responsive three-stage signal/quality/output status strip. | **Code committed; mobile visual QA not yet confirmed** |

## What remains non-negotiable before claiming production readiness

1. **Authentication, persistence and production architecture:** Anonymous browser replay isolation is now implemented, but is **not authentication**. Sessions expire after 30 minutes and are bounded to 32 per process; multi-worker replicas do not share their state, and no durable identity or audit retention exists. A public server must never expose private research/patient records without separate secure access controls and data governance.
2. **Real model verification:** Run the canonical training pipeline on authorized research cohorts, reproduce independently reported results with locked subject-level splits, and enforce promotion gates. The current interactive forecaster remains heuristic/simulated.
3. **Clinical research limits:** Only 3 Type-2 diabetes participants were in the primary 10-person holdout of the separate CGMacros study. Interval calibration, personalization and Shanghai external validation have not passed the documented acceptance gates.
4. **Real browser QA:** Check missing-data gaps, forecast withholding, chapter switching, rapid-click recovery and narrow-screen layout in Chromium, Firefox and mobile Safari/Chrome. No claim of completed visual testing is made here.
5. **CI and build verification:** Verify successful GitHub Actions runs for Python tests, default-dashboard JavaScript syntax and React/TypeScript checks. No passing run has yet been independently confirmed.
6. **Dependency reproducibility:** Python range constraints and the missing frontend npm lockfile do not yet define a fully reproducible release. Generate and verify lockfiles in a controlled build environment before packaging.
7. **Submission evidence:** Add a genuine minimum-20-minute accessible unlisted demo video to the README and metadata; confirm the registered roster, every public download, and actual Unstop acknowledgement.

## Browser replay isolation (new)

`backend/app/browser_sessions.py` allocates an independent replay state for each accepted anonymous visitor token. HTTP routes now resolve their state through a server-issued HTTP-only cookie, use a session lock for mutations and present no cross-browser shared replay state in normal single-process operation. WebSocket replay requires the same visitor cookie. The separate `backend/tests/test_browser_session_isolation.py` asserts two visitors do not change each other's twin version, unknown cookies mint new tokens, WebSockets reject missing tokens, and expiration/capacity are enforced. The judge verification script also checks independent visitors after the trace comparisons.

**Still unverified:** successful CI completion of the new tests, high-concurrency performance, browser behavior across reverse proxies, multi-process deployment, and handling of real protected patient datasets.

## Exact software claims the judge can independently check

- The synthetic test patient `HDT-027` has six guided checkpoints; `sensor_gap` must return `forecast_status=ABSTAINED`, `excursion_risk=null`, and `forecasts=[]`.
- For invalid or non-`VALID` historical readings, the public `recent_history` should contain `glucose=null` rather than a carried-forward value. An internal carry-forward feature may still support short-gap *extrapolation* within the 15-minute freshness rule.
- Horizon positions on the chart should reflect the actual 30-, 60-, and 120-minute offsets; gaps should not be drawn as verified continuous glucose.
- Default browser prototype is served by the FastAPI backend; the Next.js project is an optional alternative UI.
- The CGMacros study metrics are from a separate experiment and not the currently running heuristic-demo model.

## Reproducibility commands

```bash
python -m pip install -r backend/requirements.txt
python -m pytest backend/tests -q
python backend/scripts/verify_judge_submission.py
node --check backend/static/app.js
python backend/scripts/submission_readiness.py
```

The readiness command intentionally returns a nonzero exit status while competition/recording attestations are incomplete. A green code test suite alone would not imply `READY` submission status or clinical efficacy.

**Documentation source:** [README](../README.md) · [Architecture](ARCHITECTURE_AND_MODELS.md) · [Evidence index](../submission/JUDGE_EVIDENCE_INDEX.md) · [Submission checklist](../SUBMISSION_CHECKLIST.md)
