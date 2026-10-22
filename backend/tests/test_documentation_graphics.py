"""Keep judge-facing figures present, parseable and locally linked.

These checks do not evaluate whether a chart represents clinical evidence;
research limitations are separately documented.
"""
from pathlib import Path
import re
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
ASSETS = [
    "docs/assets/hero.svg",
    "docs/assets/system-architecture.svg",
    "docs/assets/technology-stack.svg",
    "docs/assets/research-evidence.svg",
]


def test_original_vector_artwork_is_accessible_svg():
    for relative in ASSETS:
        path = ROOT / relative
        assert path.is_file(), f"Missing SVG: {relative}"
        assert path.stat().st_size > 600, f"Artwork is unexpectedly empty: {relative}"
        drawing = ElementTree.parse(path).getroot()
        assert drawing.tag == "{http://www.w3.org/2000/svg}svg"
        assert drawing.attrib.get("viewBox"), f"Missing responsive viewBox: {relative}"
        assert drawing.attrib.get("role") == "img"
        assert drawing.find("{http://www.w3.org/2000/svg}title") is not None
        assert drawing.find("{http://www.w3.org/2000/svg}desc") is not None


def test_readme_embeds_every_asset():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for relative in ASSETS:
        assert f"]({relative})" in readme, f"Not embedded: {relative}"


def test_readme_local_links_exist():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    local = re.findall(r"!?\[[^\]]+\]\(([^)]+)\)", readme)
    for url in local:
        if url.startswith(("https://", "http://", "#", "mailto:")):
            continue
        # Drop optional page anchors; an absent file should fail loudly.
        relative = url.split("#", 1)[0]
        assert not relative.startswith("/"), f"Unexpected absolute link: {url}"
        assert (ROOT / relative).exists(), f"Broken README link: {url}"
