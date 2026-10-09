#!/usr/bin/env bash
# One-time Google Cloud setup for the staging environment.
#
# Run in Google Cloud Shell (console.cloud.google.com -> ">_" icon), from the repo root:
#   bash infra/gcp-setup.sh
# Safe to re-run: every step skips what already exists.
# Creates a Cloud SQL instance, which is billed even when idle; billing must be enabled.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-finance-tracker-a4751}"
REGION="asia-south1"                                  # Mumbai
GITHUB_REPO="${GITHUB_REPO:-shriyeole/bytesmith-finance}"
SQL_INSTANCE="finance-db"
DB_NAME="finance"
DB_USER="finance_app"
API_SA="finance-api@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOY_SA="github-deployer@${PROJECT_ID}.iam.gserviceaccount.com"

step() { echo; echo "==> $*"; }
exists() { "$@" >/dev/null 2>&1; }
grant() { # grant <member> <role>
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="$1" --role="$2" --condition=None --quiet >/dev/null
}

gcloud config set project "$PROJECT_ID" >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
echo "Project $PROJECT_ID ($PROJECT_NUMBER), region $REGION, repo $GITHUB_REPO"

step "Enabling APIs (1-2 min)"
gcloud services enable \
  run.googleapis.com sqladmin.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  cloudscheduler.googleapis.com cloudresourcemanager.googleapis.com \
  firebase.googleapis.com firebasehosting.googleapis.com identitytoolkit.googleapis.com

step "Artifact Registry repository 'finance'"
exists gcloud artifacts repositories describe finance --location="$REGION" \
  || gcloud artifacts repositories create finance --repository-format=docker --location="$REGION"

step "Cloud SQL Postgres instance '$SQL_INSTANCE' (first time takes 5-10 min)"
# Public IP with no authorised networks: reachable only through Cloud Run's built-in,
# IAM-checked Cloud SQL connection.
exists gcloud sql instances describe "$SQL_INSTANCE" \
  || gcloud sql instances create "$SQL_INSTANCE" --database-version=POSTGRES_16 --region="$REGION" \
       --edition=ENTERPRISE --tier=db-f1-micro --storage-auto-increase \
       --backup-start-time=20:30 --enable-point-in-time-recovery
exists gcloud sql databases describe "$DB_NAME" --instance="$SQL_INSTANCE" \
  || gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE"

step "Database user + 'database-url' secret (password is generated, never printed)"
if exists gcloud secrets describe database-url; then
  echo "secret database-url already exists; leaving it alone"
else
  DB_PASS="$(openssl rand -hex 24)"
  if gcloud sql users list --instance="$SQL_INSTANCE" --format='value(name)' | grep -qx "$DB_USER"; then
    gcloud sql users set-password "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASS"
  else
    gcloud sql users create "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASS"
  fi
  printf 'postgresql+psycopg://%s:%s@/%s?host=/cloudsql/%s:%s:%s' \
    "$DB_USER" "$DB_PASS" "$DB_NAME" "$PROJECT_ID" "$REGION" "$SQL_INSTANCE" \
    | gcloud secrets create database-url --replication-policy=automatic --data-file=-
  unset DB_PASS
fi

step "Service accounts"
exists gcloud iam service-accounts describe "$API_SA" \
  || gcloud iam service-accounts create finance-api --display-name="Finance API (Cloud Run runtime)"
exists gcloud iam service-accounts describe "$DEPLOY_SA" \
  || gcloud iam service-accounts create github-deployer --display-name="GitHub Actions deployer"

for ROLE in roles/cloudsql.client roles/secretmanager.secretAccessor; do
  grant "serviceAccount:$API_SA" "$ROLE"
done
for ROLE in roles/run.admin roles/artifactregistry.writer roles/firebasehosting.admin \
            roles/serviceusage.serviceUsageConsumer roles/cloudsql.client; do
  grant "serviceAccount:$DEPLOY_SA" "$ROLE"
done
# The deployer may run services/jobs as the API identity, and nothing else.
gcloud iam service-accounts add-iam-policy-binding "$API_SA" \
  --member="serviceAccount:$DEPLOY_SA" --role=roles/iam.serviceAccountUser --quiet >/dev/null

step "Daily alerts schedule (08:00 IST) -> Cloud Run Job finance-daily-alerts"
grant "serviceAccount:$API_SA" roles/run.invoker
exists gcloud scheduler jobs describe finance-daily-alerts --location="$REGION" \
  || gcloud scheduler jobs create http finance-daily-alerts --location="$REGION" \
       --schedule="0 8 * * *" --time-zone="Asia/Kolkata" --http-method=POST \
       --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/finance-daily-alerts:run" \
       --oauth-service-account-email="$API_SA"
echo "(The job itself is created by the first GitHub deploy; the schedule simply fails until then.)"

step "Workload Identity Federation for GitHub Actions (no key files)"
exists gcloud iam workload-identity-pools describe github --location=global \
  || gcloud iam workload-identity-pools create github --location=global --display-name="GitHub Actions"
exists gcloud iam workload-identity-pools providers describe github-oidc --location=global --workload-identity-pool=github \
  || gcloud iam workload-identity-pools providers create-oidc github-oidc --location=global \
       --workload-identity-pool=github --issuer-uri="https://token.actions.githubusercontent.com" \
       --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
       --attribute-condition="assertion.repository=='${GITHUB_REPO}'"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository/${GITHUB_REPO}" \
  --quiet >/dev/null

cat <<OUT

==> Done. Add these in GitHub: ${GITHUB_REPO} -> Settings -> Environments -> "staging" -> Variables

  GCP_PROJECT_ID       ${PROJECT_ID}
  GCP_WIF_PROVIDER     projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/providers/github-oidc
  GCP_DEPLOY_SA        ${DEPLOY_SA}
  CLOUD_SQL_INSTANCE   ${PROJECT_ID}:${REGION}:${SQL_INSTANCE}
  FIREBASE_API_KEY     (Firebase console -> Project settings -> Your apps -> Web app)
  FIREBASE_AUTH_DOMAIN ${PROJECT_ID}.firebaseapp.com

Also: Firebase console -> Authentication -> Sign-in method -> enable Email/Password and Google.
Set a budget alert: Billing -> Budgets & alerts.
OUT
