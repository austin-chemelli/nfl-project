"""Narrative evals (M6.2e): compare records of the same game from different producers, prompt
versions or models. `compare_records` gives one markdown report: a metrics table (counts, source
support, drops, time, tokens) and the texts side by side for reading. Judging errors (wrong facts,
pairing mistakes, contradictions) stays a human read of the texts.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def _label(path: Path, rec: dict) -> str:
    tag = path.parent.name if "experiments" in path.parts else rec.get("prompt_version", "?")
    return f"{rec['producer']}/{tag}"


def _summary(path: Path) -> dict:
    """The run summary next to a draft (experiments write one per draft; live runs one per run)."""
    s = path.with_name(path.name.removesuffix(".json") + ".summary.json")
    return json.loads(s.read_text()) if s.exists() else {}


def _kinds(notes: list[dict]) -> str:
    c = Counter(n["kind"] for n in notes)
    return ", ".join(f"{k} {v}" for k, v in c.most_common()) or "-"


def metrics(path: Path) -> dict:
    rec = json.loads(path.read_text())
    s = _summary(path)
    row = {"record": _label(path, rec), "model": rec["model"]}
    for side in ("away", "home"):
        t = rec[side]
        team = t["team"]
        row[f"{team} QB"] = f"{t['qb_name']} ({t['qb_status']})"
        row[f"{team} notes"] = f"{len(t['notes'])}: {_kinds(t['notes'])}"
        multi = sum(len(x["sources"]) > 1 for x in t["scheme_trends"])
        row[f"{team} trends (2+ sources)"] = f"{len(t['scheme_trends'])} ({multi})"
        row[f"{team} absences"] = str(len(t["key_absences"]))
        row[f"{team} injury / motivation"] = f"{t['injury_impact']} / {t['motivation']}"
    row["matchup notes (support)"] = f"{len(rec['matchup_notes'])} ({', '.join(str(m['support']) for m in rec['matchup_notes'])})"  # fmt: skip
    row["claims"] = str(len(rec["claims"]))
    row["minutes"] = f"{s['seconds'] / 60:.1f}" if "seconds" in s else "-"
    row["output tokens"] = str(s.get("output_tokens", "-"))
    row["dropped"] = str(sum(s.get("dropped", {}).values())) if s else "-"
    row["re-cited"] = str(sum(s.get("recited", {}).values())) if s else "-"
    return row


def _texts(path: Path) -> list[str]:
    rec = json.loads(path.read_text())
    out = [f"### {_label(path, rec)} ({rec['model']})", "", f"**Consensus.** {rec['consensus_narrative']}", ""]  # fmt: skip
    for side in ("away", "home"):
        t = rec[side]
        out += [f"**{t['team']} summary.** {t['summary']}", ""]
        out += [f"- {n['kind']} {n['impact']:+d}: {n['text']}" for n in t["notes"]]
        out += [f"- trend ({x['unit']}, {'works' if x['working'] else 'not working' if x['working'] is False else '?'}, {len(x['sources'])} src): {x['trend']}" for x in t["scheme_trends"]]  # fmt: skip
        out.append("")
    out.append("**Matchup notes.**")
    out += [f"- ({m['support']}) {m['text']}" for m in rec["matchup_notes"]] or ["- none"]
    return [*out, ""]


def compare_records(paths: list[Path]) -> str:
    rows = [metrics(p) for p in paths]
    keys = list(dict.fromkeys(k for r in rows for k in r))
    lines = ["| | " + " | ".join(r["record"] for r in rows) + " |", "|---|" + "---|" * len(rows)]
    for k in keys[1:]:
        lines.append(f"| {k} | " + " | ".join(r.get(k, "-") for r in rows) + " |")
    out = [f"# Narrative comparison: {json.loads(paths[0].read_text())['game_id']}", "", *lines, ""]
    for p in paths:
        out += _texts(p)
    return "\n".join(out)
