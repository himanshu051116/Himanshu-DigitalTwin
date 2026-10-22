"""Offline regression tests for the submission inventory and video-link gate."""
from pathlib import Path

from scripts.submission_readiness import REQUIRED_FILES, _youtube_video_url, evaluate


def _fixture(tmp_path: Path, with_video: bool = True):
    for relative in REQUIRED_FILES.values():
        file = tmp_path / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"test file")
    url = "https://youtu.be/abcdefghijk" if with_video else ""
    (tmp_path / "README.md").write_text("Synthetic demo: " + url, encoding="utf-8")
    metadata = {
        "team_name": "sample_team",
        "college_name": "sample_college",
        "team_leader_name": "Sample Leader",
        "team_members": ["Sample Leader"],
        "registration_confirmed": True,
        "public_github_repo_url": "https://github.com/example/repo",
        "public_repository_confirmed": True,
        "demo_video_url": url,
        "demo_video_duration_minutes": 21 if with_video else 0,
        "video_link_access_confirmed": bool(with_video),
        "submission_platform_entry_confirmed": True,
    }
    return metadata


def _check(result, name):
    return next(item for item in result["checks"] if item["check"] == name)["passed"]


def test_inventory_uses_committed_presentation_filenames():
    assert REQUIRED_FILES["presentation_pdf"] == "submission/HimanshuDigitalTwin_Presentation.pdf"
    assert REQUIRED_FILES["presentation_editable"] == "submission/HimanshuDigitalTwin_Presentation.pptx"


def test_missing_video_blocks_readiness_even_when_other_fields_attested(tmp_path):
    metadata = _fixture(tmp_path, with_video=False)
    result = evaluate(tmp_path, metadata)
    assert result["gate"] == "NOT_READY"
    assert not _check(result, "video_url_format")
    assert not _check(result, "video_url_in_readme")
    assert not _check(result, "video_length")


def test_local_inventory_passes_only_for_linked_minimum_20_min_video(tmp_path):
    metadata = _fixture(tmp_path)
    assert evaluate(tmp_path, metadata)["gate"] == "READY"
    metadata["demo_video_duration_minutes"] = 19.99
    assert evaluate(tmp_path, metadata)["gate"] == "NOT_READY"
    metadata["demo_video_duration_minutes"] = 20
    (tmp_path / "README.md").write_text("No video here", encoding="utf-8")
    assert not _check(evaluate(tmp_path, metadata), "video_url_in_readme")


def test_local_check_rejects_missing_presentation(tmp_path):
    metadata = _fixture(tmp_path)
    (tmp_path / REQUIRED_FILES["presentation_pdf"]).unlink()
    result = evaluate(tmp_path, metadata)
    assert not _check(result, "presentation_pdf")
    assert result["gate"] == "NOT_READY"


def test_youtube_url_validation_rejects_placeholders():
    assert _youtube_video_url("https://www.youtube.com/watch?v=abcdefghijk")
    assert _youtube_video_url("https://youtu.be/abcdefghijk")
    assert not _youtube_video_url("https://youtu.be/VIDEO_ID")
    assert not _youtube_video_url("https://example.com/watch?v=abcdefghijk")
    assert not _youtube_video_url("http://youtu.be/abcdefghijk")
