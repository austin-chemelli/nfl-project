# ADR 0023: Data before web, and a live contract check before every web deploy

Status: accepted 2026-11-07 (Austin). Amends ADR 0015's "contract changes stay additive" rule with a check that enforces it.

## Context
ADR 0015 publishes data independently of the site: scheduled jobs write the site JSON to a public bucket, and Firebase serves the React app, which reads that bucket at runtime. Its rule was that contract changes stay additive (new fields optional in zod), or the web deploy goes out before the data that needs it. Nothing enforced it. On 2026-11-07 PR #27 made new team-file fields required; the web deploy went out minutes after the merge, while the bucket still held files from the previous image, and the live Staff and Tendencies tabs failed to load until `nfl-site` was run by hand. The next scheduled site build was up to three days away. The reverse is also possible: a job change that drops a field the live page still needs.

## Options
1. **Optional fields only.** Every new field defaulted in zod, every page coded for its absence. Correct when followed, but it relies on remembering, and that's what failed. Doesn't cover a job dropping a field.
2. **Rebuild the data before the web deploy.** When the image changes, CI runs `nfl-site` with it, then deploys the web. New fields can be required, since the data has them by the time the page does. Doesn't catch a mismatch on its own.
3. **Check this commit's contract against the live data before the web deploy.** Parse every kind of published file with the new zod schemas; fail the deploy on any mismatch. Catches both directions, but on its own would block a correct change whose data isn't built yet.

## Decision
2 and 3 together, in CI on `main` (`.github/workflows/ci.yml`): `deploy-image` → `site-data` (runs `nfl-site --wait` when the image changed) → `contract-live` (`npm run test:live`, `web/src/data/live.contract.test.ts`, against the public bucket) → `deploy-site`. A failed check leaves the old page up and CI red. The check reads the meta, tracker, hypotheses, coaches, DIY matrix, league, similar, audit and last season's files, all 32 team files, this week's and last week's slates and recaps, and two games from each with their retros; a 404 is "not built yet" and passes.

## Consequences
- A merge that changes job code now also rebuilds the site data at once, instead of at the next schedule. `nfl-site` is idempotent, and merges already avoid the 10 minutes before a lock.
- Web deploys wait for the image build and the data rebuild when both changed: about 6 to 8 minutes instead of 2.
- Zod fields can be required again when the same PR makes the jobs write them. A web-only change that requires data no job writes yet fails the check, which is the point.
- The check needs the public bucket reachable from CI; it retries three times, then fails rather than deploying blind.
- Still not covered: a browser tab opened before a deploy, holding the old code, reading new data. Additive changes don't affect it; the error box's reload covers the rest.
