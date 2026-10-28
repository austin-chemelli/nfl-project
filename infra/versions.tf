terraform {
  required_version = ">= 1.9"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
  # State lives in a bucket Austin creates once by hand (docs/hosting.md §3.3).
  # The bucket name is passed at init: terraform init -backend-config="bucket=<project>-tfstate"
  backend "gcs" {
    prefix = "nfl-project"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
