# infra

Terraform for the hosted pipeline (docs/hosting.md). Phase 1 here: APIs, buckets, registry,
service accounts, empty secrets, keyless GitHub auth. `jobs.tf` and `alerts.tf` follow once the
first cloud refresh works.

First time, from this directory, after `docs/hosting.md` §3 items 1–3:

    cp terraform.tfvars.example terraform.tfvars   # edit project_id and alert_email (gitignored)
    terraform init -backend-config="bucket=<project_id>-tfstate"
    terraform plan
    terraform apply

Then add the secret values (§3.4) and the two GitHub variables from `terraform output`.
