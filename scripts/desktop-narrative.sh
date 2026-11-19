#!/usr/bin/env bash
# One desktop narrative pass. Runs in the desktop's WSL on Wednesday evening (every game) and
# Saturday morning (the Sunday and Monday games: games already kicked off are skipped); the times
# are PASSES in src/nfl/llm/narrative.py. Setup: docs/runbook.md, "Narrative on the desktop".
#   1. update the checkout and the schedule, lines, rosters and depth charts the research reads
#   2. research every upcoming game of the week
#   3. upload the records to the data bucket and rebuild the site (cloud job nfl-site)
#
# Producer (--producer, or NARRATIVE_PRODUCER):
#   claude  headless Claude Code on Austin's Max login (ADR 0030; the nfl-narrative.timer systemd
#           unit). Every API-key variable is unset and the pass refuses unless `claude auth status`
#           reports a claude.ai login; a login expiring within 3 days logs a WARNING.
#   local   the open-weight model on Ollama (ADR 0014; the Windows Task Scheduler task). Default
#           until the switch-over, so the existing task runs unchanged.
# --dry-run: every check (checkout, login, the week), no research, nothing uploaded or logged.
#
# Any failure writes an ERROR to Cloud Logging (log nfl-desktop-narrative), which emails Austin
# (infra/alerts.tf). A pass that never runs is caught by the nfl-narrative-check job before each lock.
set -uo pipefail
cd "$(dirname "$0")/.."

producer=${NARRATIVE_PRODUCER:-local}
dry=0
while [ $# -gt 0 ]; do
  case "$1" in
    --producer) producer=${2:?--producer needs claude or local}; shift 2 ;;
    --dry-run) dry=1; shift ;;
    *) echo "usage: desktop-narrative.sh [--producer claude|local] [--dry-run]"; exit 2 ;;
  esac
done
case "$producer" in claude|local) ;; *) echo "unknown producer '$producer'"; exit 2 ;; esac

PROJECT="${GCP_PROJECT:-nfl-project-prod}"
REGION="${GCP_REGION:-us-central1}"
BUCKET="gs://${PROJECT}-data"
LOGDIR="data/raw/narrative_claude/passes"
[ "$producer" = local ] && LOGDIR="data/raw/narrative_local/passes"
mkdir -p "$LOGDIR"
if [ "$dry" = 0 ]; then
  exec > >(tee -a "$LOGDIR/$(date -u +%Y%m%dT%H%M%SZ).log") 2>&1
fi

log() {  # severity, message: to Cloud Logging and this run's log file
  echo "[$1] $2"
  [ "$dry" = 1 ] && return 0
  gcloud logging write nfl-desktop-narrative "$2" --severity="$1" --project="$PROJECT" >/dev/null ||
    echo "(could not write to Cloud Logging)"
}
fail() { log ERROR "desktop narrative pass failed: $1 (log: $LOGDIR on the desktop)"; exit 1; }

# One pass at a time (a timer catch-up and a hand run must not overlap).
mkdir -p "${XDG_STATE_HOME:-$HOME/.local/state}/nfl-narrative"
exec 9>"${XDG_STATE_HOME:-$HOME/.local/state}/nfl-narrative/pass.lock"
flock -n 9 || { echo "another narrative pass is running; nothing to do"; exit 0; }

if [ "$dry" = 0 ]; then
  # This clone only runs passes, so it follows main exactly. A local edit used to stop the pass
  # (2026-11-04); now it is saved next to the logs and dropped, with a warning.
  out=$(git fetch -q origin main 2>&1) || fail "git fetch: $(tail -1 <<<"$out")"
  if ! git diff --quiet HEAD; then
    patch="$LOGDIR/local-edits-$(date -u +%Y%m%dT%H%M%SZ).patch"
    git diff HEAD >"$patch"
    log WARNING "desktop checkout had local edits to $(git diff --name-only HEAD | tr '\n' ' '); saved to $patch"
  fi
  out=$(git reset -q --hard origin/main 2>&1) || fail "git reset: $(tail -1 <<<"$out")"
  uv sync -q || fail "uv sync"
  for t in games lines rosters_weekly; do
    gcloud storage rsync -r "$BUCKET/curated/$t" "data/curated/$t" -q || fail "download curated/$t"
  done
fi

if [ "$producer" = claude ]; then
  unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN CLAUDE_CODE_OAUTH_TOKEN ANTHROPIC_BASE_URL \
    CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX CLAUDE_CODE_USE_FOUNDRY
  command -v claude >/dev/null || fail "Claude Code is not installed on the desktop (no 'claude' on PATH)"
  login=$(timeout 60 claude auth status --json 2>/dev/null | python3 -c '
import json, sys
from datetime import datetime, timezone
try:
    d = json.load(sys.stdin)
except ValueError:
    print("bad"); sys.exit()
if not d.get("loggedIn"):
    print("out"); sys.exit()
if d.get("authMethod") != "claude.ai":
    print("method " + str(d.get("authMethod"))); sys.exit()
days = ""
if d.get("loginExpiresAt"):
    left = datetime.fromisoformat(d["loginExpiresAt"].replace("Z", "+00:00")) - datetime.now(timezone.utc)
    days = str(max(0, int(left.total_seconds() // 86400)))
print("ok " + str(d.get("subscriptionType") or "?") + " " + days)
')
  case "$login" in
    ok*) ;;
    out) fail "Claude is not logged in on the desktop: open Ubuntu there, run claude, then /login with the Max account" ;;
    method*) fail "Claude is signed in with '${login#method }', not the claude.ai Max login (an API key would bill the API): remove it, then claude /login" ;;
    *) fail "claude auth status did not answer; is Claude Code installed and up to date?" ;;
  esac
  read -r _ plan days_left <<<"$login"
  echo "claude.ai login ok (plan $plan${days_left:+, expires in $days_left days})"
  if [ -n "${days_left:-}" ] && [ "$days_left" -le 3 ]; then
    log WARNING "the Claude login on the desktop expires in $days_left day(s): open Ubuntu there, run claude, then /login"
  fi
fi

read -r season week < <(uv run nfl narrative week) || fail "no upcoming week in the schedule"
wk=$(printf '%02d' "$week")
if [ "$dry" = 0 ]; then  # the projected QB in the research input is the depth chart's QB1
  gcloud storage rsync -r "$BUCKET/curated/depth_charts/season=$season" "data/curated/depth_charts/season=$season" -q ||
    log WARNING "could not download curated/depth_charts: the research gets the schedule's QB names"
fi
if [ "$dry" = 1 ]; then
  echo "--dry-run: checks passed; would research $season week $week with producer $producer"
  exit 0
fi
log INFO "desktop narrative pass started: $season week $week ($producer)"

result=$(mktemp)
if [ "$producer" = claude ]; then
  uv run nfl narrative claude "$season" "$week" 2>&1 | tee "$result"
else
  uv run nfl narrative run "$season" "$week" 2>&1 | tee "$result"
fi
status=${PIPESTATUS[0]}

# Upload whatever was stored, even if some games failed; never delete anything in the bucket.
dir="marts/narrative/season=$season/week=$wk"
if [ -d "data/$dir" ]; then
  gcloud storage rsync -r "data/$dir" "$BUCKET/$dir" -q || fail "upload $dir"
fi
gcloud run jobs execute nfl-site --region "$REGION" --project "$PROJECT" --async -q ||
  fail "starting the site rebuild"

if [ "$status" -ne 0 ]; then
  detail=$(grep '^FAILED ' "$result" | cut -c8- | head -8 | tr '\n' ';' | cut -c1-1200)
  fail "some games failed in $season week $week (the rest were uploaded; rerunning this script resumes): ${detail:-$(tail -1 "$result" | cut -c1-300)}"
fi
log INFO "desktop narrative pass done: $season week $week ($producer)"
