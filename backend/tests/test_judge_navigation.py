"""Judge-navigation contract: local artifact links must resolve and promises must be honest.

This checks navigability, not the scientific validity of screenshots or claims.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
PAGES = [
    "README.md",
    "JUDGE_START_HERE.md",
    "submission/JUDGE_EVIDENCE_INDEX.md",
    "submission/PRESENTATION_OVERVIEW.md",
    "himanshusubh1510_MITS_Gwalior/README.md",
    "SUBMISSION_CHECKLIST.md",
]


def _targets(text: str):
    # Basic links/images. URLs with literal parentheses are out of scope.
    for target in re.findall(r"!?\[[^\]]+\]\(([^)]+)\)", text):
        yield target.strip().split("#", 1)[0].split(" ", 1)[0]
    # GitHub-flavored HTML thumbnails also appear in the landing README.
    yield from re.findall(r'<img\s[^>]*src="([^"]+)"', text)


def test_judge_navigation_documents_have_no_missing_relative_targets():
    for name in PAGES:
        source = ROOT / name
        assert source.is_file()
        for target in _targets(source.read_text(encoding="utf-8")):
            if not target or target.startswith(("http:", "https:", "mailto:", "data:", "/", "#")):
                continue
            resolved = (source.parent / target).resolve()
            assert resolved.is_relative_to(ROOT.resolve()), f"Link escapes repo: {name}: {target}"
            assert resolved.exists(), f"Broken judge link: {name} -> {target}"


def test_first_screen_has_run_command_screenshots_and_truthful_boundaries():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    first = readme.split("## The problem", 1)[0]
    for required in (
        "JUDGE_START_HERE.md",
        "Live_Demo_Lunch.png",
        "Live_Demo_SensorGap.png",
        "python -m uvicorn",
        "--app-dir backend",
        "synthetic",
        "Sensor gap",
    ):
        assert required.lower() in first.lower(), f"Missing top-level judge signal: {required}"
    assert "not the performance of the running demo" in readme.lower()
    assert "not yet" in readme.lower()  # Unlisted recording is still missing.


def test_judge_run_commands_match_real_launch_scripts():
    judge = (ROOT / "JUDGE_START_HERE.md").read_text(encoding="utf-8")
    win = (ROOT / "run_local.bat").read_text(encoding="utf-8")
    unix = (ROOT / "run_local.sh").read_text(encoding="utf-8")
    command = "app.main:app --app-dir backend --host 127.0.0.1 --port 8000"
    assert command in judge
    assert command in win
    assert command in unix
    assert "pip install -r backend/requirements.txt" in judge
    assert "Show chapter" in judge


def test_judge_deck_and_evidence_have_explicit_provenance():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert (ROOT / "submission/HimanshuDigitalTwin_Presentation.pdf").stat().st_size > 0
    assert (ROOT / "submission/HimanshuDigitalTwin_Presentation.pptx").stat().st_size > 0
    assert "45" in readme and "10-person" in readme
    assert "not" in readme.lower() and "clinically" in readme.lower()
