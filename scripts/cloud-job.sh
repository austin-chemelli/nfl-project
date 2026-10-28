#!/usr/bin/env bash
# Entry point for Cloud Run Jobs (docs/hosting.md §2). Usage: cloud-job.sh <job> [args]
#   refresh          nfl weekly refresh, then publish the site JSON
#   lock <slot>      clone the repo, nfl lock --slot <slot> --commit --push, publish site + lock files
#   odds             nfl odds snapshot, rebuild site JSON, publish
# Environment: NFL_DATA_ROOT (bucket mount), NFL_SITE_ROOT (public bucket mount, optional),
#   ODDS_API_KEY, GITHUB_DEPLOY_KEY_FILE (lock only), NFL_IMAGE_SHA (set at image build), NFL_REPO.
set -euo pipefail

job="${1:?job name}"; shift || true
repo_url="${NFL_REPO:-git@github.com:austin-chemelli/nfl-project.git}"
site_root="${NFL_SITE_ROOT:-}"

publish() {
  # Copy site JSON (and lock artifacts, if a repo clone is given) to the public bucket mount.
  [ -n "$site_root" ] || { echo "publish: NFL_SITE_ROOT unset, skipping"; return; }
  mkdir -p "$site_root/site"
  cp "$NFL_DATA_ROOT"/marts/site/*.json "$site_root/site/"
  if [ -n "${1:-}" ] && [ -d "$1/public/predictions" ]; then
    mkdir -p "$site_root/predictions"
    cp -r "$1"/public/predictions/. "$site_root/predictions/"
  fi
  echo "publish: $(ls "$site_root/site" | wc -l) site files -> $site_root"
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
  local head; head="$(git -C /tmp/repo rev-parse --short HEAD)"
  case "${NFL_IMAGE_SHA:-$head}" in
    "$head"*) ;;
    *) echo "refusing: repo main is at $head but this image was built from $NFL_IMAGE_SHA" >&2
       echo "(the image workflow has not caught up with the last push; rerun after it finishes)" >&2
       exit 3 ;;
  esac
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
  *)
    echo "unknown job: $job" >&2; exit 2 ;;
esac
