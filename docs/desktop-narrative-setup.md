# Desktop setup: narrative passes on Claude Code

Status: current, written 2026-11-19 for the switch (ADR 0030, M6.8). Everything here runs on the **desktop**, in its **WSL Ubuntu** terminal, in the checkout `~/dev/nfl-project`. Background and day-to-day operation: [runbook.md](runbook.md), "Narrative on the desktop".

**What you end up with:** a systemd timer in WSL that runs a narrative pass on Wednesday 18:00 and Saturday 07:00 Eastern, using Claude Code on your Max login (never an API key). Each pass researches every game not yet kicked off (about 15 minutes), uploads the records and rebuilds the site. The old Windows task `nfl-narrative` (the local model) is switched off.

## Steps

1. **Get the code.**
   ```
   cd ~/dev/nfl-project
   git switch main && git pull --ff-only
   ```
   Check: `ls scripts/desktop-setup.sh` exists. If not, PR #66 isn't merged yet.

2. **Check everything.**
   ```
   bash scripts/desktop-setup.sh
   ```
   It prints `ok`, `note` or `NEED` per item and ends with "All set" or a count of things to fix. Run it again after each fix. It may ask for your Ubuntu password once (to turn on lingering). Fixes for each `NEED`:

   | NEED says | Do |
   |---|---|
   | Claude is not logged in | `claude`, then `/login` and sign in with the Max account; `/exit`; rerun the script |
   | Claude is signed in with an API key or token | remove `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` / `CLAUDE_CODE_OAUTH_TOKEN` from `~/.bashrc`, `~/.profile` or `~/.zshrc`, open a new terminal, `claude` then `/login` |
   | Claude Code is not installed | `curl -fsSL https://claude.ai/install.sh \| bash`, open a new terminal, then the login above |
   | gcloud can't read the data bucket | `gcloud auth login` (the account the old pass used), then `gcloud config set project nfl-project-prod` |
   | checkout is on '...', not main | `git switch main && git pull --ff-only` |
   | systemd is off | `sudo sh -c 'printf "[boot]\nsystemd=true\n" >> /etc/wsl.conf'`, then in PowerShell `wsl --shutdown`, then open Ubuntu again |
   | nothing keeps WSL running after sign-in | job-search's "JobSearch WSL" task does this; see `~/dev/job-search/docs/runbook.md`, "Start at Windows login" |
   | uv is not installed | `curl -LsSf https://astral.sh/uv/install.sh \| sh`, new terminal |

3. **Try one game** (optional, about 3 minutes, nothing stored or published):
   ```
   bash scripts/desktop-setup.sh --test-game 2026_11_LV_DEN
   ```
   Any game id of the coming week works (`uv run nfl narrative slate <season> <week>` lists them). Expect a table with `ok (not stored)`, the pages and searches it used, and how many items the checks dropped.

4. **Switch over and run a pass now.**
   ```
   bash scripts/desktop-setup.sh --enable
   ```
   This turns the timer on, disables the Windows task `nfl-narrative`, and starts a pass immediately for every game not yet kicked off. Follow it:
   ```
   journalctl --user -u nfl-narrative -f
   ```
   It ends with `desktop narrative pass done: <season> week <week> (claude)` after about 15 minutes. The site shows the new records a few minutes later, once the `nfl-site` job it starts has published.

## Optional: the late-status pass and the repeat check (ADR 0032)

**Late-status pass.** A short second pass re-checks only who plays (starting quarterback, injury designations, inactives, starters ruled out) for games that already have a record, so the news adjustment sees Thursday and Saturday-morning news before each lock. About 5 minutes for a full slate; the records are new `claude_max` records with `pass_kind: status`. The units are installed **off** by `desktop-setup.sh`; switch the timer (Thursday 07:30 and Saturday 10:30 Eastern, `STATUS_PASSES`) on or off with:
```
bash scripts/desktop-setup.sh --enable-status
bash scripts/desktop-setup.sh --disable-status
```
Run one by hand (any time, games already status-checked since the last slot are skipped): `systemctl --user start nfl-narrative-status.service`, or `uv run nfl narrative claude <season> <week> --status-only [game_id...]`. Nothing waits for it: the lock takes the latest record before it, and the cloud `narrative check` counts full passes only, so a status pass that doesn't run changes nothing.

**Repeat check (by hand, about 7 minutes).** Researches three games that have a stored record from the latest full pass a second time, stores nothing, and appends the comparison to `marts/narrative_repeat.parquet`:
```
uv run nfl narrative repeat <season> <week> --games 3
uv run nfl narrative repeat --report      # agreement per rating, no research
```

## Checks afterwards

- Next runs: `systemctl --user list-timers nfl-narrative.timer`
- Last pass output: `journalctl --user -u nfl-narrative -n 80`; full log in `data/raw/narrative_claude/passes/`
- One game's session (prompt, transcript, record, what was dropped): `data/raw/narrative_claude/season=<S>/week=<WW>/<game_id>_<time>/`
- Every check without a pass: `bash scripts/desktop-narrative.sh --producer claude --dry-run`
- Run a pass by hand (stored games are skipped): `systemctl --user start nfl-narrative.service`

## When an email comes

| Email | Do |
|---|---|
| Claude is not logged in on the desktop | `claude`, `/login`, then `systemctl --user start nfl-narrative.service` |
| the Claude login expires in N day(s) | the same login, before it runs out (logins last a few weeks) |
| some games failed | `systemctl --user start nfl-narrative.service` resumes; the game's folder above says why (often the usage limit: wait for it to reset) |

## Going back to the local model

```
bash scripts/desktop-setup.sh --disable
```
Timer off, Windows task `nfl-narrative` back on. Ollama and SearXNG must be running for it (docs/desktop-llm-setup.md).
