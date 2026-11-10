#!/usr/bin/env bash
# Claude Code SessionStart hook: put the project's current state in front of every chat, so no
# session starts uninformed (docs/state-maintenance.md). Prints to stdout, which Claude Code adds
# to the conversation's context.
#
# Registered twice: in the repo's .claude/settings.json (sessions started inside a checkout) and in
# ~/dev/.claude/settings.json (Austin's VS Code workspace is ~/dev, so most sessions start there;
# scripts/hooks/dev-folder-settings.json is that file). Which checkout to read: the session's cwd
# if it is inside one (stdin JSON), else $CLAUDE_PROJECT_DIR, else the primary checkout.
input=$(cat 2>/dev/null)
cwd=$(printf '%s' "$input" | python3 -c 'import sys, json; print(json.load(sys.stdin).get("cwd", ""))' 2>/dev/null)
PRIMARY="$HOME/dev/nfl-project"
# One line per run in ~/.claude/nfl-hooks.log, so "did the hook fire?" has an answer.
echo "$(date -Is) ${0##*/} cwd=${cwd:-?} project=${CLAUDE_PROJECT_DIR:-?}" >> "$HOME/.claude/nfl-hooks.log" 2>/dev/null

root=""
for candidate in "$cwd" "${CLAUDE_PROJECT_DIR:-}"; do
  [ -n "$candidate" ] || continue
  top=$(cd "$candidate" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)
  if [ -n "$top" ] && [ -f "$top/docs/state.md" ]; then root="$top"; break; fi
done
note=""
if [ -z "$root" ]; then
  [ -f "$PRIMARY/docs/state.md" ] || exit 0
  root="$PRIMARY"
  note="(This session started outside a checkout, so this is main's copy from $PRIMARY. Work in a worktree: CLAUDE.md, Parallel work. If this session is about another project, ignore this block.)"
fi
cd "$root" || exit 0

# Keep this short (journal 2026-11-09): the full state.md, board prose and journal tail ran ~37 KB per
# session. Inject the parts that change what a chat does first; everything else is one Read away.
echo "# Project state: a digest of docs/state.md in $root (scripts/hooks/session-start.sh)."
echo "Read docs/state.md in full before changing code or docs. Keep it current: docs/state-maintenance.md."
[ -n "$note" ] && echo "$note"
echo
# The bottom line, up to the next section.
awk '/^## Bottom line/{on=1} on&&/^## /&&!/^## Bottom line/{exit} on' docs/state.md
echo "## Waiting on Austin (open rows of the Open decisions table)"
echo
awk '/^## Open decisions/{on=1;next} on&&/^## /{exit} on&&/^\|/&&!/decided/' docs/state.md
echo
# The live layer: one track file per thread in .notes/hub/tracks/ (the hub, ~/dev/hub, shows them).
# Print every track in one line each, then this checkout's own track file in full, then the rules.
python3 - "$root" <<'PY' 2>/dev/null || echo "(could not read .notes/hub/tracks)"
import datetime as dt, os, re, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
tracks = root / ".notes/hub/tracks"
branch = subprocess.run(["git", "-C", str(root), "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
def fm(text):
    m = re.match(r"\A---\s*\n(.*?)\n---", text, re.S)
    out = {}
    for line in (m.group(1) if m else "").splitlines():
        k = re.match(r"^(\w+):\s*(.*)$", line)
        if k:
            out[k.group(1)] = k.group(2).strip().strip("\"'`")
    return out
print("# Hub tracks (.notes/hub/tracks/; Board: http://localhost:8765/nfl-project/)")
print()
mine = None
files = sorted(tracks.glob("*.md")) if tracks.is_dir() else []
for f in files:
    m = fm(f.read_text(errors="replace"))
    age = dt.datetime.now() - dt.datetime.fromtimestamp(f.stat().st_mtime)
    h = int(age.total_seconds() // 3600)
    print(f"- {f.stem}: {m.get('status', '?')} · {m.get('branch', '-')} · {m.get('step', '')} (updated {h} h ago)")
    wt = os.path.expanduser(m.get("worktree", ""))
    if (m.get("branch") and m.get("branch") == branch) or (wt and Path(wt) == root):
        mine = f
if not files:
    print("(no track files yet)")
print()
if mine is not None:
    print(f"# Your track file: {mine} (yours alone; keep it current)")
    print()
    print(mine.read_text(errors="replace").strip())
elif branch and branch != "main":
    print(f"# No track file for branch {branch}: create .notes/hub/tracks/<track>.md before you change anything (format: ~/dev/hub/README.md).")
print()
print("""# Hub rules (~/dev/CLAUDE.md, Hub)
- Update your own track file (status, step, pr, needs_you, waiting_on) when the track starts, at each step, when you open a PR and when you stop. A Stop hook blocks the turn end if you changed files without updating it. Never edit another thread's track file; cross-track changes go through the master thread (project.md).
- Plans, breakdowns and decision briefs go to .notes/hub/plans/<slug>.md (status: proposed; a "## Decisions" section with one "### " item per decision, each with Options, Recommendation and Status: open|decided). Link Austin to http://localhost:8765/nfl-project/plans/<slug>#decisions instead of pasting the plan into the chat.
- PR and CI state come from gh; don't copy them by hand beyond the pr number.""")
PY
echo
echo "# Latest journal headings (docs/journal.md)"
grep '^## ' docs/journal.md | tail -3
echo
echo "# state_check (scripts/state_check.py; fix ERRORs the first time you touch docs this session)"
echo
python3 scripts/state_check.py 2>&1 || true
