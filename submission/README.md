# Submission files — HimanshuDigitalTwin

**Team:** `himanshusubh1510` · **Presenter:** Himanshu Shukla · **Institution:** MITS Gwalior

This folder contains the judging assets for a **synthetic, non-clinical** digital-twin research prototype. For code and an immediate run, start at the [root README](../README.md) or [judge quick start](../JUDGE_START_HERE.md).

## Open in this order

| Order | File | Purpose |
|---|---|---|
| **1** | [Six-slide PDF](HimanshuDigitalTwin_Presentation.pdf) · [editable PPTX](HimanshuDigitalTwin_Presentation.pptx) | Read the problem, architecture, demo proof, sensor safety and research boundaries |
| **2** | [Valid synthetic lunch screenshot](Live_Demo_Lunch.png) · [sensor-gap abstention screenshot](Live_Demo_SensorGap.png) | Actual Playwright captures of the running local FastAPI app, **not** fabricated mockups or real patient measurements |
| **3** | [Judge demo instructions](DEMO_RUNBOOK.md) · [recorded synthetic checkpoint trace](judge_verified_demo_trace.json) | Reproduce the six checkpoints without any external patient data |
| **4** | [Architecture PDF](architecture.pdf) · [architecture source](../docs/assets/system-architecture.svg) | Trace data inputs, quality gates, forecast and abstention |
| **5** | [Evidence and limitations](JUDGE_EVIDENCE_INDEX.md) · [independent research report](../backend/reports/research/CGMacros_Real_45_Subject_Evidence_Report_2026-10-12.md) | Understand exactly which results are separate from the active demo |
| **6** | [Official readiness checklist](../SUBMISSION_CHECKLIST.md) | See what is present and what still requires manual submission |

[View all six slides at once](Preview_All_Six_Slides.png) · [Read slide-level notes](PRESENTATION_OVERVIEW.md).

## Regeneration sources

- [Editable-slide generator](generate_native_deck.py): builds actual PowerPoint shapes, text and vectors; slide 4 embeds a crop of the verified browser screenshot.
- [Browser screenshot capture](capture_demo.py): starts localhost FastAPI, selects synthetic Lunch/Sensor gap, asserts the expected status and saves PNGs.
- [GitHub Actions presentation build](../.github/workflows/build-presentation.yml): captures actual browser states, generates the PPTX, renders a PDF and verifies six pages.

`Presentation.html` is an **earlier browser-slide draft**, not the current PowerPoint source of truth. `trace_reproduction_v022.json` is supplementary technical output, not proof of clinical validation.

## What is *not* supplied or verified

The required genuine **minimum-20-minute** unlisted YouTube video link is not provided. [Recording plan](VIDEO_RECORDING_PLAN.md) is not a completed video. The registered roster, acceptance of this repository/folder structure, anonymous external downloads and the competition-platform acknowledgement still need review. No trained research model is claimed to be promoted into the synthetic demo.

**Clinical boundary:** The system is for demonstration and methodology review only. Never use its readings, risk percentages or forecasts for clinical decisions, diagnosis, treatment or medication dosing.
