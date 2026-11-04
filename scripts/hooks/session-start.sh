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

echo "# Project state (docs/state.md in $root, injected by scripts/hooks/session-start.sh). Keep it current: docs/state-maintenance.md."
[ -n "$note" ] && echo "$note"
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
