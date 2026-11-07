"""Previews are never the record (ADR 0024): only the daily pass writes them and only the game page's
`today` block reads them."""

from datetime import datetime
from pathlib import Path

import polars as pl

from nfl import previews
from nfl.config import Paths

SRC = Path(__file__).resolve().parents[1] / "src" / "nfl"
ALLOWED = {"previews.py", "daily.py", "site.py"}


def test_no_grading_or_publishing_module_reads_previews():
    offenders = []
    for f in SRC.rglob("*.py"):
        if f.name in ALLOWED:
            continue
        text = f.read_text()
        if "previews" in text and (
            "import previews" in text or "previews.parquet" in text or "nfl.previews" in text
        ):
            offenders.append(str(f.relative_to(SRC)))
    assert offenders == []


def test_site_reads_previews_only_for_the_today_block():
    text = (SRC / "site.py").read_text()
    assert text.count("previews.latest(") == 1
    assert "def _today(" in text


def test_append_only_and_latest(tmp_path):
    paths = Paths(tmp_path)
    paths.marts.mkdir(parents=True)
    t0, t1 = datetime(2026, 11, 4), datetime(2026, 11, 6)
    row = lambda t, p: pl.DataFrame({"game_id": ["G"], "model_id": ["student"], "scored_at": [t],
                                     "p_home": [p], "spread_home": [1.0]}).cast(previews.SCHEMA)  # fmt: skip
    previews.append(paths, row(t0, 0.6))
    previews.append(paths, row(t1, 0.4))
    assert pl.read_parquet(paths.marts / previews.FILE).height == 2
    assert previews.latest(paths)["p_home"].to_list() == [0.4]
