"""Headless render of every Streamlit page against the real site JSON (skipped without it)."""

from pathlib import Path

import pytest

from nfl.config import get_paths

PAGES = Path(__file__).resolve().parents[1] / "src" / "nfl" / "ui" / "pages"
HAS_SITE = (get_paths().site / "meta.json").exists()


@pytest.mark.skipif(not HAS_SITE, reason="needs marts/site (run nfl site)")
@pytest.mark.parametrize("page", sorted(p.stem for p in PAGES.glob("*.py")))
def test_page_renders_without_exceptions(page):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PAGES / f"{page}.py"), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
