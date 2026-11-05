"""Week recap (M9.5, ADR 0016): `build_recap` aggregates a week's game retros into a `WeekRecap`
and writes `marts/retro/season=S/recap_<ww>.json`.

Judgment calls: upsets are limited to winners the market rated below 50%; luckiest/unluckiest are
ranked by *pure* luck (factors that are not partly skill: fumbles, kicks, return plays), and the
recap's `luck_net` carries that pure-luck sum.
"""

from __future__ import annotations

import json
import math

from nfl.config import Paths, now_utc
from nfl.retro.game import _names, _sig, pure_luck, retro_path
from nfl.retro.schema import (
    BoldCall,
    RecapGame,
    RecapModel,
    RecapTeam,
    RetroGame,
    TeamRetro,
    WeekRecap,
)

MARKET = "market_baseline"
N_TOP = 3


def recap_path(paths: Paths, season: int, week: int):
    return paths.marts / "retro" / f"season={season}" / f"recap_{week:02d}.json"


def load_week(paths: Paths, season: int, week: int) -> list[RetroGame]:
    d = retro_path(paths, season, "x").parent
    out = []
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        if f.name.startswith("recap_"):
            continue
        g = RetroGame.model_validate_json(f.read_text())
        if g.week == week:
            out.append(g)
    return out


def _winner_p(g: RetroGame, p_home: float) -> float | None:
    m = g.result.margin
    return None if m == 0 else (p_home if m > 0 else 1 - p_home)


def _score(g: RetroGame) -> str:
    r = g.result
    return f"{max(r.home_score, r.away_score)}-{min(r.home_score, r.away_score)}"


def _upsets(games: list[RetroGame], names: dict[str, str]) -> list[RecapGame]:
    rows = []
    for g in games:
        m = next((p for p in g.predictions if p.model_id == MARKET), None)
        wp = None if m is None else _winner_p(g, m.p_home)
        if wp is not None and wp < 0.5:
            rows.append((wp, g))
    out = []
    for wp, g in sorted(rows, key=lambda t: (t[0], t[1].game_id))[:N_TOP]:
        home_won = g.result.margin > 0
        win, lose = (g.home, g.away) if home_won else (g.away, g.home)
        nm = lambda c: names.get(c, c)
        place = f"at {nm(g.home)}" if not home_won else f"over {nm(lose)}"
        out.append(
            RecapGame(
                game_id=g.game_id,
                away=g.away,
                home=g.home,
                value=round(wp, 3),
                sentence=f"{nm(win)} won {_score(g)} {place} with a {round(100 * wp)}% market "
                f"win chance.",
            )
        )
    return out


def _misread(games: list[RetroGame], names: dict[str, str]) -> list[RecapGame]:
    rows = []
    for g in games:
        e = next((p for p in g.predictions if p.model_id == "student"), None)
        if e is not None:
            rows.append((e.log_loss, e, g))
    out = []
    for ll, e, g in sorted(rows, key=lambda t: (-t[0], t[2].game_id))[:N_TOP]:
        nm = lambda c: names.get(c, c)
        m = g.result.margin
        end = (
            f"the game ended {_score(g)}"
            if m == 0
            else f"{nm(g.home if m > 0 else g.away)} won {_score(g)}"
        )
        out.append(
            RecapGame(
                game_id=g.game_id,
                away=g.away,
                home=g.home,
                value=round(ll, 3),
                sentence=f"The Student gave {nm(e.pick)} {round(100 * e.p_pick)}% and {end}.",
            )
        )
    return out


def _bold_calls(
    games: list[RetroGame], names: dict[str, str]
) -> tuple[BoldCall | None, BoldCall | None]:
    """The week's best right call and costliest wrong call across approaches (not per approach)."""
    rows = [
        (p, g) for g in games for p in g.predictions if p.kind == "approach" and p.right is not None
    ]

    def call(p, g: RetroGame) -> BoldCall:
        earned = math.log(2) - p.log_loss
        pct = round(100 * p.p_pick)
        who = f"{p.label} gave {names.get(p.pick, p.pick)} {pct}%"
        if p.right:
            tail = f"and they won: {earned:.2f} better than a coin flip."
        else:
            tail = f"and they lost: {-earned:.2f} worse than a coin flip."
        return BoldCall(
            game_id=g.game_id,
            away=g.away,
            home=g.home,
            model_id=p.model_id,
            label=p.label,
            pick=p.pick,
            p_pick=p.p_pick,
            log_loss=p.log_loss,
            earned=round(earned, 3),
            sentence=f"{who} {tail}",
        )

    right = [r for r in rows if r[0].right]
    wrong = [r for r in rows if not r[0].right]
    best = min(right, key=lambda r: (r[0].log_loss, r[1].game_id, r[0].model_id), default=None)
    worst = min(wrong, key=lambda r: (-r[0].log_loss, r[1].game_id, r[0].model_id), default=None)
    return (call(*best) if best else None, call(*worst) if worst else None)


def _luck_rows(games: list[RetroGame], names: dict[str, str]):
    rows = []
    for g in games:
        for t in g.teams.values():
            rows.append((pure_luck(t), t, g))
    return rows


def _team_sentence(v: float, t: TeamRetro, names: dict[str, str]) -> str:
    pure = [f for f in t.luck if not f.partly_skill]
    top = max(pure, key=lambda f: abs(f.swing_pts))
    nm = names.get(t.team, t.team)
    return (
        f"{nm}: {_sig(v)} pts of pure luck, mostly {top.label[0].lower() + top.label[1:]} "
        f"({_sig(top.swing_pts)})."
    )


def _recap_team(v: float, t: TeamRetro, g: RetroGame, names) -> RecapTeam:
    return RecapTeam(
        team=t.team, game_id=g.game_id, luck_net=v, sentence=_team_sentence(v, t, names)
    )


def _models(games: list[RetroGame]) -> list[RecapModel]:
    acc: dict[str, dict] = {}
    market: dict[str, float] = {}
    for g in games:
        for p in g.predictions:
            d = acc.setdefault(p.model_id, {"label": p.label, "kind": p.kind, "ll": {}, "right": 0})
            d["ll"][g.game_id] = p.log_loss
            d["right"] += 1 if p.right else 0
            if p.model_id == MARKET:
                market[g.game_id] = p.log_loss
    # ranked models (approaches + ensemble) are compared over the games every one of them has
    ranked_ids = [m for m, d in acc.items() if d["kind"] in ("approach", "ensemble")]
    shared = set.intersection(*(set(acc[m]["ll"]) for m in ranked_ids)) if ranked_ids else set()
    rows = []
    for mid, d in acc.items():
        ll = d["ll"]
        if mid in ranked_ids and shared:
            ll = {k: v for k, v in ll.items() if k in shared}
        mean = sum(ll.values()) / len(ll)
        common = [k for k in ll if k in market]  # games where the market has a row too
        vs = None
        if common:
            vs = round(
                sum(ll[k] for k in common) / len(common)
                - sum(market[k] for k in common) / len(common),
                3,
            )
        rows.append((mid, d, mean, vs))
    elig = sorted(
        (r for r in rows if r[1]["kind"] in ("approach", "ensemble")), key=lambda r: (r[2], r[0])
    )
    rest = sorted(
        (r for r in rows if r[1]["kind"] not in ("approach", "ensemble")),
        key=lambda r: (r[2], r[0]),
    )
    out = []
    for rank, (mid, d, mean, vs) in [(i + 1, r) for i, r in enumerate(elig)] + [
        (0, r) for r in rest
    ]:
        out.append(
            RecapModel(
                model_id=mid,
                label=d["label"],
                kind=d["kind"],
                n=len(d["ll"]),
                right=d["right"],
                log_loss=round(mean, 3),
                vs_market=vs,
                rank=rank,
            )
        )
    return out


def build_recap(paths: Paths, season: int, week: int) -> WeekRecap:
    games = load_week(paths, season, week)
    names = _names()
    models = _models(games)
    luck = _luck_rows(games, names)
    lucky = sorted(luck, key=lambda r: (-r[0], r[2].game_id, r[1].team))
    unlucky = sorted(luck, key=lambda r: (r[0], r[2].game_id, r[1].team))
    best = next((m.model_id for m in models if m.rank == 1), None)
    best_call, costliest_call = _bold_calls(games, names)
    return WeekRecap(
        season=season,
        week=week,
        built_at=now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"),
        games=sorted(g.game_id for g in games),
        best_model=best,
        models=models,
        upsets=_upsets(games, names),
        misread=_misread(games, names),
        luckiest=[_recap_team(v, t, g, names) for v, t, g in lucky[:N_TOP] if v > 0],
        unluckiest=[_recap_team(v, t, g, names) for v, t, g in unlucky[:N_TOP] if v < 0],
        note=f"One week is {len(games)} games; a model's rank here says almost nothing about "
        f"its skill.",
        best_call=best_call,
        costliest_call=costliest_call,
    )


def write_recap(paths: Paths, season: int, week: int) -> WeekRecap | None:
    if not load_week(paths, season, week):
        return None
    rec = build_recap(paths, season, week)
    out = recap_path(paths, season, week)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec.model_dump(mode="json"), indent=1) + "\n")
    return rec
