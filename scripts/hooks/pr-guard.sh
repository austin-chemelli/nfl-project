#!/usr/bin/env bash
# Claude Code PreToolUse hook on Bash. Before `gh pr create` or `git push`, two things must hold
# (docs/state-maintenance.md):
#   1. a branch that changes code (src/ web/ infra/ scripts/ tests/) also changes docs/journal.md
#      or docs/state.md, unless the command carries the label docs-not-needed;
#   2. scripts/state_check.py --strict passes (the hub is internally consistent).
# Exit 2 blocks the command and shows stderr to Claude; anything else lets it run.
# Lock pushes from the primary checkout are on main and skip rule 1; rule 2 still applies.
#
# Registered in the repo's .claude/settings.json and in ~/dev/.claude/settings.json (Austin's VS
# Code workspace is ~/dev; scripts/hooks/dev-folder-settings.json). The checkout to inspect is
# the one the session's cwd (stdin JSON) is in; a command run outside any checkout is let through.
input=$(cat)
read -r cwd cmd < <(printf '%s' "$input" | python3 -c '
import sys, json
d = json.load(sys.stdin)
print(d.get("cwd", ""), json.dumps(d.get("tool_input", {}).get("command", "")))
' 2>/dev/null)
cmd=$(printf '%s' "$cmd" | python3 -c 'import sys, json; print(json.load(sys.stdin))' 2>/dev/null)
echo "$(date -Is) ${0##*/} cmd=${cmd:0:40} cwd=${cwd:-?} project=${CLAUDE_PROJECT_DIR:-?}" >> "$HOME/.claude/nfl-hooks.log" 2>/dev/null
case "$cmd" in
  *"gh pr create"*|*"git push"*) ;;
  *) exit 0 ;;
esac
case "$cmd" in *"--delete"*|*"docs-not-needed"*) exit 0 ;; esac

# A `cd <dir> && ...` at the start of the command moves the checkout the command acts on.
case "$cmd" in
  "cd "*) target=$(printf '%s' "$cmd" | sed -E 's/^cd +("?)([^ ;&|"]+)\1.*/\2/'); [ -d "$target" ] && cwd="$target" ;;
esac
root=$(cd "${cwd:-.}" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)
[ -n "$root" ] && [ -f "$root/docs/state.md" ] || exit 0
cd "$root" || exit 0

msgs=""
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ -n "$branch" ] && [ "$branch" != "main" ]; then
  base=$(git merge-base origin/main HEAD 2>/dev/null)
  if [ -n "$base" ]; then
    files=$(git diff --name-only "$base" HEAD)
    if grep -qE '^(src|web|infra|scripts|tests)/' <<<"$files" && ! grep -qE '^docs/(journal|state)\.md$' <<<"$files"; then
      msgs+="Blocked: this branch changes code but neither docs/journal.md nor docs/state.md. Do the checkpoint in docs/state-maintenance.md (journal entry, hub rows), commit, then retry. If there is truly nothing to record, add --label docs-not-needed to gh pr create."$'\n'
    fi
  fi
fi
check=$(python3 scripts/state_check.py --strict 2>&1) || msgs+="Blocked: scripts/state_check.py found errors in docs/state.md ($root); fix them, commit, then retry:"$'\n'"$check"$'\n'

if [ -n "$msgs" ]; then
  printf '%s' "$msgs" >&2
  exit 2
fi
exit 0
