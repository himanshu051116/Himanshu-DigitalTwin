"""Guard against an HTML/JavaScript selector drift in the canonical judge UI."""
from html.parser import HTMLParser
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend/static/app.js"
PAGE = ROOT / "backend/static/index.html"


class IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == "id" and value:
                self.ids.add(value)


def test_every_literal_default_dashboard_selector_has_an_element():
    script = SCRIPT.read_text(encoding="utf-8")
    html = PAGE.read_text(encoding="utf-8")
    collector = IdCollector()
    collector.feed(html)
    selectors = set(re.findall(r"\$\('#([A-Za-z0-9_-]+)'\)", script))
    assert selectors, "No script selectors found; check test regex"
    missing = selectors - collector.ids
    assert not missing, f"Missing dashboard elements: {sorted(missing)}"


def test_judge_status_and_sensor_quality_evidence_are_visible():
    html = PAGE.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")
    collector = IdCollector()
    collector.feed(html)
    required = {
        "judgeChapter", "judgeDemoBtn", "trajectory", "forecastRows",
        "signalInput", "signalQuality", "signalAge", "signalOutput",
        "signalSummary", "risk", "dataBanner",
    }
    assert required.issubset(collector.ids)
    assert "quality==='VALID'" in script or "quality!=='VALID'" in script
    assert "Date.parse" in script, "Chart should use actual timestamps"
    assert "Forecast withheld" in script
