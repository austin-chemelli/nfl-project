# nfl-project infrastructure (docs/hosting.md, ADR 0015: two runners, one bucket).
# Phase 1 of the plan: APIs, buckets, registry, service accounts, secrets (empty), WIF for Actions.
# Jobs, schedules and alerts are added in jobs.tf / alerts.tf once the first cloud refresh works.

locals {
  services = [
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "storage.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "billingbudgets.googleapis.com",
    "iam.googleapis.com",
    "cloudbilling.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------- buckets

# The data root: today's ./data layout, mounted by every job at /mnt/data. Private.
resource "google_storage_bucket" "data" {
  name                        = "${var.project_id}-data"
  location                    = var.region
  uniform_bucket_level_access = true
  versioning { enabled = true }
  lifecycle_rule {
    condition { num_newer_versions = 5 }
    action { type = "Delete" }
  }
  depends_on = [google_project_service.apis]
}

# What the site reads: marts/site/*.json copied here after each run. Public, cached briefly.
resource "google_storage_bucket" "site" {
  name                        = "${var.project_id}-site"
  location                    = var.region
  uniform_bucket_level_access = true
  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD"]
    response_header = ["Content-Type", "Cache-Control"]
    max_age_seconds = 3600
  }
  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket_iam_member" "site_public" {
  bucket = google_storage_bucket.site.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# ---------------------------------------------------------------- images

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "nfl"
  format        = "DOCKER"
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions { keep_count = 10 }
  }
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition { older_than = "2592000s" } # 30 days
  }
  depends_on = [google_project_service.apis]
}

# ---------------------------------------------------------------- service accounts

# Runs the jobs: reads/writes the data bucket, writes the site bucket, reads secrets.
resource "google_service_account" "jobs" {
  account_id   = "nfl-jobs"
  display_name = "nfl-project Cloud Run Jobs"
}

resource "google_storage_bucket_iam_member" "jobs_data" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.jobs.email}"
}

resource "google_storage_bucket_iam_member" "jobs_site" {
  bucket = google_storage_bucket.site.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.jobs.email}"
}

# The desktop's narrative uploads: write-only into the data bucket's narrative/ prefix is not
# expressible with IAM alone; it gets objectCreator on the data bucket (can add, cannot overwrite or
# read). Key is created by hand only if the desktop can't use Austin's own login (docs/hosting.md).
resource "google_service_account" "desktop" {
  account_id   = "nfl-desktop"
  display_name = "nfl-project desktop uploader"
}

resource "google_storage_bucket_iam_member" "desktop_data" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.desktop.email}"
}

# ---------------------------------------------------------------- secrets (empty; values added by hand)

resource "google_secret_manager_secret" "odds_api_key" {
  secret_id = "odds-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "github_deploy_key" {
  secret_id = "github-deploy-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "jobs_read" {
  for_each  = { odds = google_secret_manager_secret.odds_api_key.id, gh = google_secret_manager_secret.github_deploy_key.id }
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.jobs.email}"
}

# ---------------------------------------------------------------- GitHub Actions -> GCP (keyless)

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository == \"${var.github_repo}\""
  oidc { issuer_uri = "https://token.actions.githubusercontent.com" }
}

# What Actions may do: push images, apply Terraform, run jobs, deploy to Firebase.
resource "google_service_account" "deploy" {
  account_id   = "nfl-deploy"
  display_name = "nfl-project GitHub Actions deployer"
}

resource "google_service_account_iam_member" "deploy_wif" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

resource "google_project_iam_member" "deploy_roles" {
  for_each = toset([
    "roles/artifactregistry.admin",
    "roles/run.admin",
    "roles/cloudscheduler.admin",
    "roles/iam.serviceAccountUser",
    "roles/storage.admin",
    "roles/secretmanager.admin",
    "roles/monitoring.editor",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/iam.workloadIdentityPoolAdmin",
    "roles/firebasehosting.admin",
    "roles/resourcemanager.projectIamAdmin", # this file's project IAM bindings, from CI
    "roles/logging.admin",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_project_iam_member" "deploy_sa_admin" {
  project = var.project_id
  role    = "roles/iam.serviceAccountAdmin"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# The budget lives on the billing account, so CI needs a role there too (empty account = skip).
resource "google_billing_account_iam_member" "deploy_budgets" {
  count              = var.billing_account != "" ? 1 : 0
  billing_account_id = var.billing_account
  role               = "roles/billing.costsManager"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}
