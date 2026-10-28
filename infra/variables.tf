variable "project_id" {
  description = "GCP project id"
  type        = string
}

variable "region" {
  description = "Region for jobs, buckets and the registry"
  type        = string
  default     = "us-central1"
}

variable "github_repo" {
  description = "owner/name of the GitHub repo (Workload Identity + deploy)"
  type        = string
  default     = "austin-chemelli/nfl-project"
}

variable "image" {
  description = "Container image for the jobs (set by the deploy workflow after a build)"
  type        = string
  default     = ""
}

variable "alert_email" {
  description = "Where job failures and stale-data alerts go"
  type        = string
}

variable "billing_account" {
  description = "Billing account id (XXXXXX-XXXXXX-XXXXXX) for the budget alert; empty disables it"
  type        = string
  default     = ""
}

variable "budget_usd" {
  description = "Monthly budget for the alert, in whole USD"
  type        = number
  default     = 10
}

variable "locks_paused" {
  description = "Keep the Thu/Sat lock schedules paused (shadow week); set false to go live"
  type        = bool
  default     = true
}
