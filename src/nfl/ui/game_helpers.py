"""Pure helpers for the Game page: feature formatting, edges, contributions, tendencies, narrative."""

from __future__ import annotations

from nfl.ui import data

QB_STATUS = {0: "healthy starter", 1: "questionable / limited / new", 2: "backup or unknown"}

# Tendency metrics shown as dumbbells: (label, offense metric, defense metric, unit, help).
# A metric the other side has no counterpart for passes None for that side.
TENDENCY_PAIRS = [
    ("Pass rate", "pass_rate", "pass_rate_faced", "pct",
     ("Share of plays that are passes: how often the offense throws, and how often the defense "
     "has faced a pass.")),
    ("Success rate", "success_rate", "success_rate_allowed", "pct",
     ("Share of plays that gain enough to keep the offense on schedule. Higher is better for the "
     "offense; for the defense it is the rate it allows.")),
    ("EPA per play", "epa_per_play", "epa_per_play_allowed", "epa",
     ("Expected points added per play: how much each play moves the scoreboard odds. Defense: "
     "what it gives up.")),
    ("Motion rate", "motion_rate", None, "pct",
     "Share of plays with a pre-snap motion by a skill player."),
    ("Play-action rate", "play_action_rate", None, "pct",
     "Share of pass plays that start with a run fake."),
    ("Blitz rate", None, "blitz_rate", "pct",
     "Share of pass plays where the defense sends an extra pass rusher."),
    ("8+ in the box vs run", None, "box_8plus_vs_run_rate", "pct",
     "Share of run plays where the defense stacks 8 or more players near the line."),
]  # fmt: skip
TENDENCY_EXTRA = {  # shown only in the table
    "no_huddle_rate": ("No-huddle rate", "pct"), "shotgun_rate": ("Shotgun rate", "pct"),
    "under_center_rate": ("Under-center rate", "pct"), "rpo_rate": ("RPO rate", "pct"),
    "screen_rate": ("Screen rate", "pct"), "fourth_down_go_rate": ("4th-down go rate", "pct"),
    "pass_rushers_5plus_rate": ("5+ pass rushers", "pct"),
    "box_6minus_vs_run_rate": ("6 or fewer in the box vs run", "pct"),
}  # fmt: skip
SITUATIONS = [("all", "All plays"), ("early_down", "Early downs"), ("third_down", "Third down"),
              ("red_zone", "Red zone")]  # fmt: skip
SITUATION_HELP = {
    "all": "Every play this season.",
    "early_down": "First and second down.",
    "third_down": "Third down only.",
    "red_zone": "Plays inside the opponent's 20.",
}


def pts_toward(x: float | None, home: str, away: str) -> str:
    """'+3.9 pts toward GB' for a contribution in win-probability points (positive = home)."""
    if x is None:
        return "–"
    if abs(x) < 0.05:
        return "0.0 pts"
    return f"{x:+.1f} pts toward {home if x > 0 else away}"


def contribution_items(cm: dict, home_field_label: str = "Home field") -> list[dict]:
    """Chart rows for one model's contribution: home field first, then groups in registry order."""
    order = [g["id"] for g in data.groups()]
    items = [{"id": "home_field", "name": home_field_label, "pp": cm.get("home_field_pp") or 0.0,
              "help": "The built-in edge the home team gets before anything else is considered."}]  # fmt: skip
    for k in sorted(cm.get("groups", {}), key=lambda k: order.index(k) if k in order else 99):
        gd = data.group(k)
        items.append({"id": k, "name": gd["name"], "pp": cm["groups"][k].get("pp") or 0.0,
                      "help": gd.get("description", "")})  # fmt: skip
    return items


def edge_rows(edges: dict, home: str) -> list[dict]:
    """Groups where one team has the edge, biggest first. signed > 0 favors the home team."""
    out = []
    for gid, e in (edges or {}).items():
        if not e.get("favors"):
            continue
        gd = data.group(gid)
        s = float(e["strength_pct"])
        out.append({"id": gid, "name": gd["name"], "help": gd.get("description", ""),
                    "favors": e["favors"], "pct": s,
                    "signed": s if e["favors"] == home else -s,
                    "text": f"{e['favors']} has the {gd['name']} edge, bigger than {s:.0f}% of "
                            "matchups"})  # fmt: skip
    return sorted(out, key=lambda r: -r["pct"])


def feature_unit(feature: str) -> str | None:
    return data.member(feature).get("unit")


def feature_label(feature: str) -> str:
    return data.member(feature).get("label") or feature.split(".", 1)[-1].replace("_", " ")


def tape(features: dict) -> dict[str, list[tuple[str, str, list[dict]]]]:
    """heading -> [(group id, group name, rows)] in registry order; features with no values skipped.

    Row: {label, help, home, away} with values already formatted by the feature's unit."""
    by_group: dict[str, list[dict]] = {}
    for f, d in features.items():
        h, a, gm = d.get("home"), d.get("away"), d.get("game")
        if h is None and a is None and gm is None:
            continue
        unit = feature_unit(f)
        by_group.setdefault(d.get("group") or "other", []).append(
            {
                "label": feature_label(f),
                "help": data.help_text(f),
                "home": data.fmt(h if h is not None else gm, unit),
                "away": data.fmt(a if a is not None else gm, unit),
            }
        )
    out: dict[str, list[tuple[str, str, list[dict]]]] = {}
    seen = set()
    for g in data.groups():
        if g["id"] in by_group:
            out.setdefault(g["heading"], []).append((g["id"], g["name"], by_group[g["id"]]))
            seen.add(g["id"])
    for gid, rows in by_group.items():
        if gid not in seen:
            out.setdefault("Other", []).append((gid, data.group(gid)["name"], rows))
    return out


def feature_contrib_rows(group_contrib: dict) -> list[dict]:
    """Per-feature win-probability points inside a group, biggest first."""
    fs = sorted(group_contrib.get("features", {}).items(), key=lambda kv: -abs(kv[1] or 0))
    return [{"label": feature_label(f), "help": data.help_text(f), "pp": v} for f, v in fs]


# ------------------------------------------------------------------------------------ tendencies


def tendency_lookup(
    rows: list[dict], team_side: str, side: str, metric: str, sit: str
) -> dict | None:
    for r in rows:
        if (r["team_side"], r["side"], r["metric"], r["situation"]) == (
            team_side,
            side,
            metric,
            sit,
        ):
            return r
    return None


def tendency_val(r: dict | None, unit: str) -> str:
    if r is None or r.get("rate") is None:
        return "–"
    return data.fmt(r["rate"], unit)


def tendency_points(rows: list[dict], off_side: str, sit: str) -> list[dict]:
    """Dumbbell rows for `off_side`'s offense vs the other team's defense in one situation.

    Each: label, help, unit, off, def, league (floats or None). Metrics with neither side skipped."""
    def_side = "away" if off_side == "home" else "home"
    out = []
    for label, om, dm, unit, hlp in TENDENCY_PAIRS:
        o = tendency_lookup(rows, off_side, "off", om, sit) if om else None
        d = tendency_lookup(rows, def_side, "def", dm, sit) if dm else None
        if o is None and d is None:
            continue
        lg = (o or d).get("league_rate")
        out.append({"label": label, "help": hlp, "unit": unit, "off": o and o["rate"],
                    "def": d and d["rate"], "league": lg})  # fmt: skip
    return out


def tendency_table(rows: list[dict], off_side: str, sit: str) -> list[dict]:
    """Table for the 'show table' toggle: every metric, with the league average and sample size."""
    def_side = "away" if off_side == "home" else "home"
    out = []
    specs = [(off_side, "off", om, lab, u) for lab, om, _, u, _ in TENDENCY_PAIRS if om]
    specs += [(def_side, "def", dm, lab, u) for lab, _, dm, u, _ in TENDENCY_PAIRS if dm]
    for m, (lab, u) in TENDENCY_EXTRA.items():
        defensive = "rushers" in m or "box" in m
        specs.append(
            (def_side if defensive else off_side, "def" if defensive else "off", m, lab, u)
        )
    for ts, side, m, lab, unit in specs:
        r = tendency_lookup(rows, ts, side, m, sit)
        if r is None:
            continue
        out.append({"Metric": f"{'Offense' if side == 'off' else 'Defense'}: {lab}",
                    "Rate": tendency_val(r, unit), "League": data.fmt(r.get("league_rate"), unit),
                    "Plays": r.get("n")})  # fmt: skip
    return out


# ------------------------------------------------------------------------------------ narrative


def impact_marker(impact: int | None) -> str:
    """Text marker (never color alone): sized by |impact|, direction by sign."""
    i = int(impact or 0)
    if i == 0:
        return "● neutral"
    arrows = "▲" if i > 0 else "▼"
    word = "helps" if i > 0 else "hurts"
    return f"{arrows * min(abs(i), 2)} {word}{' a lot' if abs(i) >= 2 else ''}"


def trend_status(working: bool | None) -> str:
    return "unclear" if working is None else "working" if working else "not working"


def source_links(urls: list[str] | None) -> str:
    """Markdown links 'source 1, source 2' (empty string when none)."""
    return ", ".join(f"[source {i}]({u})" for i, u in enumerate(urls or [], 1))


def note_line(n: dict) -> str:
    link = f" [source]({n['source_url']})" if n.get("source_url") else ""
    return f"**{impact_marker(n.get('impact'))}** ({n.get('kind', 'other')}): {n['text']}{link}"


def trend_line(t: dict) -> str:
    unit = str(t.get("unit", "")).capitalize()
    src = source_links(t.get("sources"))
    return f"**{unit}**: {t['trend']} ({trend_status(t.get('working'))})" + (
        f" {src}" if src else ""
    )


def matchup_notes_sorted(nar: dict) -> list[dict]:
    return sorted(nar.get("matchup_notes") or [], key=lambda n: -(n.get("support") or 0))


def matchup_line(n: dict) -> str:
    k = n.get("support") or len(n.get("sources") or [])
    src = source_links(n.get("sources"))
    return f"{n['text']} ({k} source{'s' if k != 1 else ''}{': ' + src if src else ''})"


def dot_models(models: dict) -> list[str]:
    """Row order: references, ensemble, then the four approaches (global is diagnostic, hidden)."""
    order = ["market_baseline", "elo_v0", "ensemble", *data.APPROACH_ORDER]
    return [m for m in order if m in models and models[m].get("p_home") is not None]


# ------------------------------------------------------------------------------------ html tables


def _esc(t: object) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))  # fmt: skip


def html_table(
    headers: list[str], rows: list[list[str]], helps: list[list[str]] | None = None
) -> str:
    """A small table whose cells can carry hover help (title attr). `helps[i][j]` is cell (i, j)'s
    tooltip ('' for none); a cell with help gets an ⓘ. Text is escaped."""
    th = "text-align:left;padding:3px 8px;border-bottom:1px solid rgba(128,128,128,.4)"
    td = "padding:3px 8px;border-bottom:1px solid rgba(128,128,128,.2)"
    head = "".join(f"<th style='{th}'>{_esc(h)}</th>" for h in headers)
    body = []
    for i, row in enumerate(rows):
        cells = []
        for j, c in enumerate(row):
            tip = helps[i][j] if helps else ""
            tip_attr = f" title='{_esc(tip)}'" if tip else ""
            mark = " <span style='opacity:.5'>ⓘ</span>" if tip else ""
            cells.append(f"<td style='{td}'{tip_attr}>{_esc(c)}{mark}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (f"<div style='overflow-x:auto'><table style='border-collapse:collapse;width:100%'>"
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>")  # fmt: skip
