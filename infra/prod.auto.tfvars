# Non-sensitive values, committed; CI and the laptop both read them.
# alert_email and billing_account come from terraform.tfvars locally (gitignored) and from
# repository secrets in CI (TF_VAR_alert_email, TF_VAR_billing_account).
project_id   = "nfl-project-prod"
region       = "us-central1"
locks_paused = true # flip to false after the shadow week (docs/runbook.md)
