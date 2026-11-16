"""The game's Health board (Austin, 2026-11-15): each offense's position rooms against the defensive
rooms that face them, at full strength and now with the listed absences.

Inputs are the two teams' health records (`players.health` plus the room grades of `players.rooms`):
ranks 1-32 for a room at full strength (`rank`) and its estimate now (`now_rank`), and the
full-strength starters with this week's status. Nothing new is estimated here: a pair only sets two
ranks side by side, says which side the gap favours and whether the injuries moved it, and fills a
template sentence from those numbers and the names of who is missing. Context only (ADR 0027).
"""

from __future__ import annotations

# offense room -> the defensive room that faces it, in display order
PAIRS = (("WR", "CB"), ("TE", "LB"), ("RB", "LB"), ("OL", "EDGE"), ("OL", "DL"))
NAME = {
    "QB": "quarterback room", "RB": "backs", "WR": "receivers", "TE": "tight ends",
    "OL": "offensive line", "EDGE": "edge rushers", "DL": "interior line", "LB": "linebackers",
    "CB": "corners", "S": "safeties",
}  # fmt: skip
EVEN = 6  # ranks: a smaller gap between the two rooms reads even
FLAG_GAP = 12  # a pair is flagged when the rooms are this far apart now...
FLAG_MOVED = 8  # ...or the injuries moved the gap by this much
NAMES_SHOWN = 2
HURT = 3  # ranks: a smaller drop from full strength isn't called a change
SINGULAR = {"QB", "OL", "DL"}  # "the offensive line faces", "the receivers face"


def _missing(starters: list[dict], grp: str) -> list[dict]:
    """Who in the room isn't expected to play fully, those who won't play first, then key players:
    name, status (IR, Out, Questionable, ...) and whether he's out (expected not to play)."""
    rows = [s for s in starters if s.get("grp") == grp and s["p_play"] < 1 and not s.get("doubt")]
    rows.sort(key=lambda s: (s["p_play"] > 0, not s.get("key"), s["p_play"]))
    return [
        {
            "player": s["player"],
            "status": s["status"],
            "out": s["p_play"] == 0,
            "key": bool(s.get("key")),
        }
        for s in rows
    ]


def _who(missing: list[dict]) -> str:
    """ " with Jaycee Horn and Mike Jackson out", " with A out and B questionable", or ""."""
    shown = missing[:NAMES_SHOWN]
    more = len(missing) - len(shown)
    out = [m["player"] for m in shown if m["out"]]
    iffy = [f"{m['player']} {(m['status'] or 'listed').lower()}" for m in shown if not m["out"]]
    parts = ([" and ".join(out) + " out"] if out else []) + iffy
    if not parts:
        return ""
    return " with " + " and ".join(parts) + (f" and {more} more" if more else "")


def _room(team: str, r: dict, starters: list[dict]) -> dict:
    return {
        "team": team, "grp": r["grp"], "name": NAME.get(r["grp"], r["grp"]),
        "rank": r["rank"], "label": r["label"], "now_rank": r["now_rank"],
        "now_label": r["now_label"], "health": r.get("health"),
        "missing": _missing(starters, r["grp"]),
    }  # fmt: skip


def _sentence(o: dict, d: dict) -> str:
    """One line for a flagged pair, from its ranks and names."""

    def hurt(x: dict) -> str:
        return f"usually {x['label']} (#{x['rank']}) but about #{x['now_rank']} now" + _who(
            x["missing"]
        )

    def plain(x: dict) -> str:
        return f"#{x['rank']}, {x['label']}"

    o_hurt, d_hurt = (x["now_rank"] - x["rank"] >= HURT for x in (o, d))
    if d_hurt and (not o_hurt or abs(d["now_rank"] - d["rank"]) >= abs(o["now_rank"] - o["rank"])):
        lead = f"{o['team']}'s {o['name']} ({plain(o) if not o_hurt else 'about #' + str(o['now_rank']) + ' now'})"
        return f"{lead} {_face(o)} {d['team']}'s {d['name']}, {hurt(d)}."
    if o_hurt:
        lead = f"{d['team']}'s {d['name']} ({plain(d)})"
        return f"{lead} {_face(d)} {o['team']}'s {o['name']}, {hurt(o)}."
    return (
        f"{o['team']}'s {o['name']} ({plain(o)}) {_face(o)} {d['team']}'s {d['name']} ({plain(d)})."
    )


def _face(x: dict) -> str:
    return "faces" if x["grp"] in SINGULAR else "face"


def pair(off_team: str, off: dict, off_starters: list[dict], def_team: str, dfn: dict,
         def_starters: list[dict]) -> dict:  # fmt: skip
    o, d = _room(off_team, off, off_starters), _room(def_team, dfn, def_starters)
    gap_now = d["now_rank"] - o["now_rank"]  # > 0: the offense's room ranks better
    gap_full = d["rank"] - o["rank"]
    favours = None if abs(gap_now) < EVEN else (off_team if gap_now > 0 else def_team)
    moved = abs(gap_now - gap_full) >= FLAG_MOVED
    flag = abs(gap_now) >= FLAG_GAP or moved
    return {
        "offense": o, "defense": d, "favours": favours, "moved": moved, "flag": flag,
        "sentence": _sentence(o, d) if flag else None,
        "_shift": abs(gap_now - gap_full), "_gap": abs(gap_now),
    }  # fmt: skip


def board(home: str, away: str, h_home: dict | None, h_away: dict | None) -> dict | None:
    """Both sides of the ball as pairs, a lede (the pair the injuries moved most, else the widest
    flagged gap) and a note per team whose quarterback room moved. None without both teams' rooms."""
    teams = {home: h_home, away: h_away}
    if not all(h and h.get("rooms") and h.get("now") for h in teams.values()):
        return None
    rooms = {t: {r["grp"]: r for r in h["rooms"]} for t, h in teams.items()}
    starters = {t: h["now"]["starters"] for t, h in teams.items()}
    sides, flagged = [], []
    for off, dfn in ((away, home), (home, away)):
        rows = [
            pair(off, rooms[off][a], starters[off], dfn, rooms[dfn][b], starters[dfn])
            for a, b in PAIRS
            if a in rooms[off] and b in rooms[dfn]
        ]
        flagged += [r for r in rows if r["flag"]]
        sides.append({"offense": off, "defense": dfn, "rows": rows})
    # the pair the injuries moved most; with none moved, the widest gap
    lede = max(
        flagged,
        key=lambda r: (r["moved"], r["_shift"] if r["moved"] else 0, r["_gap"]),
        default=None,
    )
    notes = []
    for t in (away, home):
        q = rooms[t].get("QB")
        if q and q["now_rank"] - q["rank"] >= HURT:
            who = _missing(starters[t], "QB")
            notes.append(
                f"{t}'s quarterback room goes from #{q['rank']} to about #{q['now_rank']}"
                + _who(who)
                + "."
            )
    for s in sides:
        for r in s["rows"]:
            r.pop("_shift"), r.pop("_gap")
    return {
        "sides": sides,
        "lede": lede["sentence"] if lede else None,
        "lede_kind": None if not lede else "moved" if lede["moved"] else "gap",
        "notes": notes,
    }
