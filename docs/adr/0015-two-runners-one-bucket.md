# ADR 0015: Two runners, one bucket; site data served from storage, not redeployed

Status: accepted 2026-10-28 (plan; implementation is step 5). Amends ADR 0008 (hosting path) for the consequences of ADR 0014 (the LLM runs on the desktop).

## Context
ADR 0008 put the whole weekly pipeline in Cloud Run Jobs. ADR 0014 then moved the LLM work to the desktop, which a cloud job can't reach without joining the home network. The locks must never depend on the desktop being on. Separately, the site's data (`marts/site/*.json`) changes several times a week (locks, grading, odds snapshots), so "redeploy the site whenever data changes" would mean a Firebase deploy from inside every job.

## Decision
- **Two runners, one source of truth.** The **cloud** (Cloud Run Jobs on a schedule) runs everything numeric: ingest, curate, features, locks, grading, ledger, site JSON. The **desktop** runs only the LLM jobs (narrative research, previews) on its own schedule. They never call each other; they share one private GCS bucket (`nfl-data`): the cloud mounts it as `NFL_DATA_ROOT`; the desktop uploads narrative records and previews to it. A lock reads whatever narrative records exist; if the desktop was off, the Narrative approach simply has no record for that game (it is shadow anyway).
- **Site data lives in a public bucket, not in the site.** A second bucket (`nfl-site-public`) holds `site/*.json` (and `public/predictions/` copies) with public read, CORS, and `Cache-Control: max-age=300`. The React site fetches from it. Firebase Hosting serves only the static app, deployed by GitHub Actions on pushes to `main`. Data updates need no deploy.
- **Locks commit and push from the cloud job** with a GitHub deploy key (write, this repo only) held in Secret Manager, the same `nfl lock --commit --push` path as today.
- **Local dev reads the bucket**, never writes to it: `gcloud storage rsync` down, or a FUSE mount on WSL read-only. The laptop stops being a runner once the cloud locks are verified (one shadow week where both run and must agree).

## Consequences
The desktop can be off for days without affecting the public record. Narrative records are eventually consistent (a record uploaded after a lock is used by the next lock). Two buckets and one deploy key to manage. The site has a hard dependency on the public bucket's availability (GCS SLA is fine). No API server still (ADR 0009); the only server-side code is scheduled jobs.
