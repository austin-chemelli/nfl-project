"""ADR 0032, research side: schema v3, the checks on the new fields, the `news.*` features (point in
time), the repeat table and the late-status pass."""

import json
import subprocess
from datetime import UTC, date, datetime, time
from pathlib import Path

import polars as pl
import pytest

from nfl.config import Paths
from nfl.features import news, store
from nfl.llm import checks, repeat
from nfl.llm import claude_research as cr
from nfl.llm import narrative as nar
from nfl.llm.client import read_calls
from nfl.llm.fetch import Page
from tests.test_claude_research import NOW, URL_A, _ctx, _games, _Pages, _record, _row, _transcript

BUILD = datetime(2030, 1, 1)
KNOWN = datetime(2026, 10, 28, 20, 0)  # the example record's stamp
GAMES = pl.DataFrame(
    {
        "game_id": ["2026_07_BAL_CIN", "2026_08_BAL_BUF"],
        "season": [2026, 2026],
        "week": [7, 8],
        "kickoff_utc": [datetime(2026, 10, 25, 17, 0), datetime(2026, 11, 1, 18, 0)],
        "home_team": ["CIN", "BUF"],
        "away_team": ["BAL", "BAL"],
    }
)
NAMES = {"G_LAMAR": {"Lamar Jackson"}, "G_JB": {"Jacoby Brissett"}, "G_JA": {"Josh Allen"}}


def rec(**over):
    d = nar.example()
    d.update({k: v for k, v in over.items() if k not in ("home", "away")})
    for side in ("home", "away"):
        d[side].update(over.get(side, {}))
    return nar.GameNarrative.model_validate(d)


# ------------------------------------------------------------------------------------ schema


def test_schema_v1_v2_v3_all_parse_and_v3_fields_default():
    d = nar.example()
    assert nar.SCHEMA_VERSION == "3" and nar.PROMPT_VERSION == "narrative_v4"
    for v in ("1", "2", "3"):
        d["schema_version"] = v
        for side in ("home", "away"):  # a v1/v2 record has none of the v3 fields
            for f in ("qb_named_starter", "starters_ruled_out", "coach_fired_this_week"):
                d[side].pop(f, None)
        r = nar.GameNarrative.model_validate(d)
        assert r.home.qb_named_starter is None and r.home.starters_ruled_out == []
        assert r.away.coach_fired_this_week is False and r.pass_kind == "full"
    with pytest.raises(ValueError):
        nar.GameNarrative.model_validate({**d, "schema_version": "4"})
    assert rec().home.qb_named_starter == "Josh Allen"


def test_passes_are_unchanged_and_status_passes_are_separate():
    assert nar.PASSES == ((2, time(18, 0)), (5, time(7, 0)))
    assert nar.STATUS_PASSES == ((3, time(7, 30)), (5, time(10, 30)))
    # Thursday 2026-11-05 12:00 UTC = 07:00 EST: before the 07:30 status pass; Saturday's was last
    assert nar.last_pass(datetime(2026, 11, 5, 12, 0), nar.STATUS_PASSES) == datetime(2026, 10, 31, 14, 30)  # fmt: skip
    assert nar.last_pass(datetime(2026, 11, 5, 12, 30), nar.STATUS_PASSES) == datetime(2026, 11, 5, 12, 30)  # fmt: skip
    assert nar.last_pass(datetime(2026, 11, 5, 12, 30)) == datetime(2026, 11, 4, 23, 0)


def test_status_records_never_stand_in_for_a_full_pass(monkeypatch):
    status = rec(producer="claude_max", pass_kind="status", known_as_of="2026-10-30T12:00:00Z")
    full = rec(producer="claude_max", known_as_of="2026-10-29T12:00:00Z")
    monkeypatch.setattr(nar, "load_records", lambda paths, seasons=None: [status, full])
    since = datetime(2026, 10, 29, 23, 0)
    assert nar.stored_since(None, 2026, 8, since) == set()
    assert nar.stored_since(None, 2026, 8, since, "status") == {"2026_08_BAL_BUF"}


# ------------------------------------------------------------------------------------ checks


def test_names_are_matched_across_initials_and_suffixes():
    assert checks.same_person("J. Brissett", "Jacoby Brissett Jr.")
    assert checks.same_person("Brissett", "Jacoby Brissett")
    assert not checks.same_person("Josh Allen", "Jacoby Brissett")
    assert not checks.same_person("Kyle Allen", "Josh Allen")


def test_checks_drop_off_roster_starters_and_a_named_qb_without_a_claim(tmp_path):
    paths = _games(tmp_path)
    r = _record()
    r["away"]["qb_named_starter"] = "Jacoby Brissett"  # on BAL's roster; the claim names him
    r["away"]["starters_ruled_out"] = ["Lamar Jackson", "Josh Allen"]  # Allen is Buffalo's
    r["home"]["qb_named_starter"] = "Daron Payne"  # NYG's DT, and no claim: dropped
    r["home"]["starters_ruled_out"] = ["Example Receiver", "Daron Payne"]  # Payne is not BUF's
    out, drops, _ = checks.apply(r, _ctx(paths))
    assert out["away"]["qb_named_starter"] == "Jacoby Brissett"
    assert out["away"]["starters_ruled_out"] == ["Lamar Jackson"]
    assert out["home"]["qb_named_starter"] is None
    assert out["home"]["starters_ruled_out"] == ["Example Receiver"]
    assert drops["ruled_out: team"] == 2 and drops["qb_named: team"] == 1
    # a roster-valid name still needs a claim that cites him
    r2 = _record()
    r2["home"]["qb_named_starter"] = "Josh Allen"  # on BUF's roster; the only claim is Brissett's
    out2, drops2, _ = checks.apply(r2, _ctx(paths))
    assert out2["home"]["qb_named_starter"] is None and drops2["qb_named: no claim"] == 1


# ------------------------------------------------------------------------------------ features


def _depth(rows):
    """Timestamped depth charts: (team, dt, gsis_id) for QB1."""
    return pl.DataFrame(
        [{"team": t, "dt": dt, "pos_rank": 1, "pos_abb": "QB", "pos_slot": 1, "gsis_id": g,
          "season": 2026} for t, dt, g in rows]
    )  # fmt: skip


PLAYS = pl.DataFrame({"game_id": ["2026_07_BAL_CIN"] * 3, "posteam": ["BAL"] * 3,
                      "passer_player_id": ["G_LAMAR"] * 3})  # fmt: skip
CHART_LAMAR = ("BAL", "2026-10-27T12:00:00Z", "G_LAMAR")
CHART_JB_LATE = ("BAL", "2026-10-29T12:00:00Z", "G_JB")  # after the record's stamp


def _feat(records, depth, inj=None, plays=PLAYS):
    rows = news._rows(records, GAMES, plays, depth, inj, NAMES, BUILD)
    return {(r["side"], r["feature"]): r["value"] for r in rows.iter_rows(named=True)}, rows


def test_qb_change_confirmed_needs_a_name_that_is_neither_last_games_passer_nor_the_chart():
    named = rec(away={"qb_named_starter": "Jacoby Brissett"})
    f, rows = _feat([named], _depth([CHART_LAMAR]))
    assert f[("away", "news.qb_change_confirmed")] == 1.0
    assert f[("home", "news.qb_change_confirmed")] == 0.0  # Allen named, no reference known: 0
    assert set(rows["known_as_of"]) == {KNOWN} and set(rows["source"]) == {"llm_news"}
    same = rec(away={"qb_named_starter": "L. Jackson"})  # initials: still him
    assert _feat([same], _depth([CHART_LAMAR]))[0][("away", "news.qb_change_confirmed")] == 0.0
    none = rec(away={"qb_named_starter": None})
    assert _feat([none], _depth([CHART_LAMAR]))[0][("away", "news.qb_change_confirmed")] == 0.0


def test_qb_change_uses_the_chart_as_of_the_record_not_a_later_one():
    named = rec(away={"qb_named_starter": "Jacoby Brissett"})
    # the chart flips to Brissett a day AFTER the record: when stamped, it was a change
    f, _ = _feat([named], _depth([CHART_LAMAR, CHART_JB_LATE]))
    assert f[("away", "news.qb_change_confirmed")] == 1.0
    # flipped BEFORE the record: the chart already names him, so reporting adds nothing: 0
    early = ("BAL", "2026-10-28T08:00:00Z", "G_JB")
    f2, _ = _feat([named], _depth([CHART_LAMAR, early]))
    assert f2[("away", "news.qb_change_confirmed")] == 0.0


def _inj(name, status, modified):
    return pl.DataFrame({"season": [2026], "week": [8], "franchise": ["BAL"], "name": [name],
                         "status": [status], "date_modified": [modified]})  # fmt: skip


def test_starters_ruled_out_new_counts_names_the_report_did_not_list_before_the_record():
    r = rec(away={"starters_ruled_out": ["Jacoby Brissett", "Lamar Jackson"]})
    key = ("away", "news.starters_ruled_out_new")
    d = _depth([CHART_LAMAR])
    assert _feat([r], d, _inj("Jacoby Brissett", "Out", datetime(2026, 10, 27, 12)))[0][key] == 1.0
    # the same row stamped after the record is invisible to it: both names are new
    assert _feat([r], d, _inj("Jacoby Brissett", "Out", datetime(2026, 10, 29, 12)))[0][key] == 2.0
    # Questionable is not Out; an unstamped row counts as known (availability's convention)
    assert _feat([r], d, _inj("Jacoby Brissett", "Questionable", None))[0][key] == 2.0
    assert _feat([r], d, _inj("J. Brissett", "Doubtful", None))[0][key] == 1.0
    assert _feat([r], d, None)[0][key] is None


def test_a_record_stamped_after_a_lock_is_invisible_to_it():
    named = rec(away={"qb_named_starter": "Jacoby Brissett"}, known_as_of="2026-10-31T10:00:00Z")
    _, rows = _feat([named], _depth([CHART_LAMAR]))
    assert store.as_of(rows, datetime(2026, 10, 31, 9, 0)).is_empty()
    seen = store.as_of(rows, datetime(2026, 10, 31, 11, 0))
    assert seen.filter(pl.col("feature") == "news.qb_change_confirmed").height == 2


def test_build_skips_pre_v3_records(tmp_path):
    paths = Paths(tmp_path)
    d = tmp_path / "marts" / "narrative" / "season=2026" / "week=08"
    d.mkdir(parents=True)
    old = rec().model_dump(mode="json") | {"schema_version": "2"}
    (d / "2026_08_BAL_BUF_old.json").write_text(json.dumps(old))
    assert news.build(paths, GAMES, BUILD).is_empty()


# ------------------------------------------------------------------------------------ repeat


def _pair(b_over):
    a = rec().model_dump(mode="json")
    b = json.loads(json.dumps(a))
    for path, v in b_over.items():
        t = b
        *head, last = path.split(".")
        for k in head:
            t = t[k]
        t[last] = v
    return a, b


def test_agreement_math_within_one_step():
    a, b = _pair({
        "home.qb_status": 1,          # 0 vs 1: integer scale, agrees
        "home.injury_impact": 3,      # 1 vs 3: two steps, disagrees
        "home.motivation": 0.6,       # 0.4 vs 0.6: within 0.25, agrees
        "away.sentiment": 0.3,        # -0.2 vs 0.3: disagrees
        "away.lookahead": True,       # flag changed: disagrees
        "weather_concern": 0.45,      # 0.3 vs 0.45: agrees
    })  # fmt: skip
    df = repeat.compare(a, b, datetime(2026, 10, 29))
    got = {(r["team"], r["rating"]): r["agree"] for r in df.iter_rows(named=True)}
    assert got[("BUF", "qb_status")] and not got[("BUF", "injury_impact")]
    assert got[("BUF", "motivation")] and not got[("BAL", "sentiment")]
    assert not got[("BAL", "lookahead")] and got[("BAL", "revenge")]
    assert got[(None, "weather_concern")] and got[(None, "upset_buzz")]
    assert df.height == 2 * 8 + 2 and set(df.columns) == set(repeat.SCHEMA)


def test_agreement_reads_the_table_by_rating_and_is_empty_without_it(tmp_path):
    from nfl import io

    paths = Paths(tmp_path)
    assert repeat.agreement(paths) == {}
    a, b = _pair({"home.injury_impact": 3})
    io.append(repeat.path(paths), repeat.compare(a, b, datetime(2026, 10, 29)), repeat.SCHEMA)
    a2, b2 = _pair({})
    io.append(repeat.path(paths), repeat.compare(a2, b2, datetime(2026, 11, 5)), repeat.SCHEMA)
    ag = repeat.agreement(paths)
    assert ag["injury_impact"] == (0.75, 4) and ag["qb_status"] == (1.0, 4)
    assert ag["weather_concern"] == (1.0, 2)
    assert "injury_impact" not in repeat.silenced(paths)  # 4 pairs: too few to silence
    assert "| injury_impact | 4 | 75% |" in repeat.report(paths)


def test_repeat_reruns_a_stored_game_without_storing_it(tmp_path, monkeypatch):
    paths = _games(tmp_path)
    monkeypatch.setattr(cr, "now_utc", lambda: NOW)
    monkeypatch.setattr(repeat, "now_utc", lambda: NOW)
    first = _record() | {"producer": "claude_max", "prompt_version": "claude_v2"}
    f = tmp_path / "r.json"
    f.write_text(json.dumps(first))
    nar.ingest(paths, f, now=datetime(2026, 10, 28, 21, 0))
    monkeypatch.setattr(nar, "slate", lambda p, s, w, now=None: pl.DataFrame([_row()]))

    def fake_claude(cmd, **kw):
        folder = Path(kw["cwd"])
        rec2 = _record()
        rec2["away"]["injury_impact"] = 0  # 2 vs 0: disagrees
        _transcript(folder, [URL_A], ["Ravens week 8"])
        (folder / "record.json").write_text(json.dumps(rec2))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(cr, "Fetcher", lambda *a, **k: _Pages())
    out = repeat.run(paths, 2026, 8, 3, runner=fake_claude, login=lambda: "max")
    assert out == [("2026_08_BAL_BUF", None)]
    assert len(nar.load_records(paths)) == 1  # nothing stored
    ag = repeat.agreement(paths)
    assert ag["injury_impact"] == (0.5, 2) and ag["qb_status"][1] == 2


# ------------------------------------------------------------------------------ status pass


class _StatusPages:
    def get(self, url):
        t = "Jacoby Brissett will start for Baltimore after the trade. Lamar Jackson is out."
        return Page(url, url, "t", t, date(2026, 10, 30), NOW, 200, True, None)


def test_status_only_merge_keeps_the_record_and_stamps_a_new_known_as_of(tmp_path, monkeypatch):
    paths = _games(tmp_path)
    base = rec(producer="claude_max", prompt_version="claude_v2")
    now = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(cr, "now_utc", lambda: now)
    status = {
        "home": {"team": "BUF", "qb_status": 0, "qb_named_starter": None, "injury_impact": 1,
                 "starters_ruled_out": [], "key_absences": []},
        "away": {"team": "BAL", "qb_status": 2, "qb_named_starter": "Jacoby Brissett",
                 "injury_impact": 3, "starters_ruled_out": ["Lamar Jackson"],
                 "key_absences": ["Lamar Jackson (QB, Out)"]},
        "claims": [{"claim": "Jacoby Brissett will start for Baltimore after the trade.",
                    "category": "qb", "team": "BAL", "source_url": URL_A,
                    "published_at": "2026-10-30", "confidence": "high"}],
        "searches": ["Ravens QB Friday"],
    }  # fmt: skip

    def fake_claude(cmd, **kw):
        folder = Path(kw["cwd"])
        names = {p.name for p in folder.iterdir()}
        assert "previous.json" in names and "record.json" not in names
        _transcript(folder, [URL_A], ["Ravens QB Friday"])
        (folder / "status.json").write_text(json.dumps(status))
        return subprocess.CompletedProcess(cmd, 0)

    run = cr.research_game(paths, _row(), store=True, run=fake_claude, fetcher=_StatusPages(), now=now, base=base)  # fmt: skip
    assert run.ok and run.stored, run.error
    new = json.loads(run.stored.read_text())
    assert new["pass_kind"] == "status" and new["producer"] == "claude_max"
    assert new["prompt_version"] == "claude_status_v1" and new["schema_version"] == "3"
    assert new["known_as_of"] == "2026-10-30T12:00:00"
    assert new["known_as_of"] != base.known_as_of.isoformat()
    # status fields replaced
    assert new["away"]["qb_named_starter"] == "Jacoby Brissett"
    assert new["away"]["qb_name"] == "Jacoby Brissett"
    assert new["away"]["starters_ruled_out"] == ["Lamar Jackson"] and new["away"]["injury_impact"] == 3  # fmt: skip
    assert new["home"]["injury_impact"] == 1
    # everything else kept
    before = base.model_dump(mode="json")
    for k in ("summary", "notes", "scheme_trends", "sentiment", "hype", "motivation", "revenge"):
        assert new["away"][k] == before["away"][k]
    assert new["consensus_narrative"] == base.consensus_narrative and new["matchup_notes"]
    assert new["upset_buzz"] == base.upset_buzz
    assert new["searches"] == [*base.searches, "Ravens QB Friday"]
    assert [c["category"] for c in new["claims"]] == ["qb"]  # the base's injury claim is superseded
    recs = nar.load_records(paths)
    assert [r.pass_kind for r in recs] == ["status"]
    assert read_calls(paths)["job"].to_list() == ["research_claude_status"]
