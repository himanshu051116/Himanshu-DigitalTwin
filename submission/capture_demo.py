"""Capture actual localhost research-demo screens. Never fabricate screenshots.

The app runs with bundled synthetic patients only, no downloaded medical data.
In CI, Playwright launches a real Chromium browser and writes two reproducible PNGs.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OUT = ROOT / "submission"


def wait_for_server(address: str, process: subprocess.Popen, timeout: float = 30) -> None:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if process.poll() is not None:
            raise RuntimeError("FastAPI exited before becoming ready")
        try:
            with urllib.request.urlopen(address + "/api/health", timeout=1) as r:
                if r.status == 200:
                    return
        except (OSError, TimeoutError):
            time.sleep(0.25)
    raise TimeoutError("FastAPI localhost health endpoint did not become ready")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", type=Path, default=OUT)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    host = "http://127.0.0.1:18760"
    env = dict(os.environ)
    # Explicitly keep optional downloaded cohort data and research model overrides out.
    env.pop("HDT_MODEL_DIR", None)
    env.pop("HDT_DATA_ROOT", None)
    env.pop("HDT_ALLOW_UNPROMOTED_TRANSPORT", None)

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", "18760"],
        cwd=str(BACKEND), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    try:
        wait_for_server(host, proc)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                context = browser.new_context(
                    viewport={"width": 1600, "height": 1000},
                    device_scale_factor=1.25, reduced_motion="reduce",
                )
                page = context.new_page()
                page.goto(host + "/", wait_until="networkidle", timeout=30000)
                expect(page.locator("#judgeChapter")).to_be_visible()
                expect(page.locator("#signalSummary")).to_contain_text("forecast", timeout=15000)

                page.locator("#judgeChapter").select_option("lunch")
                page.locator("#judgeDemoBtn").click()
                expect(page.locator("#judgeDemoBtn")).to_have_text("Show chapter")
                expect(page.locator("#signalOutput")).to_have_text("3 forecast horizons")
                expect(page.locator("#glucose")).not_to_contain_text("—")
                page.screenshot(
                    path=str(args.outdir / "Live_Demo_Lunch.png"),
                    full_page=False, animations="disabled",
                )

                page.locator("#judgeChapter").select_option("sensor_gap")
                page.locator("#judgeDemoBtn").click()
                expect(page.locator("#judgeDemoBtn")).to_have_text("Show chapter")
                expect(page.locator("#signalOutput")).to_have_text("Forecast withheld")
                expect(page.locator("#risk")).to_have_text("Withheld")
                expect(page.locator("#glucose")).to_contain_text("—")
                page.screenshot(
                    path=str(args.outdir / "Live_Demo_SensorGap.png"),
                    full_page=False, animations="disabled",
                )
                print("Captured verified synthetic lunch and sensor-gap states.")
            finally:
                browser.close()
    finally:
        proc.terminate()
        try:
            proc.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()


if __name__ == "__main__":
    main()
