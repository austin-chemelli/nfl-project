# ADR 0008: Local first, then Terraform'd GCP + Firebase; no Actions cron, no GitHub Pages; self-hosting later

Status: accepted 2026-10-23, amended 2026-10-26.

## Context
Goals: live during the season, show hosting/IaC/CI, keep costs near zero, keep a path to self-hosting on the spare desktop and to eventual users. The first lock now waits for the approaches (ADR 0010), so an interim GitHub Actions cron scheduler would be used only briefly between the first lock and the GCP scheduler.

## Options
1. GitHub Actions cron as an interim scheduler (needs persisted state in git or a hand-made bucket), then GCP.
2. Run lock and refresh commands by hand until the Terraform'd GCP scheduler exists.
3. Homelab first.

## Decision
Option 2 (amendment). Locks and refreshes are commands run on the laptop at the lock times until P2; the commit timestamp is the proof. P2: one container image, Cloud Run Jobs + Cloud Scheduler + GCS (FUSE-mounted data root) + Secret Manager + Workload Identity Federation, all in `infra/` Terraform with plan-on-PR and apply-on-main. Site on Firebase Hosting in the same project; GitHub Pages is skipped. GitHub Actions is CI and the deploy trigger, not the scheduler. Self-hosting on the desktop (hybrid: desktop primary, cloud fallback, source of truth in GCS) is a separate project after the live pipeline is boring.

## Consequences
Manual lock runs until P2; a missed run is a missed lock, so the commands must be one-liners with a checklist. Portability rules from day one: one image with CLI subcommands, config via env, data root is a path, no code knows where it runs. Firebase rewrites only target Cloud Run/Functions, so a future desktop-hosted API would live on its own subdomain.
