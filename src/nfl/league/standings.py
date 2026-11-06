"""Standings measures behind the NFL tiebreakers (ADR 0019).

`Results` holds a set of finished (or simulated) games and derives every measure the tiebreak
procedure needs, lazily and per team: W-L-T with a tie as half a win, records against a set of
opponents (division, conference, common), strength of victory and of schedule, points and their
ranks. Team codes are canonical (OAK, SD and STL map through `canon`).

Built for the Monte Carlo: `extended` adds a season's simulated games to a played base without
rebuilding the base from per-game data, and only totals are updated per game. Points are tracked
only for games with scores, so a simulated game costs three small tuple updates per club.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from nfl.league.divisions import DIVISION_TEAMS, DIVISIONS
from nfl.models.elo import TEAM_ALIASES

# (wins, ties, games); losses are games - wins - ties
_ZERO = (0, 0, 0)

DIVISION_SET: dict[str, frozenset[str]] = {
    t: frozenset(DIVISION_TEAMS[d]) for t, (_, d) in DIVISIONS.items()
}
CONFERENCE_SET: dict[str, frozenset[str]] = {
    c: frozenset(t for t, (cc, _) in DIVISIONS.items() if cc == c) for c in ("AFC", "NFC")
}


def canon(team: str) -> str:
    """Historical codes (OAK, SD, STL) to the current franchise code."""
    return TEAM_ALIASES.get(team, team)


@dataclass(frozen=True, slots=True)
class GameResult:
    home: str
    away: str
    outcome: float  # 1.0 home win, 0.5 tie, 0.0 away win
    home_score: int | None = None  # None for a simulated game
    away_score: int | None = None

    @classmethod
    def from_scores(cls, home: str, away: str, home_score: int, away_score: int) -> GameResult:
        """A played game from its score, with historical codes mapped."""
        o = 1.0 if home_score > away_score else 0.0 if home_score < away_score else 0.5
        return cls(canon(home), canon(away), o, int(home_score), int(away_score))


class Results:
    __slots__ = ("_cache", "_net", "_opp", "_own_pts", "_pa", "_pf", "_tot", "left", "scored")

    def __init__(
        self, games: Iterable[GameResult], remaining: Iterable[tuple[str, str]] | None = None
    ):
        """`remaining` is the unplayed schedule as (home, away) pairs; it feeds `left`."""
        self._tot: dict[str, tuple[int, int, int]] = {}
        self._opp: dict[str, dict[str, tuple[int, int, int]]] = {}
        self._pf: dict[str, int] = {}
        self._pa: dict[str, int] = {}
        self._net: dict[str, dict[str, int]] = {}  # team -> opponent -> points for - against
        self._own_pts = True
        self.scored = True  # every game has a score
        self._cache: dict = {}
        self.left: dict[str, int] | None = None
        self._add(games)
        if remaining is not None:
            self.left = {t: 0 for t in self._tot}
            for h, a in remaining:
                self.left[h] = self.left.get(h, 0) + 1
                self.left[a] = self.left.get(a, 0) + 1

    def extended(self, games: Iterable[GameResult]) -> Results:
        """A new Results: this one's games plus `games` (this one is left untouched)."""
        if self.left is not None:
            games = list(games)
        new = Results.__new__(Results)
        new._tot = self._tot.copy()
        new._opp = {t: d.copy() for t, d in self._opp.items()}
        new._pf, new._pa, new._net = self._pf, self._pa, self._net  # copied on first score
        new._own_pts = False
        new.scored = self.scored
        new._cache = {}
        new.left = None
        new._add(games)
        if self.left is not None:
            left = self.left.copy()
            for g in games:
                left[g.home] = max(0, left.get(g.home, 0) - 1)
                left[g.away] = max(0, left.get(g.away, 0) - 1)
            new.left = left
        return new

    def _add(self, games: Iterable[GameResult]) -> None:
        tot, opp = self._tot, self._opp
        for g in games:
            h, a, o = g.home, g.away, g.outcome
            if o == 1.0:
                hw, ht, aw, at = 1, 0, 0, 0
            elif o == 0.0:
                hw, ht, aw, at = 0, 0, 1, 0
            else:
                hw, ht, aw, at = 0, 1, 0, 1
            x = tot.get(h, _ZERO)
            tot[h] = (x[0] + hw, x[1] + ht, x[2] + 1)
            x = tot.get(a, _ZERO)
            tot[a] = (x[0] + aw, x[1] + at, x[2] + 1)
            d = opp.get(h)
            if d is None:
                d = opp[h] = {}
            x = d.get(a, _ZERO)
            d[a] = (x[0] + hw, x[1] + ht, x[2] + 1)
            d = opp.get(a)
            if d is None:
                d = opp[a] = {}
            x = d.get(h, _ZERO)
            d[h] = (x[0] + aw, x[1] + at, x[2] + 1)
            hs, as_ = g.home_score, g.away_score
            if hs is None or as_ is None:
                self.scored = False
            else:
                self._add_points(h, a, hs, as_)

    def _add_points(self, h: str, a: str, hs: int, as_: int) -> None:
        if not self._own_pts:  # copy on first write
            self._pf, self._pa = self._pf.copy(), self._pa.copy()
            self._net = {t: d.copy() for t, d in self._net.items()}
            self._own_pts = True
        pf, pa, net = self._pf, self._pa, self._net
        pf[h] = pf.get(h, 0) + hs
        pa[h] = pa.get(h, 0) + as_
        pf[a] = pf.get(a, 0) + as_
        pa[a] = pa.get(a, 0) + hs
        net.setdefault(h, {})
        net.setdefault(a, {})
        net[h][a] = net[h].get(a, 0) + hs - as_
        net[a][h] = net[a].get(h, 0) + as_ - hs

    # --- records ---------------------------------------------------------------------------

    @property
    def teams(self) -> list[str]:
        return list(self._tot)

    @property
    def games_played(self) -> dict[str, int]:
        return {t: v[2] for t, v in self._tot.items()}

    def record(self, team: str) -> tuple[int, int, int]:
        """(wins, losses, ties) over every game."""
        w, t, n = self._tot.get(team, _ZERO)
        return w, n - w - t, t

    def pct(self, team: str) -> float:
        """Win percentage with a tie as half a win; 0.0 with no games."""
        w, t, n = self._tot.get(team, _ZERO)
        return (w + t / 2) / n if n else 0.0

    def record_vs(self, team: str, opps: Iterable[str]) -> tuple[int, int, int]:
        """(wins, losses, ties) against the clubs in `opps`."""
        od = self._opp.get(team)
        w = t = n = 0
        if od:
            for o in opps:
                x = od.get(o)
                if x is not None:
                    w += x[0]
                    t += x[1]
                    n += x[2]
        return w, n - w - t, t

    def pct_vs(self, team: str, opps: Iterable[str]) -> float | None:
        """Win percentage against `opps`; None if the team played none of them."""
        w, l, t = self.record_vs(team, opps)
        n = w + l + t
        return (w + t / 2) / n if n else None

    def games_vs(self, team: str, opps: Iterable[str]) -> int:
        return sum(self.record_vs(team, opps))

    def division_record(self, team: str) -> tuple[int, int, int]:
        return (
            self.record_vs(team, DIVISION_SET[team] - {team}) if team in DIVISION_SET else (0,) * 3
        )

    def conference_record(self, team: str) -> tuple[int, int, int]:
        if team not in DIVISIONS:
            return (0, 0, 0)
        return self.record_vs(team, CONFERENCE_SET[DIVISIONS[team][0]] - {team})

    def opponents(self, team: str) -> set[str]:
        return set(self._opp.get(team, ()))

    def common_opponents(self, teams: Iterable[str]) -> set[str]:
        """Opponents every club in `teams` played, not counting the clubs themselves."""
        teams = list(teams)
        sets = [set(self._opp.get(t, ())) for t in teams]
        return set.intersection(*sets) - set(teams) if sets else set()

    # --- strength -------------------------------------------------------------------------

    def _opp_pct_sum(self, weights: dict[str, int]) -> float:
        num = den = 0
        for o, m in weights.items():
            w, t, n = self._tot.get(o, _ZERO)
            num += m * (2 * w + t)
            den += m * 2 * n
        return num / den if den else 0.0

    def sov(self, team: str) -> float:
        """Combined win percentage of the opponents this club beat (once per win)."""
        c = self._cache.get(("sov", team))
        if c is None:
            c = self._cache[("sov", team)] = self._opp_pct_sum(
                {o: x[0] for o, x in self._opp.get(team, {}).items() if x[0]}
            )
        return c

    def sos(self, team: str) -> float:
        """Combined win percentage of every opponent (once per game played)."""
        c = self._cache.get(("sos", team))
        if c is None:
            c = self._cache[("sos", team)] = self._opp_pct_sum(
                {o: x[2] for o, x in self._opp.get(team, {}).items()}
            )
        return c

    # --- points (only meaningful when `scored`) -----------------------------------------

    def points(self, team: str) -> tuple[int, int]:
        return self._pf.get(team, 0), self._pa.get(team, 0)

    def net_points(self, team: str, opps: Iterable[str] | None = None) -> int:
        if opps is None:
            return self._pf.get(team, 0) - self._pa.get(team, 0)
        nd = self._net.get(team, {})
        return sum(nd.get(o, 0) for o in opps)

    def points_ranks(self) -> tuple[dict[str, int], dict[str, int]]:
        """(league, conference) rank sums: rank in points scored plus rank in points allowed.

        Lower is better; clubs level on a measure share its rank. Ranked among the clubs in the
        results only.
        """
        c = self._cache.get("ranks")
        if c is None:
            teams = list(self._tot)
            league = _rank_sum(teams, self._pf, self._pa)
            conf: dict[str, int] = {}
            for members in CONFERENCE_SET.values():
                conf.update(_rank_sum([t for t in teams if t in members], self._pf, self._pa))
            c = self._cache["ranks"] = (league, conf)
        return c


def _rank_sum(teams: list[str], pf: dict[str, int], pa: dict[str, int]) -> dict[str, int]:
    f = [pf.get(t, 0) for t in teams]
    a = [pa.get(t, 0) for t in teams]
    return {
        t: 2 + sum(1 for x in f if x > f[i]) + sum(1 for x in a if x < a[i])
        for i, t in enumerate(teams)
    }
