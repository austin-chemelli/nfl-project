# Keeping the project state current

`docs/state.md` is where the project is. `docs/journal.md` is how it got there. `.notes/board.md` is who is doing what right now (uncommitted, one file shared by every worktree). Chats keep all three current as part of the work, at the boundaries below; Austin never has to. The SessionStart hook (`scripts/hooks/session-start.sh`) puts the hub, the board, the last two journal entries and `scripts/state_check.py`'s findings in every chat's context; the PreToolUse hook (`scripts/hooks/pr-guard.sh`) and CI enforce the PR boundary.

Fix any `ERROR` the check reports the first time you touch docs in a session, whoever caused it. `WARN` lines are environmental (another chat's worktree, a stale date): fix them if they're yours, mention them to Austin if not.

## When a track starts (you have a worktree and a branch)

1. `git fetch`, then re-read the Workstreams table in the hub and the board.
2. If an area you need is claimed on the board by another row, stop and tell Austin; don't edit it. Small additive touches (one CLAUDE.md line, an optional contract field) are allowed: note them in your row.
3. Add your board row: track, chat, branch, worktree, areas claimed, doing now, date.
4. Add your workstream row to `docs/state.md` on your branch. If the track will run longer than a day, also put that one row on `main` so other chats see it on their next fetch: from the primary checkout, `git cherry-pick` the docs-only commit and push (docs-only pushes don't need asking).
5. Scratch notes for the track go in `.notes/<track>/`.

## Checkpoint (before `gh pr create`, and whenever a decision closes or a finding changes direction)

The hook blocks `gh pr create` and `git push` on a branch that changes code without changing the journal or the hub, and whenever `state_check --strict` finds errors. Do this before it has to:

1. **Journal entry**, appended at the end of `docs/journal.md`, in the file's existing shape:

   ```
   ## YYYY-MM-DD: <what, in one line> (<milestone or PR>)

   **Why.** The problem or the request.
   **What changed.** What was built or changed, with the files or commands that matter.
   **Findings.** Numbers with n, surprises, what the data said.
   **Lesson.** What to do differently, or what this closes.
   ```

   A short entry is fine. A PR with nothing worth recording gets the label `docs-not-needed` instead (rare).

2. **Hub edits** in `docs/state.md`, only the parts your work changed:
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

1. Delete your board row.
2. In the hub: mark the workstream row merged with the date and PR, or delete it if nothing follows; move the bottom line forward if the merge changed what's live. Docs-only commit on `main`, pushed.
3. The journal entry reached `main` with the PR; nothing to do.

## Rules that keep conflicts small

- Journal: append at the end only. Hub: edit only the rows and sections your work touched. tasks.md: only your milestone's section. One-row conflicts rebase cleanly.
- The hub stays under 200 lines. Detail goes in the reference docs and the journal; the hub links.
- Dates are absolute (2026-11-04), never "today" or "this week".
- The desktop's Tailscale IP, keys and tokens never appear in any of these files.
