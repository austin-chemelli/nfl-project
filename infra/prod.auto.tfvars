# Non-sensitive values, committed; CI and the laptop both read them.
# alert_email and billing_account come from terraform.tfvars locally (gitignored) and from
# repository secrets in CI (TF_VAR_alert_email, TF_VAR_billing_account).
project_id   = "nfl-project-prod"
region       = "us-central1"
locks_paused = false # live from 2026 Week 9 (Thu 2026-11-05); true pauses both lock schedules
