# Phase 2: the scheduled jobs (docs/hosting.md §1). One image, four jobs, one scheduler identity.
# The image tag is managed by the image workflow (gcloud run jobs update), so Terraform ignores it.

locals {
  image = var.image != "" ? var.image : "${var.region}-docker.pkg.dev/${var.project_id}/nfl/nfl:latest"
  jobs = {
    weekly-refresh = { args = ["refresh"], timeout = "7200s", secrets_key = false }
    lock-thu       = { args = ["lock", "thu"], timeout = "3600s", secrets_key = true }
    lock-sat       = { args = ["lock", "sat"], timeout = "3600s", secrets_key = true }
    odds-snapshot  = { args = ["odds"], timeout = "1800s", secrets_key = false }
  }
  # Cloud Scheduler cron in America/New_York (DST handled by the time zone).
  # The lock schedules stay paused until the shadow week is verified (docs/hosting.md §4.4);
  # flip var.locks_paused to false to go live.
  schedules = {
    weekly-refresh = { "tue-10" = "0 10 * * 2" }
    lock-thu       = { "thu-09" = "0 9 * * 4" }
    lock-sat       = { "sat-12" = "0 12 * * 6" }
    odds-snapshot = {
      "thu-2005" = "5 20 * * 4"
      "sun-0920" = "20 9 * * 0"
      "sun-1250" = "50 12 * * 0"
      "sun-1600" = "0 16 * * 0"
      "sun-2010" = "10 20 * * 0"
      "mon-2005" = "5 20 * * 1"
    }
  }
  schedule_pairs = merge([
    for job, crons in local.schedules : { for name, cron in crons : "${job}-${name}" => { job = job, cron = cron } }
  ]...)
}

resource "google_cloud_run_v2_job" "jobs" {
  for_each            = local.jobs
  name                = "nfl-${each.key}"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.jobs.email
      timeout         = each.value.timeout
      max_retries     = 0

      containers {
        image   = local.image
        command = ["/app/cloud-job.sh"]
        args    = each.value.args
        resources {
          limits = { cpu = "4", memory = "8Gi" }
        }
        env {
          name  = "NFL_DATA_ROOT"
          value = "/mnt/data"
        }
        env {
          name  = "NFL_SITE_ROOT"
          value = "/mnt/site"
        }
        env {
          name = "ODDS_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.odds_api_key.secret_id
              version = "latest"
            }
          }
        }
        dynamic "env" {
          for_each = each.value.secrets_key ? [1] : []
          content {
            name  = "GITHUB_DEPLOY_KEY_FILE"
            value = "/secrets/github-deploy-key"
          }
        }
        volume_mounts {
          name       = "data"
          mount_path = "/mnt/data"
        }
        volume_mounts {
          name       = "site"
          mount_path = "/mnt/site"
        }
        dynamic "volume_mounts" {
          for_each = each.value.secrets_key ? [1] : []
          content {
            name       = "secrets"
            mount_path = "/secrets"
          }
        }
      }

      volumes {
        name = "data"
        gcs {
          bucket    = google_storage_bucket.data.name
          read_only = false
        }
      }
      volumes {
        name = "site"
        gcs {
          bucket    = google_storage_bucket.site.name
          read_only = false
        }
      }
      dynamic "volumes" {
        for_each = each.value.secrets_key ? [1] : []
        content {
          name = "secrets"
          secret {
            secret = google_secret_manager_secret.github_deploy_key.secret_id
            items {
              version = "latest"
              path    = "github-deploy-key"
              mode    = 256 # 0400
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
  depends_on = [google_project_service.apis, google_secret_manager_secret_iam_member.jobs_read]
}

# ---------------------------------------------------------------- scheduler

resource "google_service_account" "scheduler" {
  account_id   = "nfl-scheduler"
  display_name = "Cloud Scheduler -> Cloud Run Jobs"
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  for_each = google_cloud_run_v2_job.jobs
  name     = each.value.name
  location = each.value.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_scheduler_job" "runs" {
  for_each  = local.schedule_pairs
  name      = "nfl-${each.key}"
  region    = var.region
  schedule  = each.value.cron
  time_zone = "America/New_York"
  paused    = startswith(each.value.job, "lock-") ? var.locks_paused : false
  # Each run is also retried by nothing: a failed execution alerts (alerts.tf) and is rerun by hand.
  attempt_deadline = "180s"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/${google_cloud_run_v2_job.jobs[each.value.job].id}:run"
    headers     = { "Content-Type" = "application/json" }
    body        = base64encode("{}")
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
  depends_on = [google_cloud_run_v2_job_iam_member.scheduler_invoker]
}
