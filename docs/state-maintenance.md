# Keeping the project state current

`docs/state.md` is where the project is. `docs/journal.md` is how it got there. `.notes/hub/tracks/<track>.md` is who is doing what right now: one file per track, written only by that track's thread (uncommitted; every worktree shares `.notes/` through the symlink). The project hub (`~/dev/hub`, `hub.toml`) shows them with the PR and CI state from `gh`, the plans in `.notes/hub/plans/` and this file's decisions and milestones, at <http://localhost:8765/nfl-project/>, reloading on every file save. It replaced `.notes/board.md` on 2026-11-10. Chats keep all of these current as part of the work, at the boundaries below; Austin never has to. The SessionStart hook (`scripts/hooks/session-start.sh`) puts a digest in every chat's context (`state.md`'s bottom line and open decisions, one line per track, the session's own track file in full, the hub rules, the latest journal headings and `scripts/state_check.py`'s findings; the full hub is one Read away); the PreToolUse hook (`scripts/hooks/pr-guard.sh`) and CI enforce the PR boundary. The hooks are registered in two places, because Claude Code reads `.claude/settings.json` from the folder a session starts in: the repo's own (sessions started inside a checkout) and `~/dev/.claude/settings.json` (Austin's VS Code workspace is `~/dev`; copy `scripts/hooks/dev-folder-settings.json` there, absolute paths to the primary checkout's scripts). The scripts find the checkout from the session's cwd, so they work for every worktree; a session started in `~/dev` with no cwd in a checkout gets main's copy from `~/dev/nfl-project`.

Fix any `ERROR` the check reports the first time you touch docs in a session, whoever caused it. `WARN` lines are environmental (another chat's worktree, a stale date): fix them if they're yours, mention them to Austin if not.

## When a track starts (you have a worktree and a branch)

1. `git fetch`, then re-read the Workstreams table in `state.md` and the track files (the hub Board).
2. If an area you need is claimed by another track file (`areas:`), stop and tell Austin; don't edit it. Small additive touches (one CLAUDE.md line, an optional contract field) are allowed: note them in your track file. The Board flags two tracks claiming the same area.
3. Create your track file `.notes/hub/tracks/<track>.md`: frontmatter `title`, `thread`, `status` (running, waiting, idle, parked, done), `step`, `branch`, `worktree`, `pr`, `milestone`, `tasks`, `decisions`, `waiting_on`, `needs_you`, `plans`, `areas`, then a short body. Quote a value that contains ` #`. Keep it current at every step and PR; a Stop hook (`~/dev/hub/hooks/stop_track.py`) blocks the turn end when a turn changed files, committed or opened a PR without saving it. Format: `~/dev/hub/README.md`.
4. Add your workstream row to `docs/state.md` on your branch. If the track will run longer than a day, also put that one row on `main` so other chats see it on their next fetch: from the primary checkout, `git cherry-pick` the docs-only commit and push (docs-only pushes don't need asking).
5. Scratch notes for the track go in `.notes/<track>/`. Plans and decision briefs for Austin go in `.notes/hub/plans/<slug>.md` (a `## Decisions` section, one `### ` item each with Options, Recommendation, Status); link him to the plan's hub page instead of pasting it.

## Checkpoint (before `gh pr create`, and whenever a decision closes or a finding changes direction)

The hook blocks `gh pr create` and `git push` on a branch that changes code without changing the journal or `state.md`, and whenever `state_check --strict` finds errors. Do this before it has to:

1. **Journal entry**, appended at the end of `docs/journal.md`, in the file's existing shape:

   ```
   ## YYYY-MM-DD: <what, in one line> (<milestone or PR>)

   **Why.** The problem or the request.
   **What changed.** What was built or changed, with the files or commands that matter.
   **Findings.** Numbers with n, surprises, what the data said.
   **Lesson.** What to do differently, or what this closes.
   ```

   A short entry is fine. A PR with nothing worth recording gets the label `docs-not-needed` instead (rare).

2. **`state.md` edits**, only the parts your work changed:
   - Your workstream row: status and PR number.
   - Milestones: the row your work advanced.
   - Open decisions: close what you closed (move it to "Recently closed" with what closed it); add what you opened.
   - Known issues and risks: add what you found; remove what you fixed.
   - Schedule and links: if you changed `infra/jobs.tf`, `PASSES`, a workflow or a URL.
   - Bottom line: rewrite it, dated today, when the week's picture changed.
3. **Reference docs**: any doc in the docs map that describes something you changed gets updated and its "Verified" date bumped. The check flags a doc edited after its verified date.
4. **Notes**: promote a scratch note others will need into `docs/` (and the docs map); move the rest to `.notes/archive/`.
5. Run `python3 scripts/state_check.py` and fix what it reports. Commit the docs in the PR with the code.

## Close (after the merge and the branch cleanup in CLAUDE.md)

1. Fold your track file's results into `state.md`, `tasks.md` and the journal, then move the file to `.notes/hub/archive/`.
2. In `state.md`: mark the workstream row merged with the date and PR, or delete it if nothing follows; move the bottom line forward if the merge changed what's live. Docs-only commit on `main`, pushed.
3. The journal entry reached `main` with the PR; nothing to do.

## Rules that keep conflicts small

- Journal: append at the end only. `state.md`: edit only the rows and sections your work touched. Track files: only your own; changes that affect another track go through the master thread (`.notes/hub/project.md`). tasks.md: only your milestone's section. One-row conflicts rebase cleanly.
- `state.md` stays under 200 lines. Detail goes in the reference docs and the journal; `state.md` links.
- Dates are absolute (2026-11-04), never "today" or "this week".
- The desktop's Tailscale IP, keys and tokens never appear in any of these files.
