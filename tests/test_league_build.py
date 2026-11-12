"""league.json: contract, determinism, snapshots, and that a failure can't stop the site (M14.10)."""

import json
from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest

from nfl import site
from nfl.league import build as lb
from nfl.league.divisions import DIVISIONS
from nfl.league.inputs import VariantInputs

CODES = sorted(DIVISIONS)
NOW = datetime(2026, 11, 3, 12)
KICK = datetime(2026, 9, 10)
RUNS = 200


def _pairs(codes, shift):
    rot = codes[shift % 32 :] + codes[: shift % 32]
    return [(rot[i], rot[31 - i]) for i in range(16)]


def _games(played=6, weeks=10):
    rows = []
    for w in range(1, weeks + 1):
        for h, a in _pairs(CODES, w * 3):
            done = w <= played
            hs = (17 + (CODES.index(h) + w) % 14) if done else None
            rows.append({
                "game_id": f"2026_{w:02d}_{a}_{h}", "season": 2026, "week": w, "game_type": "REG",
                "kickoff_utc": KICK + timedelta(days=7 * (w - 1)), "home_team": h, "away_team": a,
                "home_score": hs, "away_score": 20 if done else None,
                "result": (hs - 20) if done else None,
            })  # fmt: skip
    return pl.DataFrame(rows, schema_overrides={"kickoff_utc": pl.Datetime("us")})


def _inputs(games, shift=0.0):
    _, rem = lb.regular_season(games)
    ids, home, away = (
        rem["game_id"].to_list(),
        rem["home_team"].to_list(),
        rem["away_team"].to_list(),
    )
    ratings = {t: (i - 15.5) / 20 for i, t in enumerate(CODES)}
    p = 1 / (1 + np.exp(-np.array([ratings[h] - ratings[a] + 0.2 + shift for h, a in zip(home, away, strict=True)])))  # fmt: skip

    def variant(name, source, version):
        return VariantInputs(name, ids, home, away, p, [source] * len(ids), {source: len(ids)},
                             ratings, 0.2, 0.9, None, version)  # fmt: skip

    return {"student": variant("student", "scored", "abc"), "market": variant("market", "line", "")}


def _file(games=None, **kw):
    games = _games() if games is None else games
    return lb.league_file(games, _inputs(games), 2026, NOW, n_runs=RUNS, **kw)


def test_file_matches_the_contract_and_is_valid_json():
    obj, _ = _file()
    lb.LeagueFile.model_validate(obj)
    json.dumps(obj, allow_nan=False)
    assert obj["through_week"] == 6 and obj["n_sims"] == RUNS
    assert len(obj["teams"]) == 32 and len(obj["games"]) == 64
    for v in lb.VARIANTS:
        assert set(obj["odds"][v]["teams"]) == set(CODES)
        assert sum(o["playoffs"] for o in obj["odds"][v]["teams"].values()) == pytest.approx(14, abs=0.01)  # fmt: skip
    assert obj["odds"]["student"]["sources"] == {"scored": 64}
    assert obj["odds"]["market"]["sources"] == {"line": 64}


def test_standings_rows_are_consistent():
    obj, _ = _file()
    rows = {r["team"]: r for r in obj["teams"]}
    assert sum(r["w"] for r in rows.values()) + sum(r["t"] for r in rows.values()) / 2 == 96
    assert all(r["w"] + r["l"] + r["t"] == 6 and r["left"] == 4 for r in rows.values())
    for conf in ("AFC", "NFC"):
        seeds = sorted(r["seed_today"] for r in rows.values() if r["conf"] == conf and r["seed_today"])  # fmt: skip
        assert seeds == [1, 2, 3, 4, 5, 6, 7]
    for r in rows.values():
        if r["seed_today"] and r["seed_today"] <= 4:
            assert r["div_rank"] == 1


def test_played_and_ratings_rebuild_the_standings_in_the_browser():
    """M26.2: the played games in the file give the file's own standings; ratings price playoff games."""
    from nfl.league.standings import GameResult, Results

    obj, _ = _file()
    assert len(obj["played"]) == 96 and obj["played"][0]["week"] == 1
    r = Results(GameResult.from_scores(g["home"], g["away"], g["home_score"], g["away_score"]) for g in obj["played"])  # fmt: skip
    for row in obj["teams"]:
        assert r.record(row["team"]) == (row["w"], row["l"], row["t"])
        assert r.points(row["team"]) == (row["pf"], row["pa"])
    for v in lb.VARIANTS:
        assert set(obj["odds"][v]["ratings"]) == set(CODES)
        assert obj["odds"][v]["home_term"] == pytest.approx(0.2)


def test_same_inputs_same_numbers_and_new_inputs_a_new_seed():
    a, b = _file()[0], _file()[0]
    assert a["seed"] == b["seed"] and a["odds"] == b["odds"] and a["games"] == b["games"]
    later = lb.league_file(_games(), _inputs(_games()), 2026, NOW + timedelta(days=2), n_runs=RUNS)[0]  # fmt: skip
    assert later["odds"] == a["odds"]  # the clock alone changes nothing
    moved = lb.league_file(_games(), _inputs(_games(), 0.1), 2026, NOW, n_runs=RUNS)[0]
    assert moved["seed"] != a["seed"]
    assert _file(_games(played=7))[0]["seed"] != a["seed"]


def test_games_are_ranked_and_carry_both_probabilities():
    obj, _ = _file()
    lev = [g["leverage_total"] for g in obj["games"]]
    assert lev == sorted(lev, reverse=True)
    g = obj["games"][0]
    assert g["kickoff"].endswith("Z") and g["home"] in CODES and g["market_source"] == "line"
    assert g["n_home_wins"] + g["n_away_wins"] == RUNS


def test_after_the_last_game_the_file_keeps_the_final_standings():
    games = _games(played=10)
    obj, sims = lb.league_file(games, None, 2026, NOW, n_runs=RUNS)
    lb.LeagueFile.model_validate(obj)
    assert sims == {} and obj["games"] == [] and obj["n_sims"] == 0
    assert obj["through_week"] == 10 and obj["odds"]["student"]["teams"] == {}
    assert all(r["left"] == 0 and r["w"] + r["l"] + r["t"] == 10 for r in obj["teams"])


def test_through_week_is_the_last_full_week():
    games = _games(played=6)
    thursday = pl.col("game_id") == games.filter(pl.col("week") == 7)["game_id"][0]
    games = games.with_columns(
        pl.when(thursday).then(24).otherwise(pl.col("home_score")).alias("home_score"),
        pl.when(thursday).then(20).otherwise(pl.col("away_score")).alias("away_score"),
    )
    obj, sims = lb.league_file(games, _inputs(games), 2026, NOW, n_runs=RUNS)
    assert obj["through_week"] == 6
    rows = lb.snapshot_rows(obj, sims, _inputs(games), "lock", NOW)
    assert rows["week"].unique().to_list() == [7]  # a Saturday lock in Week 7 is Week 7


def _snap(obj, sims, games, kind="refresh", as_of=NOW):
    return lb.snapshot_rows(obj, sims, _inputs(games), kind, as_of)


def test_snapshots_append_and_never_rewrite(tmp_path):
    games = _games()
    obj, sims = _file(games)
    path = tmp_path / "league" / "season=2026" / "snapshots.parquet"
    assert lb.append_snapshot(path, _snap(obj, sims, games))
    first = pl.read_parquet(path)
    assert first.height == 64 and set(first["variant"]) == {"student", "market"}
    assert first.filter(pl.col("variant") == "student")["model_version"].unique().to_list() == ["abc"]  # fmt: skip
    assert not lb.append_snapshot(path, _snap(obj, sims, games))  # the same build twice
    assert pl.read_parquet(path).equals(first)
    assert lb.append_snapshot(path, _snap(obj, sims, games, as_of=NOW + timedelta(days=7)))
    both = pl.read_parquet(path)
    assert both.height == 128 and both.head(64).equals(first)


def test_history_is_the_tuesday_series(tmp_path):
    games = _games()
    obj, sims = _file(games)
    path = tmp_path / "snapshots.parquet"
    assert lb.history(path) == {}
    lb.append_snapshot(path, _snap(obj, sims, games))
    lb.append_snapshot(path, _snap(obj, sims, games, kind="lock", as_of=NOW + timedelta(days=2)))
    h = lb.history(path)
    assert len(h) == 32 and len(h["KC"]) == 1  # the lock row isn't in the series
    p = obj["odds"]["student"]["teams"]["KC"]["playoffs"]
    assert h["KC"][0] == {"week": 7, "student": p, "market": obj["odds"]["market"]["teams"]["KC"]["playoffs"]}  # fmt: skip


def _paths(tmp_path, monkeypatch):
    from nfl.config import Paths

    games = _games()
    monkeypatch.setattr(lb.store, "games_frame", lambda p: games)
    monkeypatch.setattr(lb, "load_inputs", lambda p, s, a: _inputs(games))
    return Paths(tmp_path)


def test_build_writes_the_file_and_snapshots_only_when_asked(tmp_path, monkeypatch):
    paths = _paths(tmp_path, monkeypatch)
    out = lb.build(paths, 2026, now=NOW, n_runs=RUNS)
    assert (paths.site / "league.json").exists() and out["games"] == 64
    assert not lb.snapshot_path(paths, 2026).exists()
    lb.build(paths, 2026, snapshot="refresh", now=NOW, n_runs=RUNS)
    assert lb.snapshot_path(paths, 2026).exists()
    assert json.loads((paths.site / "league.json").read_text())["history"]["KC"]
    with pytest.raises(ValueError):
        lb.build(paths, 2026, snapshot="sunday", now=NOW, n_runs=RUNS)


def test_callers_ask_for_the_right_snapshot():
    import inspect

    from nfl import lock, weekly

    assert 'league_snapshot="refresh"' in inspect.getsource(weekly.refresh)
    assert 'league_snapshot="lock"' in inspect.getsource(lock.run)
    assert inspect.signature(site.build).parameters["league_snapshot"].default is None


def test_a_league_failure_leaves_the_site_build_green(monkeypatch, capsys):
    for err in (RuntimeError("boom"), pl.exceptions.PanicException("panic")):

        def fail(*a, _e=err, **k):
            raise _e

        monkeypatch.setattr(lb, "build", fail)
        site.write_league(None, 2026, "lock")
        assert "league.json failed, continuing" in capsys.readouterr().out


def test_the_site_build_writes_league_last():
    import inspect

    src = inspect.getsource(site.build)
    assert src.index("write_league(") > src.index("write_retro(paths, season)")


def test_a_snapshot_failure_keeps_the_fresh_file(tmp_path, monkeypatch, capsys):
    paths = _paths(tmp_path, monkeypatch)

    def fail(*a):
        raise OSError("mount gone")

    monkeypatch.setattr(lb, "append_snapshot", fail)
    lb.build(paths, 2026, snapshot="refresh", now=NOW, n_runs=RUNS)
    assert json.loads((paths.site / "league.json").read_text())["history"]["KC"]
    assert "SNAPSHOT NOT SAVED" in capsys.readouterr().out


def test_an_invalid_file_writes_no_snapshot(tmp_path, monkeypatch):
    paths = _paths(tmp_path, monkeypatch)

    def bad(obj):
        raise ValueError("bad file")

    monkeypatch.setattr(lb.LeagueFile, "model_validate", bad)
    with pytest.raises(ValueError):
        lb.build(paths, 2026, snapshot="refresh", now=NOW, n_runs=RUNS)
    assert not lb.snapshot_path(paths, 2026).exists()


def _min_similar(season=2026):
    return {
        "schema_version": "1", "season": season, "as_of": "2026-11-03T12:00:00Z",
        "measures": [{"id": "record", "label": "Record"}],
        "teams": {"KC": {
            "games_played": 6, "record": "4-2", "k_summary": 25, "made_playoffs": 9,
            "rounds": {"div": 4, "conf": 2, "sb": 1, "champ": 0},
            "pool": {"seasons": [2002, 2025], "n": 768}, "peers": {"made": 60, "n": 100},
            "profile": [50], "nearest": [], "flags": [],
        }},
    }  # fmt: skip


def test_league_json_has_no_similar_and_similar_json_is_written(tmp_path, monkeypatch):
    paths = _paths(tmp_path, monkeypatch)
    monkeypatch.setattr(lb.similar, "similar_file", lambda *a: _min_similar())
    out = lb.build(paths, 2026, now=NOW, n_runs=RUNS)
    assert "similar" not in json.loads((paths.site / "league.json").read_text())
    text = (paths.site / "similar.json").read_text()
    lb.SimilarFile.model_validate_json(text)
    assert " " not in text and out["similar_bytes"] == len(text)  # compact
    assert not list(paths.site.glob("*.tmp"))


def test_a_similar_failure_leaves_league_json_and_the_old_similar_json(
    tmp_path, monkeypatch, capsys
):
    paths = _paths(tmp_path, monkeypatch)
    monkeypatch.setattr(lb.similar, "similar_file", lambda *a: _min_similar())
    lb.build(paths, 2026, now=NOW, n_runs=RUNS)
    old = (paths.site / "similar.json").read_text()
    (paths.site / "league.json").unlink()

    # a real raise from inside the module, not a stubbed writer: the feature read fails
    for err in (RuntimeError("mount gone"), pl.exceptions.PanicException("panic")):

        def boom(*a, _e=err, **k):
            raise _e

        monkeypatch.setattr(lb.similar, "load_features", boom)
        lb.build(paths, 2026, now=NOW + timedelta(hours=1), n_runs=RUNS)
        assert "league: SIMILAR NOT UPDATED" in capsys.readouterr().out
        assert (paths.site / "league.json").exists()
        assert (paths.site / "similar.json").read_text() == old
        (paths.site / "league.json").unlink()


def test_an_invalid_similar_file_is_not_written(tmp_path, monkeypatch, capsys):
    paths = _paths(tmp_path, monkeypatch)
    bad = _min_similar() | {"teams": {"KC": {"games_played": 8}}}
    monkeypatch.setattr(lb.similar, "similar_file", lambda *a: bad)
    lb.build(paths, 2026, now=NOW, n_runs=RUNS)
    assert "SIMILAR NOT UPDATED" in capsys.readouterr().out
    assert not (paths.site / "similar.json").exists()
    assert (paths.site / "league.json").exists()


def test_publish_picks_up_similar_json(tmp_path):
    from nfl import publish
    from nfl.config import Paths

    paths = Paths(tmp_path)
    paths.site.mkdir(parents=True)
    (paths.site / "similar.json").write_text("{}")
    assert "site/similar.json" in publish.plan(paths, repo=tmp_path)


def test_history_over_three_tuesdays_with_a_lock_and_a_rerun(tmp_path):
    """One point a week from the Tuesday series: a lock row never enters it, and a second refresh in
    the same week replaces the first. Weeks come in order."""
    path = tmp_path / "snapshots.parquet"
    tue = [NOW, NOW + timedelta(days=7), NOW + timedelta(days=14)]
    want = {}
    for i, played in enumerate((4, 5, 6)):
        games = _games(played=played)
        obj, sims = lb.league_file(games, _inputs(games), 2026, tue[i], n_runs=RUNS)
        lb.append_snapshot(path, lb.snapshot_rows(obj, sims, _inputs(games), "refresh", tue[i]))
        if i == 1:  # a lock on Thursday, then a later refresh in the same week on other inputs
            lb.append_snapshot(
                path,
                lb.snapshot_rows(obj, sims, _inputs(games), "lock", tue[i] + timedelta(days=2)),
            )
            games2 = _games(played=played)
            obj, sims = lb.league_file(games2, _inputs(games2, 0.5), 2026, tue[i], n_runs=RUNS)
            later = tue[i] + timedelta(hours=5)
            lb.append_snapshot(
                path, lb.snapshot_rows(obj, sims, _inputs(games2, 0.5), "refresh", later)
            )
        want[i] = obj["odds"]["student"]["teams"]["KC"]["playoffs"]
    series = lb.history(path)["KC"]
    assert [p["week"] for p in series] == [5, 6, 7]
    assert series[1]["student"] == want[1]  # the later refresh of week 6
    assert series[0]["student"] != series[1]["student"] != series[2]["student"]
    assert len(lb.history(path)) == 32


def test_an_empty_similar_file_never_replaces_a_good_one_in_season(tmp_path, monkeypatch, capsys):
    """An empty feature store returns no teams rather than failing."""
    paths = _paths(tmp_path, monkeypatch)
    monkeypatch.setattr(lb.similar, "similar_file", lambda *a: _min_similar())
    lb.build(paths, 2026, now=NOW, n_runs=RUNS)
    old = (paths.site / "similar.json").read_text()
    monkeypatch.setattr(lb.similar, "similar_file", lambda *a: {**_min_similar(), "teams": {}})
    lb.build(paths, 2026, now=NOW, n_runs=RUNS)
    assert (paths.site / "similar.json").read_text() == old
    assert "SIMILAR NOT UPDATED" in capsys.readouterr().out
