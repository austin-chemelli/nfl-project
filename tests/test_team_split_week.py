"""team_split_week (ADR 0028, M25.0): registry agreement, with/without rows, the opponent tier, leakage."""

import re
from datetime import datetime, timedelta

import polars as pl

from nfl import splits
from nfl.config import Paths
from nfl.sql import runner

from .synth import SCHEMA_PLAYS, play, write_table

SEASON = 2022
TEAMS = [f"T{i:02d}" for i in range(1, 13)]
# (home, away): T01 has the best defense and T12 the best offense (rating = rank / 100 for both)
PAIRS = [
    ("T01", "T12"),
    ("T02", "T11"),
    ("T03", "T10"),
    ("T04", "T09"),
    ("T05", "T08"),
    ("T06", "T07"),
]
EXTRA = {
    "n_blitzers": pl.Float64, "n_pass_rushers": pl.Float64, "n_defense_box": pl.Float64,
    "is_play_action": pl.Boolean, "is_motion": pl.Boolean, "is_screen_pass": pl.Boolean,
    "is_rpo": pl.Boolean, "shotgun": pl.Float64, "no_huddle": pl.Float64,
    "yardline_100": pl.Float64, "air_yards": pl.Float64, "yards_gained": pl.Float64,
}  # fmt: skip
SCHEMA = {**SCHEMA_PLAYS, **EXTRA, "season": pl.Int64}
RICH = {  # one play inside every split's universe
    "n_blitzers": 2.0, "n_pass_rushers": 5.0, "is_play_action": True, "is_motion": True,
    "is_screen_pass": False, "is_rpo": False, "shotgun": 1.0, "no_huddle": 0.0, "down": 3.0,
    "yardline_100": 15.0, "air_yards": 20.0, "yards_gained": 25.0, "epa": 1.0, "wp": 0.5,
}  # fmt: skip


def rating(team: str) -> float:
    return int(team[1:]) / 100


def kickoff(week: int) -> datetime:
    return datetime(2022, 9, 1, 18) + timedelta(days=7 * (week - 1))


def gid(week: int, home: str) -> str:
    return f"{SEASON}_{week:02d}_{home}"


def feature_rows(week, home, away, def_adj=None, off_adj=None, known=None):
    known = known or kickoff(week) - timedelta(days=1)
    out = []
    for side, team in (("home", home), ("away", away)):
        for feat, val in (
            ("strength.epa_def_adj", (def_adj or {}).get(team, rating(team))),
            ("strength.epa_off_adj", (off_adj or {}).get(team, rating(team))),
        ):
            out.append({"week": week, "game_id": gid(week, home), "side": side, "feature": feat,
                        "value": val, "known_as_of": known, "source": "t", "version": "1"})  # fmt: skip
    return out


def build(root, planted=(), extra_features=(), planted_game=None, weeks=6) -> pl.DataFrame:
    """Six weeks of the fixed pairings, one filler play per team-game; `planted_game` = (week, home)
    replaces that game's filler with `planted`."""
    paths = Paths(root)
    plays, games, feats = [], [], []
    for w in range(1, weeks + 1):
        for h, a in PAIRS:
            g = gid(w, h)
            games.append({"game_id": g, "season": SEASON, "week": w, "home_team": h, "away_team": a,
                          "game_type": "REG", "kickoff_utc": kickoff(w)})  # fmt: skip
            feats += feature_rows(w, h, a)
            if planted_game == (w, h):
                continue
            for i, (off, de) in enumerate(((h, a), (a, h))):
                plays.append(play(season=SEASON, week=w, game_id=g, play_id=float(i + 1),
                                  posteam=off, defteam=de, epa=0.1))  # fmt: skip
    plays += list(planted)
    write_table(paths, "plays", plays, SCHEMA)
    write_table(
        paths, "games", games,
        {"game_id": pl.String, "season": pl.Int64, "week": pl.Int32, "home_team": pl.String,
         "away_team": pl.String, "game_type": pl.String, "kickoff_utc": pl.Datetime},
    )  # fmt: skip
    d = paths.marts / "features" / f"season={SEASON}"
    d.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        feats + list(extra_features), schema_overrides={"known_as_of": pl.Datetime}
    ).write_parquet(d / "strength.parquet")
    runner.build(paths, "team_split_week")
    return pl.read_parquet(runner.output_path(paths, "team_split_week"))


def planted_week5():
    """T01 (home) offense against T12, a mix of plays; T12's offense gets one play."""
    g = gid(5, "T01")
    base = {"season": SEASON, "week": 5, "game_id": g, "posteam": "T01", "defteam": "T12"}
    return [
        play(**base, play_id=1.0, epa=1.0, wp=0.5, down=1.0, n_blitzers=2.0, n_pass_rushers=5.0,
             air_yards=20.0, yards_gained=25.0, yardline_100=15.0, shotgun=1.0),
        play(**base, play_id=2.0, epa=-1.0, wp=0.9, down=3.0, n_blitzers=0.0, n_pass_rushers=4.0,
             air_yards=5.0, yards_gained=5.0, yardline_100=60.0, shotgun=0.0),
        play(**base, play_id=3.0, epa=0.5, wp=0.5, down=2.0, rush=1.0, qb_dropback=0.0,
             n_defense_box=6.0, yards_gained=12.0, yardline_100=40.0, **{"pass": 0.0}),
        play(**{**base, "posteam": "T12", "defteam": "T01"}, play_id=4.0, epa=0.2),
    ]  # fmt: skip


def one(df, **kw) -> dict | None:
    q = df
    for k, v in kw.items():
        q = q.filter(pl.col(k) == v)
    assert q.height <= 1, q
    return q.row(0, named=True) if q.height else None


def test_registry_and_sql_agree(tmp_path):
    sql = (runner.MODELS_DIR / "team_split_week.sql").read_text()
    in_sql = set(re.findall(r"'(\w+)' as split", sql))
    assert in_sql == set(splits.ids())
    assert len(splits.ids()) == len(set(splits.ids()))
    # a build with a play in every universe produces every registered split
    rich = play(season=SEASON, week=5, game_id=gid(5, "T01"), posteam="T01", defteam="T12", **RICH)
    run = play(season=SEASON, week=5, game_id=gid(5, "T01"), posteam="T01", defteam="T12",
               play_id=9.0, rush=1.0, n_defense_box=7.0, **{"pass": 0.0})  # fmt: skip
    out = build(tmp_path, [rich, run], planted_game=(5, "T01"))
    assert set(out["split"].unique()) == set(splits.ids())
    for s in splits.SPLITS:
        assert splits.get(s.id) is s
        assert s.chooser in ("offense", "defense", "neither") and s.source in ("pbp", "ftn")


def test_planted_plays_land_in_with_and_without_rows(tmp_path):
    df = build(tmp_path, planted_week5(), planted_game=(5, "T01"))
    k = {"game_id": gid(5, "T01"), "team": "T01", "side": "off"}
    b1 = one(df, **k, split="blitz", flag=True)
    assert (b1["plays"], b1["epa_sum"], b1["explosive"]) == (1, 1.0, 1)
    b0 = one(df, **k, split="blitz", flag=False)
    assert (b0["plays"], b0["epa_sum"], b0["explosive"]) == (1, -1.0, 0)
    # box splits are over runs only: the 6-man box is light, not heavy; the other side has no rows
    bl = one(df, **k, split="box_light", flag=True)
    assert (bl["plays"], bl["explosive"]) == (1, 1)  # a 12-yard run is explosive
    assert one(df, **k, split="box_light", flag=False) is None
    assert one(df, **k, split="box_heavy", flag=False)["plays"] == 1
    assert one(df, **k, split="box_heavy", flag=True) is None
    # deep pass: over passes with air yards (the run is out)
    assert one(df, **k, split="deep_pass", flag=True)["epa_sum"] == 1.0
    d0 = one(df, **k, split="deep_pass", flag=False)
    assert (d0["plays"], d0["epa_sum"]) == (1, -1.0)
    # neutral script (wp .2-.8): plays 1 and 3 in, play 2 (wp .9) out
    n1 = one(df, **k, split="neutral_script", flag=True)
    assert (n1["plays"], n1["epa_sum"]) == (2, 1.5)
    assert one(df, **k, split="neutral_script", flag=False)["epa_sum"] == -1.0
    # red zone: only play 1 (15 yards out)
    assert one(df, **k, split="red_zone", flag=True)["plays"] == 1
    assert one(df, **k, split="red_zone", flag=False)["plays"] == 2
    # down splits
    assert one(df, **k, split="third_down", flag=True)["epa_sum"] == -1.0
    assert one(df, **k, split="early_down", flag=True)["plays"] == 2
    # the defense row is what T12's defense allowed
    dk = {"game_id": gid(5, "T01"), "team": "T12", "side": "def"}
    assert one(df, **dk, split="blitz", flag=True)["epa_sum"] == 1.0
    # null FTN columns on the filler plays: no motion / play action rows (never flag = false)
    assert one(df, **k, split="motion") is None
    assert one(df, **k, split="play_action") is None
    # shotgun: null counts as not in the situation, so flag false exists with the right counts
    assert one(df, **k, split="shotgun", flag=True)["plays"] == 1
    assert one(df, **k, split="shotgun", flag=False)["plays"] == 2


def test_opponent_tier_sign_and_week_floor(tmp_path):
    df = build(tmp_path, planted_week5(), planted_game=(5, "T01"))
    g = gid(5, "T01")
    # T12 is the worst defense (largest EPA allowed): not top ten. T01 is the best: top ten.
    assert one(df, game_id=g, team="T01", side="off", split="vs_top10_def")["flag"] is False
    assert one(df, game_id=g, team="T12", side="off", split="vs_top10_def")["flag"] is True
    # T12 is the best offense: T01's defense faced a top-ten offense; T12's faced the worst
    assert one(df, game_id=g, team="T01", side="def", split="vs_top10_off")["flag"] is True
    # each tier split exists on one side only
    assert one(df, game_id=g, team="T01", side="off", split="vs_top10_off") is None
    assert one(df, game_id=g, team="T01", side="def", split="vs_top10_def") is None
    # in week 5, T01..T10 are the top-ten defenses: offenses facing them carry flag true
    top = df.filter((pl.col("week") == 5) & (pl.col("split") == "vs_top10_def") & pl.col("flag"))
    assert set(top["game_id"]) <= {gid(5, h) for h, _ in PAIRS}
    # T01 and T02 face T12 and T11 (ranks 12 and 11): not top ten
    assert set(top["team"]) == {f"T{i:02d}" for i in range(3, 13)}
    # no tier rows before week 4
    early = df.filter(pl.col("split").str.starts_with("vs_top10") & (pl.col("week") < 4))
    assert early.height == 0
    assert df.filter(pl.col("split").str.starts_with("vs_top10") & (pl.col("week") == 4)).height > 0


def test_leakage_plays_and_features(tmp_path):
    base = build(tmp_path / "a", planted_week5(), planted_game=(5, "T01"))
    # (1) a week-5 play changes week 5 and nothing earlier
    extra = [play(season=SEASON, week=5, game_id=gid(5, "T02"), play_id=77.0, posteam="T02",
                  defteam="T11", epa=9.0, wp=0.5, yardline_100=10.0)]  # fmt: skip
    b = build(tmp_path / "b", planted_week5() + extra, planted_game=(5, "T01"))
    key = ["game_id", "team", "side", "split", "flag"]
    assert not base.sort(key).equals(b.sort(key))
    assert base.filter(pl.col("week") < 5).sort(key).equals(b.filter(pl.col("week") < 5).sort(key))
    # (2) features stamped later never reach week 5: a week-6 row making T12 the best defense, and a
    # week-5 row for T12's own game stamped after kickoff
    flip = {"T12": -5.0}
    later = feature_rows(6, "T01", "T12", def_adj=flip)  # same game ids as the week-6 base rows
    for r in later:
        r["known_as_of"] = kickoff(6)  # not before kickoff: dropped at week 6, never at week 5
    post = feature_rows(5, "T01", "T12", def_adj=flip, known=kickoff(5) + timedelta(days=1))
    c = build(tmp_path / "c", planted_week5(), planted_game=(5, "T01"), extra_features=later + post)
    assert base.sort(key).equals(c.sort(key))
    # a properly stamped week-6 row does move week 6 (and only week 6), so the check has teeth
    live = feature_rows(6, "T01", "T12", def_adj=flip, known=kickoff(6) - timedelta(hours=1))
    d = build(tmp_path / "d", planted_week5(), planted_game=(5, "T01"), extra_features=live)
    assert base.filter(pl.col("week") < 6).sort(key).equals(d.filter(pl.col("week") < 6).sort(key))
    assert (
        not base.filter(pl.col("week") == 6)
        .sort(key)
        .equals(d.filter(pl.col("week") == 6).sort(key))
    )


def test_idempotent_and_catalog(tmp_path):
    from nfl import catalog

    build(tmp_path, planted_week5(), planted_game=(5, "T01"))
    paths = Paths(tmp_path)
    target = runner.output_path(paths, "team_split_week")
    before = target.stat().st_mtime_ns
    (r,) = runner.build(paths, "team_split_week")
    assert r.status == "unchanged" and target.stat().st_mtime_ns == before
    assert "team_split_week" not in catalog.missing(paths)
