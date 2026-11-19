#!/usr/bin/env bash
# Set up the desktop for narrative passes on headless Claude Code (ADR 0030). Run it in the
# desktop's WSL Ubuntu, in ~/dev/nfl-project. Idempotent: rerun it any time; it only says what is
# missing and installs what it can.
#
#   scripts/desktop-setup.sh                 check everything, install the systemd units (timer off)
#   scripts/desktop-setup.sh --test-game ID  also research one game now, without storing it
#   scripts/desktop-setup.sh --enable        turn the timer on and the old Windows task off (the switch)
#   scripts/desktop-setup.sh --disable       the reverse: timer off, Windows task back on
#
# What it can't do for you (it says so when it finds them missing): log in to Claude Code
# (`claude`, then /login with the Max account), log in to gcloud, turn on systemd in WSL.
set -u
cd "$(dirname "$0")/.."
repo=$(pwd)
mode=check
game=""
case "${1:-}" in
  --enable) mode=enable ;;
  --disable) mode=disable ;;
  --test-game) mode=test; game=${2:?--test-game needs a game id, e.g. 2026_12_BUF_KC} ;;
  "") ;;
  *) echo "usage: desktop-setup.sh [--test-game <game_id> | --enable | --disable]"; exit 2 ;;
esac

missing=0
ok() { echo "  ok    $*"; }
need() { echo "  NEED  $*"; missing=$((missing + 1)); }
note() { echo "  note  $*"; }
step() { echo; echo "$*"; }
schtasks=/mnt/c/Windows/System32/schtasks.exe

step "1. WSL with systemd"
if [ -d /run/systemd/system ] && systemctl --user show-environment >/dev/null 2>&1; then
  ok "systemd is running (user units work)"
else
  need "systemd is off. Run: sudo sh -c 'printf \"[boot]\\nsystemd=true\\n\" >> /etc/wsl.conf', then in PowerShell: wsl --shutdown, then open Ubuntu again"
fi
if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" = yes ]; then
  ok "lingering on (timers run with no terminal open)"
else
  note "turning on lingering (asks for your Ubuntu password)"
  sudo loginctl enable-linger "$USER" && ok "lingering on" || need "sudo loginctl enable-linger $USER failed"
fi
if [ -x "$schtasks" ] && "$schtasks" /query /tn "JobSearch WSL" >/dev/null 2>&1; then
  ok "Windows task 'JobSearch WSL' keeps WSL running from sign-in (job-search's; shared)"
else
  need "nothing keeps WSL running after sign-in: see docs/runbook.md, 'Narrative on the desktop', step 2"
fi

step "2. The checkout and its tools"
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
[ "$branch" = main ] && ok "checkout $repo on main" || need "checkout is on '${branch:-?}', not main (git switch main)"
command -v uv >/dev/null && ok "uv $(uv --version 2>/dev/null | cut -d' ' -f2)" || need "uv is not installed"
if command -v gcloud >/dev/null && gcloud storage ls "gs://${GCP_PROJECT:-nfl-project-prod}-data/curated/" >/dev/null 2>&1; then
  ok "gcloud can read the data bucket"
else
  need "gcloud can't read gs://${GCP_PROJECT:-nfl-project-prod}-data (gcloud auth login; the same account the old pass used)"
fi

step "3. Claude Code on the Max login (never an API key)"
for v in ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN CLAUDE_CODE_OAUTH_TOKEN; do
  [ -n "${!v:-}" ] && note "$v is set in this shell; the pass unsets it, but remove it from your profile"
done
if ! command -v claude >/dev/null; then
  need "Claude Code is not installed: curl -fsSL https://claude.ai/install.sh | bash, then claude and /login"
else
  ok "claude $(claude --version 2>/dev/null | cut -d' ' -f1)"
  st=$(env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u CLAUDE_CODE_OAUTH_TOKEN timeout 60 claude auth status --json 2>/dev/null)
  case "$(printf '%s' "$st" | python3 -c 'import json,sys
try: d=json.load(sys.stdin)
except ValueError: print("bad"); sys.exit()
print("ok" if d.get("loggedIn") and d.get("authMethod")=="claude.ai" else "out" if not d.get("loggedIn") else "method")')" in
    ok) ok "logged in to claude.ai" ;;
    out) need "Claude is not logged in: run claude, then /login with the Max account" ;;
    method) need "Claude is signed in with an API key or token, not claude.ai: remove it, then claude /login" ;;
    *) need "claude auth status did not answer (update Claude Code: claude update)" ;;
  esac
fi

step "4. The systemd units"
unitdir=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
if [ "$missing" = 0 ]; then  # only on a machine that passed every check above (the desktop)
  mkdir -p "$unitdir"
  changed=0
  for u in nfl-narrative.service nfl-narrative.timer; do
    if ! cmp -s "deploy/$u" "$unitdir/$u"; then cp "deploy/$u" "$unitdir/$u"; changed=1; fi
  done
  [ "$changed" = 1 ] && systemctl --user daemon-reload 2>/dev/null
  ok "units installed in $unitdir"
else
  note "units not installed: fix the NEED lines first"
fi
if systemctl --user is-enabled nfl-narrative.timer >/dev/null 2>&1; then
  ok "timer on: $(systemctl --user list-timers nfl-narrative.timer --no-legend 2>/dev/null | awk '{print $1, $2, $3}') next"
else
  note "timer off (scripts/desktop-setup.sh --enable turns it on)"
fi
if [ -x "$schtasks" ] && "$schtasks" /query /tn nfl-narrative >/dev/null 2>&1; then
  state=$("$schtasks" /query /tn nfl-narrative /fo csv /nh 2>/dev/null | tr -d '\r' | awk -F'","' '{print $3}' | tr -d '"')
  note "Windows task nfl-narrative (the local model) is ${state:-present}"
fi

step "5. A dry run of the pass (checks only, nothing researched or uploaded)"
if [ "$missing" = 0 ]; then
  NARRATIVE_PRODUCER=claude bash scripts/desktop-narrative.sh --dry-run | sed 's/^/  /' || missing=$((missing + 1))
else
  note "skipped: fix the NEED lines first"
fi

case "$mode" in
  test)
    step "6. One game researched now, not stored (about 3 minutes)"
    [ "$missing" = 0 ] || { echo "  fix the NEED lines first"; exit 1; }
    season=$(cut -d_ -f1 <<<"$game"); week=$((10#$(cut -d_ -f2 <<<"$game")))
    env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u CLAUDE_CODE_OAUTH_TOKEN \
      uv run nfl narrative claude "$season" "$week" "$game" --no-store | sed 's/^/  /'
    ;;
  enable)
    step "6. Switch: the timer on, the Windows task off"
    [ "$missing" = 0 ] || { echo "  fix the NEED lines first"; exit 1; }
    systemctl --user enable --now nfl-narrative.timer && ok "timer on"
    if [ -x "$schtasks" ] && "$schtasks" /query /tn nfl-narrative >/dev/null 2>&1; then
      "$schtasks" /change /tn nfl-narrative /disable >/dev/null && ok "Windows task nfl-narrative disabled" ||
        need "could not disable the Windows task: in PowerShell, Disable-ScheduledTask -TaskName nfl-narrative"
    fi
    systemctl --user list-timers nfl-narrative.timer --no-legend | sed 's/^/  next: /'
    ;;
  disable)
    step "6. Back: the timer off, the Windows task on"
    systemctl --user disable --now nfl-narrative.timer 2>/dev/null; ok "timer off"
    if [ -x "$schtasks" ]; then
      "$schtasks" /change /tn nfl-narrative /enable >/dev/null && ok "Windows task nfl-narrative enabled" ||
        need "could not enable the Windows task: in PowerShell, Enable-ScheduledTask -TaskName nfl-narrative"
    fi
    ;;
esac

echo
if [ "$missing" = 0 ]; then echo "All set."; else echo "$missing thing(s) to fix (NEED lines above); then run this again."; exit 1; fi
