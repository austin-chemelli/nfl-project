output "data_bucket" { value = google_storage_bucket.data.name }
output "site_bucket" { value = google_storage_bucket.site.name }
output "site_data_url" { value = "https://storage.googleapis.com/${google_storage_bucket.site.name}" }
output "registry" { value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}" }
output "jobs_service_account" { value = google_service_account.jobs.email }
output "desktop_service_account" { value = google_service_account.desktop.email }

# Paste these two into GitHub -> Settings -> Secrets and variables -> Actions -> Variables.
output "github_var_GCP_WIF_PROVIDER" { value = google_iam_workload_identity_pool_provider.github.name }
output "github_var_GCP_DEPLOY_SA" { value = google_service_account.deploy.email }
