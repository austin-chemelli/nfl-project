"""The Odds API: timestamped lines for live market features, the ledger, and closing-line value.

Raw layout (immutable, like nflverse snapshots):
    raw/odds_api/<kind>/snapshot_ts=<ts>/odds.json + manifest.json
      kind = 'live'   GET /v4/sports/americanfootball_nfl/odds, snapshot_ts = fetch time

Credits (verified 2026-10-26 on the free tier, 500/month): a snapshot of h2h+spreads+totals in one
region costs 3. The historical endpoint is paid-only on this plan (HTTP 401
HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN, no credits charged), so closing lines come from our own
pre-kickoff snapshots, falling back to nflverse's schedule lines (see nfl.ledger). Every call
records x-requests-used / -remaining in its manifest, and `guard` refuses to spend past
MONTHLY_SOFT_CAP.

Curated `lines` (one row per game × snapshot × book × market × side) is built by `curate_lines`:
    game_id, season, week, kickoff_utc, snapshot_ts, is_closing, book, market ('h2h'|'spreads'|'totals'),
    side ('home'|'away'|'over'|'under'), price_american, point, book_last_update
Spreads `point` is from that side's perspective as the book quotes it (home −3.5 = home favored).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import httpx
import polars as pl

from nfl.config import Paths, now_utc, snapshot_ts

BASE = "https://api.the-odds-api.com/v4"
SPORT = "americanfootball_nfl"
MARKETS = "h2h,spreads,totals"
REGIONS = "us"
MONTHLY_SOFT_CAP = 400  # of 500 free credits; leaves headroom for manual checks
USER_AGENT = "nfl-project (github.com/austin-chemelli)"

# Odds API full names -> nflverse abbreviations (current franchises).
TEAMS: dict[str, str] = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LA", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}  # fmt: skip


class CreditCapError(RuntimeError):
    pass


@dataclass
class OddsManifest:
    kind: str
    endpoint: str  # never includes the key
    params: dict
    fetched_at: str
    snapshot_ts: str
    sha256: str
    n_events: int
    requests_used: int | None
    requests_remaining: int | None
    requests_last: int | None


def _key() -> str:
    k = os.environ.get("ODDS_API_KEY", "")
    if not k:
        raise RuntimeError("ODDS_API_KEY is not set (.env)")
    return k


def raw_dir(paths: Paths, kind: str) -> Path:
    return paths.root / "raw" / "odds_api" / kind


def _int(h: str | None) -> int | None:
    try:
        return int(float(h)) if h is not None else None
    except ValueError:
        return None


def last_usage(paths: Paths) -> int | None:
    """Credits used this billing month, per the most recent manifest (None if no calls yet)."""
    ms = sorted(paths.root.glob("raw/odds_api/*/snapshot_ts=*/manifest.json"))
    if not ms:
        return None
    latest = max(ms, key=lambda p: json.loads(p.read_text())["fetched_at"])
    return json.loads(latest.read_text()).get("requests_used")


def guard(paths: Paths, cost: int) -> None:
    used = last_usage(paths) or 0
    if used + cost > MONTHLY_SOFT_CAP:
        raise CreditCapError(f"would use {used + cost} > soft cap {MONTHLY_SOFT_CAP} credits")


class OddsAPIError(RuntimeError):
    pass


def _get(endpoint: str, params: dict) -> httpx.Response:
    """GET with the key as a query param (the API's only option). Errors are re-raised without the
    URL so the key never reaches logs or tracebacks."""
    try:
        with httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}) as c:
            r = c.get(f"{BASE}{endpoint}", params=params | {"apiKey": _key()})
    except httpx.HTTPError as e:
        raise OddsAPIError(f"{endpoint}: {type(e).__name__}") from None
    if r.status_code >= 400:
        raise OddsAPIError(f"{endpoint}: HTTP {r.status_code}: {r.text[:300]}") from None
    return r


def _write(paths: Paths, kind: str, ts: str, body: bytes, m: OddsManifest) -> Path:
    d = raw_dir(paths, kind) / f"snapshot_ts={ts}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    (d / "odds.json").write_bytes(body)
    (d / "manifest.json").write_text(json.dumps(asdict(m), indent=1))
    return d


def snapshot(paths: Paths) -> OddsManifest:
    """Current odds for every upcoming NFL game. Cost: 3 credits."""
    guard(paths, 3)
    params = {"regions": REGIONS, "markets": MARKETS, "oddsFormat": "american", "dateFormat": "iso"}
    endpoint = f"/sports/{SPORT}/odds"
    fetched = now_utc()
    r = _get(endpoint, params)
    ts = snapshot_ts(fetched)
    m = OddsManifest(
        kind="live",
        endpoint=endpoint,
        params=params,
        fetched_at=fetched.isoformat(),
        snapshot_ts=ts,
        sha256=hashlib.sha256(r.content).hexdigest(),
        n_events=len(r.json()),
        requests_used=_int(r.headers.get("x-requests-used")),
        requests_remaining=_int(r.headers.get("x-requests-remaining")),
        requests_last=_int(r.headers.get("x-requests-last")),
    )
    _write(paths, "live", ts, r.content, m)
    return m


# ------------------------------------------------------------------------------------- parsing


def parse_events(events: list[dict], snapshot: datetime) -> pl.DataFrame:
    """Odds API event list -> long rows keyed by team abbreviations (not yet matched to games)."""
    rows = []
    for ev in events:
        home, away = TEAMS.get(ev["home_team"]), TEAMS.get(ev["away_team"])
        if home is None or away is None:
            raise ValueError(f"unknown team name: {ev['home_team']!r} / {ev['away_team']!r}")
        commence = datetime.fromisoformat(ev["commence_time"])
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                for oc in mk.get("outcomes", []):
                    name = oc["name"]
                    if mk["key"] == "totals":
                        side = name.lower()
                    elif name == ev["home_team"]:
                        side = "home"
                    elif name == ev["away_team"]:
                        side = "away"
                    else:
                        continue  # e.g. 'Draw' on some books
                    rows.append(
                        (
                            ev["id"],
                            commence.replace(tzinfo=None),
                            home,
                            away,
                            snapshot.replace(tzinfo=None),
                            bk["key"],
                            mk["key"],
                            side,
                            float(oc["price"]),
                            float(oc["point"]) if oc.get("point") is not None else None,
                            mk.get("last_update") or bk.get("last_update"),
                        )
                    )
    schema = {
        "event_id": pl.Utf8,
        "commence_utc": pl.Datetime("us"),
        "home_team": pl.Utf8,
        "away_team": pl.Utf8,
        "snapshot_ts": pl.Datetime("us"),
        "book": pl.Utf8,
        "market": pl.Utf8,
        "side": pl.Utf8,
        "price_american": pl.Float64,
        "point": pl.Float64,
        "book_last_update": pl.Utf8,
    }
    return pl.DataFrame(rows, schema=schema, orient="row")


def match_games(lines: pl.DataFrame, games: pl.DataFrame, tolerance_h: float = 36) -> pl.DataFrame:
    """Attach game_id/season/week by (home, away) and the nearest kickoff within tolerance."""
    g = games.select(
        "game_id",
        "season",
        "week",
        "home_team",
        "away_team",
        pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us")),
    )
    j = lines.join(g, on=["home_team", "away_team"], how="inner")
    j = j.with_columns(
        (pl.col("commence_utc") - pl.col("kickoff_utc")).dt.total_minutes().abs().alias("_dm")
    ).filter(pl.col("_dm") <= tolerance_h * 60)
    return (
        j.sort("_dm")
        .unique(subset=["event_id", "snapshot_ts", "book", "market", "side"], keep="first")
        .drop("_dm", "commence_utc")
    )


def _snapshot_files(paths: Paths, kind: str) -> list[tuple[Path, dict]]:
    out = []
    for d in sorted(raw_dir(paths, kind).glob("snapshot_ts=*")):
        mf = d / "manifest.json"
        if (d / "odds.json").exists() and mf.exists():
            out.append((d / "odds.json", json.loads(mf.read_text())))
    return out


def curate_lines(paths: Paths, games: pl.DataFrame) -> int:
    """Rebuild curated/lines/season=YYYY/ from every raw odds snapshot. Returns rows written."""
    parts = []
    for f, m in _snapshot_files(paths, "live"):
        snap = datetime.strptime(m["snapshot_ts"], "%Y%m%dT%H%M%SZ")
        parts.append(parse_events(json.loads(f.read_text()), snap))
    out_dir = paths.curated_table("lines")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    if not parts:
        return 0
    lines = match_games(pl.concat(parts), games)
    lines = lines.with_columns(_closing_flag(lines))
    for (season,), part in lines.group_by(["season"]):
        d = out_dir / f"season={season}"
        d.mkdir(parents=True, exist_ok=True)
        part.drop("season").write_parquet(d / "lines.parquet")
    return lines.height


def _closing_flag(lines: pl.DataFrame) -> pl.Expr:
    """is_closing: the latest snapshot strictly before kickoff for that game (any kind)."""
    before = pl.col("snapshot_ts") < pl.col("kickoff_utc")
    last = pl.col("snapshot_ts").filter(before).max().over("game_id")
    return (before & (pl.col("snapshot_ts") == last)).alias("is_closing")


def read_lines(paths: Paths, seasons: tuple[int, int] | None = None) -> pl.DataFrame:
    d = paths.curated_table("lines")
    files = sorted(d.glob("season=*/lines.parquet"))
    if seasons:
        files = [f for f in files if seasons[0] <= int(f.parent.name.split("=")[1]) <= seasons[1]]
    if not files:
        return pl.DataFrame()
    return pl.concat(
        [
            pl.read_parquet(f).with_columns(
                pl.lit(int(f.parent.name.split("=")[1])).alias("season")
            )
            for f in files
        ],
        how="diagonal_relaxed",
    )


def consensus(lines: pl.DataFrame) -> pl.DataFrame:
    """Per (game_id, snapshot_ts): median across books of the moneylines, the home spread (nflverse
    sign, + = home favored) with its prices, and the total, plus the vig-free home probability from
    the median moneylines. Medians of American odds are fine here: books cluster tightly."""
    from nfl.features.market import _implied_expr

    h2h = (
        lines.filter(pl.col("market") == "h2h")
        .pivot(on="side", index=["game_id", "snapshot_ts", "book"], values="price_american")
        .group_by("game_id", "snapshot_ts")
        .agg(pl.col("home").median().alias("home_ml"), pl.col("away").median().alias("away_ml"))
    )
    sp = lines.filter(pl.col("market") == "spreads")
    spread = (
        sp.filter(pl.col("side") == "home")
        .group_by("game_id", "snapshot_ts")
        .agg(
            (-pl.col("point")).median().alias("spread_home"),  # nflverse sign: + = home favored
            pl.col("price_american").median().alias("home_spread_price"),
        )
        .join(
            sp.filter(pl.col("side") == "away")
            .group_by("game_id", "snapshot_ts")
            .agg(pl.col("price_american").median().alias("away_spread_price")),
            on=["game_id", "snapshot_ts"],
            how="left",
        )
    )
    total = (
        lines.filter((pl.col("market") == "totals") & (pl.col("side") == "over"))
        .group_by("game_id", "snapshot_ts")
        .agg(pl.col("point").median().alias("total"), pl.len().alias("n_books"))
    )
    out = h2h.join(spread, on=["game_id", "snapshot_ts"], how="full", coalesce=True).join(
        total, on=["game_id", "snapshot_ts"], how="full", coalesce=True
    )
    ph = _implied_expr("home_ml").alias("_ph")
    pa = _implied_expr("away_ml").alias("_pa")
    return (
        out.with_columns(ph, pa)
        .with_columns((pl.col("_ph") / (pl.col("_ph") + pl.col("_pa"))).alias("p_home_vigfree"))
        .drop("_ph", "_pa")
        .sort("game_id", "snapshot_ts")
    )
