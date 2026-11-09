"""Player sources (ADR 0027, M24.0) and status-to-play rates (M24.1)."""

import httpx
import polars as pl
import pytest

from nfl import catalog, curate, ingest
from nfl.config import DATASETS, DEFAULT_SEASONS, OPTIONAL_DATASETS, SINGLE_FILE_DATASETS, Paths
from nfl.players import status

from .conftest import requires_data

RAW_TS = "snapshot_ts=20261108T000000Z"


def _raw(root, dataset, name, df):
    d = root / "raw" / "nflverse" / dataset / RAW_TS
    d.mkdir(parents=True, exist_ok=True)
    df.write_parquet(d / name)


def _part(root, table, season, df):
    d = root / "curated" / table / f"season={season}"
    d.mkdir(parents=True, exist_ok=True)
    df.drop("season", strict=False).write_parquet(d / "part0.parquet")


# ------------------------------------------------------------------------------------- registry


def test_player_sources_are_registered_optional_and_ingested_by_default():
    for ds in ("player_stats", "snap_counts", "pfr_pass", "pfr_rush", "pfr_rec", "pfr_def",
               "players", "contracts", "draft_picks"):  # fmt: skip
        assert ds in DATASETS and ds in OPTIONAL_DATASETS
    for ds in ("players", "contracts", "draft_picks"):
        assert DATASETS[ds][2] is None and ds in SINGLE_FILE_DATASETS
    assert DATASETS["snap_counts"][2] == DEFAULT_SEASONS["snap_counts"][0] == 2013
    # the lock's sources stay required
    assert not {"schedules", "pbp", "injuries", "depth_charts"} & OPTIONAL_DATASETS


def test_an_optional_download_failure_is_a_status_not_an_error(tmp_path, monkeypatch):
    def boom(client, paths, ds, season, ts, force=False):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(ingest, "fetch_one", boom)
    out = ingest.ingest(Paths(tmp_path), datasets=["players", "snap_counts"],
                        seasons={"snap_counts": (2025, 2025)})  # fmt: skip
    assert {s for _, _, s in out} == {"failed-ConnectError"}
    with pytest.raises(httpx.ConnectError):
        ingest.ingest(Paths(tmp_path), datasets=["schedules"])


# -------------------------------------------------------------------------------------- curate


def test_player_tables_curate_by_season_and_as_single_files(tmp_path):
    root = tmp_path
    _raw(root, "snap_counts", "snap_counts_2025.parquet", pl.DataFrame({
        "game_id": ["g1"], "season": [2025], "week": [1], "game_type": ["REG"], "team": ["AAA"],
        "pfr_player_id": ["Pf01"], "position": ["WR"], "offense_snaps": [50.0], "offense_pct": [0.8],
        "defense_snaps": [0.0], "defense_pct": [0.0], "st_snaps": [0.0], "st_pct": [0.0],
    }))  # fmt: skip
    _raw(
        root,
        "players",
        "players.parquet",
        pl.DataFrame({"gsis_id": ["00-1"], "pfr_id": ["Pf01"], "display_name": ["A Player"]}),
    )
    _raw(root, "contracts", "historical_contracts.parquet", pl.DataFrame({
        "player": ["A Player"], "gsis_id": ["00-1"], "apy": [1.5],
        "season_history": [[{"season": 2025}]], "contract_history": [[{"x": 1}]],
    }))  # fmt: skip
    out = curate.curate_players(Paths(root))
    assert ("snap_counts", 2025, 1) in out and ("players", 0, 1) in out
    con = catalog.connect(Paths(root), only=["snap_counts", "players", "contracts"])
    row = con.sql(
        "select p.gsis_id from snap_counts s join players p on p.pfr_id = s.pfr_player_id"
    ).fetchall()
    assert row == [("00-1",)]
    cols = [r[0] for r in con.sql("describe contracts").fetchall()]
    assert "apy" in cols and "season_history" not in cols


def test_a_failing_player_curate_never_stops_curate(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bad file")

    monkeypatch.setattr(curate, "curate_players", boom)
    assert curate.curate(Paths(tmp_path), tables=("player_weeks",)) == []


def test_the_plays_table_keeps_who_did_what():
    for c in ("receiver_player_id", "rusher_player_id", "sack_player_id", "pass_defense_1_player_id",
              "interception_player_id", "complete_pass"):  # fmt: skip
        assert c in curate.PBP_COLUMNS


# ---------------------------------------------------------------------------- status to play


def _status_root(tmp_path):
    """Team AAA, weeks 1 and 2. Week 1 sets roles; week 2's final report lists four players."""
    root = tmp_path
    inj = pl.DataFrame({
        "season": [2025] * 4, "week": [2] * 4, "team": ["AAA"] * 4, "game_type": ["REG"] * 4,
        "gsis_id": ["s1", "s2", "bk", "s4"], "position": ["WR", "WR", "QB", "CB"],
        "report_status": ["Questionable", "Questionable", "Questionable", "Out"],
    })  # fmt: skip
    _part(root, "injuries", 2025, inj)
    snaps = pl.DataFrame({
        "season": [2025] * 6, "week": [1, 1, 1, 1, 2, 2], "team": ["AAA"] * 6, "game_type": ["REG"] * 6,
        "pfr_player_id": ["P1", "P2", "PB", "P4", "P1", "PB"], "position": ["WR", "WR", "QB", "CB", "WR", "QB"],
        # the backup QB is on the sheet with no snaps in week 1: no role
        "offense_snaps": [60.0, 40.0, 0.0, 0.0, 55.0, 0.0], "offense_pct": [0.9, 0.6, 0.0, 0.0, 0.85, 0.0],
        "defense_snaps": [0.0, 0.0, 0.0, 50.0, 0.0, 0.0], "defense_pct": [0.0, 0.0, 0.0, 0.8, 0.0, 0.0],
        "st_snaps": [0.0] * 6, "st_pct": [0.0] * 6,
    })  # fmt: skip
    _part(root, "snap_counts", 2025, snaps)
    pdir = root / "curated" / "players"
    pdir.mkdir(parents=True)
    pl.DataFrame(
        {"gsis_id": ["s1", "s2", "bk", "s4"], "pfr_id": ["P1", "P2", "PB", "P4"]}
    ).write_parquet(pdir / "players.parquet")
    return Paths(root)


def test_status_rates_count_only_players_with_a_role(tmp_path):
    df = status.listed(_status_root(tmp_path), (2025, 2025))
    assert sorted(df["gsis_id"].to_list()) == ["s1", "s2", "s4"]  # the backup QB had no role
    played = dict(zip(df["gsis_id"].to_list(), df["played"].to_list(), strict=True))
    assert played == {"s1": True, "s2": False, "s4": False}
    r = status.rates(df)
    q = r.filter((pl.col("status") == "Questionable") & (pl.col("pos_group") == "WR")).row(
        0, named=True
    )
    assert (q["n"], q["played"], q["rate"]) == (2, 1, 0.5)
    assert 0.0 <= q["lo"] < 0.5 < q["hi"] <= 1.0
    assert set(r["pos_group"]) >= {"WR", "DB", "all"}


def test_a_team_week_without_snap_counts_is_left_out(tmp_path):
    paths = _status_root(tmp_path)
    extra = pl.DataFrame({
        "season": [2025], "week": [3], "team": ["AAA"], "game_type": ["REG"], "gsis_id": ["s1"],
        "position": ["WR"], "report_status": ["Questionable"],
    })  # fmt: skip
    d = paths.curated_table("injuries") / "season=2025"
    extra.drop("season").write_parquet(d / "part1.parquet")
    assert 3 not in status.listed(paths, (2025, 2025))["week"].to_list()


def test_wilson_stays_inside_zero_and_one():
    assert status.wilson(0, 10)[0] == 0.0
    assert status.wilson(10, 10)[1] == 1.0
    lo, hi = status.wilson(50, 100)
    assert lo < 0.5 < hi


@requires_data
def test_real_rates_are_sane():
    df = status.rates(status.listed(_real_paths()))
    cur = df.filter(pl.col("era") == "2016+")
    get = lambda s: cur.filter((pl.col("status") == s) & (pl.col("pos_group") == "all"))[
        "rate"
    ].item()
    assert get("Out") < 0.01 and get("Doubtful") < 0.05
    assert 0.55 < get("Questionable") < 0.85
    assert get("None") > 0.9


def _real_paths():
    from nfl.config import get_paths

    return get_paths()
