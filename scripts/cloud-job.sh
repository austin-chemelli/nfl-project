#!/usr/bin/env bash
# Entry point for Cloud Run Jobs (docs/hosting.md §2). Usage: cloud-job.sh <job> [args]
#   refresh          nfl weekly refresh, then publish the site JSON
#   lock <slot>      clone the repo, nfl lock --slot <slot> --commit --push, publish site + lock files
#   odds             nfl odds snapshot, rebuild site JSON, publish
#   retro            nfl retro daily (current-season ingest, curate, game retros + recaps), publish
# Environment: NFL_DATA_ROOT (bucket mount), NFL_SITE_BUCKET (public bucket name, optional),
#   ODDS_API_KEY, GITHUB_DEPLOY_KEY_FILE (lock only), NFL_IMAGE_SHA (set at image build), NFL_REPO.
set -euo pipefail

job="${1:?job name}"; shift || true
repo_url="${NFL_REPO:-git@github.com:austin-chemelli/nfl-project.git}"

publish() {
  # Upload site JSON (and lock artifacts, if a repo clone is given) to the public bucket with a
  # 5-minute cache (nfl publish). Skipped when NFL_SITE_BUCKET is unset (local runs).
  [ -n "${NFL_SITE_BUCKET:-}" ] || { echo "publish: NFL_SITE_BUCKET unset, skipping"; return; }
  nfl publish --bucket "$NFL_SITE_BUCKET" ${1:+--repo "$1"}
}

clone_repo() {
  # Shallow clone at main with the deploy key; refuse to run code the image wasn't built from.
  local key="${GITHUB_DEPLOY_KEY_FILE:?deploy key file}"
  mkdir -p /tmp/ssh && cp "$key" /tmp/ssh/id && chmod 600 /tmp/ssh/id
  ssh-keyscan -t ed25519 github.com > /tmp/ssh/known_hosts 2>/dev/null
  export GIT_SSH_COMMAND="ssh -i /tmp/ssh/id -o IdentitiesOnly=yes -o UserKnownHostsFile=/tmp/ssh/known_hosts"
  rm -rf /tmp/repo
  git clone -q --depth 50 --branch main "$repo_url" /tmp/repo
  git -C /tmp/repo config user.name "nfl-jobs"
  git -C /tmp/repo config user.email "nfl-jobs@users.noreply.github.com"
  check_image_matches /tmp/repo
}

check_image_matches() {
  # The image must hold the code main runs: refuse if job code changed after the commit the
  # image was built from (the paths that trigger an image rebuild in ci.yml). Commits that don't
  # touch code (lock artifacts, docs, the web app) leave the image valid; the old check demanded
  # HEAD == image commit, so Saturday's lock would have refused after Thursday's lock commit.
  local repo="$1" img="${NFL_IMAGE_SHA:-unknown}"
  [ "$img" != unknown ] || return 0
  if ! git -C "$repo" cat-file -e "${img}^{commit}" 2>/dev/null; then
    echo "refusing: the image's commit $img is not in main's recent history" >&2
    exit 3
  fi
  if ! git -C "$repo" diff --quiet "$img" HEAD -- src scripts pyproject.toml uv.lock Dockerfile .dockerignore; then
    echo "refusing: job code on main changed since the image was built from $img" >&2
    echo "(the image workflow has not caught up with the last push; rerun after it finishes)" >&2
    exit 3
  fi
}

case "$job" in
  refresh)
    nfl weekly refresh "$@"
    publish
    ;;
  lock)
    slot="${1:?slot}"; shift
    clone_repo
    cd /tmp/repo
    nfl lock --slot "$slot" --commit --push "$@"
    publish /tmp/repo
    ;;
  odds)
    nfl odds snapshot "$@"
    nfl site
    publish
    ;;
  retro)
    nfl retro daily "$@"
    publish
    ;;
  *)
    echo "unknown job: $job" >&2; exit 2 ;;
esac
