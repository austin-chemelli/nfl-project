"""Margin-of-victory Elo, FiveThirtyEight style. Walk-forward by construction: a game's prediction is
produced before its result updates the ratings."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import log

import polars as pl

from nfl.models.market import norm_cdf

MODEL_ID = "elo_v0"
MODEL_VERSION = "0.1"

TEAM_ALIASES = {"OAK": "LV", "SD": "LAC", "STL": "LA"}


@dataclass
class EloParams:
    k: float = 20.0
    hfa: float = 48.0  # Elo points of home-field advantage (~2 points of spread)
    points_per_elo: float = 25.0  # 25 Elo ≈ 1 point of spread
    regress: float = 1 / 3  # offseason regression toward the mean
    mean: float = 1505.0
    sd_margin: float = 13.5


@dataclass
class Elo:
    params: EloParams = field(default_factory=EloParams)
    ratings: dict[str, float] = field(default_factory=dict)
    season: int | None = None

    def _team(self, t: str) -> str:
        return TEAM_ALIASES.get(t, t)

    def rating(self, team: str) -> float:
        return self.ratings.setdefault(self._team(team), 1500.0)

    def new_season(self, season: int) -> None:
        if self.season is not None and season != self.season:
            for t in self.ratings:
                self.ratings[t] += (self.params.mean - self.ratings[t]) * self.params.regress
        self.season = season

    def predict(self, home: str, away: str, neutral: bool = False) -> dict:
        diff = self.rating(home) - self.rating(away) + (0 if neutral else self.params.hfa)
        p_home = 1.0 / (1.0 + 10 ** (-diff / 400.0))
        spread = diff / self.params.points_per_elo
        return {
            "p_home": p_home,
            "spread_home": spread,
            "total": None,
            "sd_margin": self.params.sd_margin,
            "elo_home": self.rating(home),
            "elo_away": self.rating(away),
        }

    def update(self, home: str, away: str, result: float, neutral: bool = False) -> None:
        """result = home_score - away_score."""
        pred = self.predict(home, away, neutral)
        p_home = pred["p_home"]
        actual = 1.0 if result > 0 else 0.0 if result < 0 else 0.5
        winner_diff = (self.rating(home) - self.rating(away)) * (1 if result >= 0 else -1)
        mov = log(abs(result) + 1) * 2.2 / (winner_diff * 0.001 + 2.2)
        shift = self.params.k * mov * (actual - p_home)
        self.ratings[self._team(home)] += shift
        self.ratings[self._team(away)] -= shift


def p_from_spread(spread: float, sd: float) -> float:
    return norm_cdf(spread / sd)


def pregame_ratings(games: pl.DataFrame, params: EloParams | None = None) -> pl.DataFrame:
    """Pre-game Elo for every game: (game_id, home_elo, away_elo), no home-field advantage.

    Walks games chronologically exactly like `nfl.predict`: `new_season` before each game, neutral =
    location != 'Home', ratings updated only when the result is known. Upcoming games therefore get
    the current ratings."""
    e = Elo(params or EloParams())
    ordered = games.sort("kickoff_utc", "game_id", nulls_last=True)
    ids: list[str] = []
    home: list[float] = []
    away: list[float] = []
    for g in ordered.iter_rows(named=True):
        e.new_season(g["season"])
        ids.append(g["game_id"])
        home.append(e.rating(g["home_team"]))
        away.append(e.rating(g["away_team"]))
        if g["result"] is not None:
            neutral = (g["location"] or "Home") != "Home"
            e.update(g["home_team"], g["away_team"], g["result"], neutral)
    return pl.DataFrame(
        {"game_id": ids, "home_elo": home, "away_elo": away},
        schema={"game_id": pl.Utf8, "home_elo": pl.Float64, "away_elo": pl.Float64},
    )
