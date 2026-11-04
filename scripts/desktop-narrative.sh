#!/usr/bin/env bash
# One desktop narrative pass (M6.2u). Windows Task Scheduler runs it in the desktop's WSL on
# Wednesday evening (every game) and Saturday morning (the Sunday and Monday games: games already
# kicked off are skipped); the times are PASSES in src/nfl/llm/narrative.py. Setup: docs/runbook.md.
#   1. update the checkout and the schedule/lines data the research step reads
#   2. research every upcoming game of the week on the desktop models
#   3. upload the records to the data bucket and rebuild the site (cloud job nfl-site)
# Any failure writes an ERROR to Cloud Logging (log nfl-desktop-narrative), which emails Austin
# (infra/alerts.tf). A pass that never runs is caught by the nfl-narrative-check job before each lock.
set -uo pipefail
cd "$(dirname "$0")/.."

PROJECT="${GCP_PROJECT:-nfl-project-prod}"
REGION="${GCP_REGION:-us-central1}"
BUCKET="gs://${PROJECT}-data"
LOGDIR="data/raw/narrative_local/passes"
mkdir -p "$LOGDIR"
exec > >(tee -a "$LOGDIR/$(date -u +%Y%m%dT%H%M%SZ).log") 2>&1

log() {  # severity, message: to Cloud Logging and this run's log file
  echo "[$1] $2"
  gcloud logging write nfl-desktop-narrative "$2" --severity="$1" --project="$PROJECT" >/dev/null ||
    echo "(could not write to Cloud Logging)"
}
fail() { log ERROR "desktop narrative pass failed: $1 (log: $LOGDIR on the desktop)"; exit 1; }

git pull -q --ff-only origin main || fail "git pull"
uv sync -q || fail "uv sync"
for t in games lines; do
  gcloud storage rsync -r "$BUCKET/curated/$t" "data/curated/$t" -q || fail "download curated/$t"
done

read -r season week < <(uv run nfl narrative week) || fail "no upcoming week in the schedule"
wk=$(printf '%02d' "$week")
log INFO "desktop narrative pass started: $season week $week"

uv run nfl narrative run "$season" "$week"
status=$?

# Upload whatever was stored, even if some games failed; never delete anything in the bucket.
dir="marts/narrative/season=$season/week=$wk"
if [ -d "data/$dir" ]; then
  gcloud storage rsync -r "data/$dir" "$BUCKET/$dir" -q || fail "upload $dir"
fi
gcloud run jobs execute nfl-site --region "$REGION" --project "$PROJECT" --async -q ||
  fail "starting the site rebuild"

[ "$status" -eq 0 ] || fail "some games failed in $season week $week (the rest were uploaded)"
log INFO "desktop narrative pass done: $season week $week"
