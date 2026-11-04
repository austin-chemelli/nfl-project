#!/usr/bin/env bash
# Claude Code SessionStart hook (registered in .claude/settings.json): put the project's current
# state in front of every chat, so no session starts uninformed (docs/state-maintenance.md).
# Prints to stdout, which Claude Code adds to the conversation's context.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
[ -f docs/state.md ] || exit 0

echo "# Project state (docs/state.md, injected by scripts/hooks/session-start.sh). Keep it current: docs/state-maintenance.md."
echo
cat docs/state.md
echo
echo "# Live board (.notes/board.md: who is doing what right now; add your row when a track starts)"
echo
if [ -f .notes/board.md ]; then cat .notes/board.md; else echo "(no board file yet)"; fi
echo
echo "# Last two journal entries (docs/journal.md)"
echo
start=$(grep -n '^## ' docs/journal.md | tail -2 | head -1 | cut -d: -f1)
if [ -n "$start" ]; then tail -n "+$start" docs/journal.md | head -150; fi
echo
echo "# state_check (scripts/state_check.py; fix ERRORs the first time you touch docs this session)"
echo
python3 scripts/state_check.py 2>&1 || true
