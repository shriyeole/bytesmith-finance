# Deploying to Google Cloud (staging)

Frontend → **Firebase Hosting**. API → **Cloud Run** (`finance-api`, `asia-south1`).
Database → **Cloud SQL for PostgreSQL** (`asia-south1`). Login → **Firebase Authentication**.
Firebase Hosting forwards `/api/**` to Cloud Run, so the browser only ever talks to one domain.

Repeat everything below with a second project for production.

## 1. One-time project setup

**Shortcut:** steps 1 and 3 are automated in `infra/gcp-setup.sh` (project `finance-tracker-a4751`).
Open Cloud Shell, clone the repo, run `bash infra/gcp-setup.sh`, then copy the variables it prints into GitHub.
The manual commands below are kept for reference.

```bash
PROJECT_ID=your-staging-project-id
REGION=asia-south1
gcloud config set project $PROJECT_ID

gcloud services enable run.googleapis.com sqladmin.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com iamcredentials.googleapis.com cloudscheduler.googleapis.com

# Container registry
gcloud artifacts repositories create finance --repository-format=docker --location=$REGION

# Database (smallest tier to start; raise later). Public IP with NO authorised networks:
# it is reachable only through Cloud Run's built-in Cloud SQL connection (IAM-authorised, encrypted).
gcloud sql instances create finance-db --database-version=POSTGRES_16 --region=$REGION \
  --edition=ENTERPRISE --tier=db-f1-micro --storage-auto-increase \
  --backup-start-time=20:30 --enable-point-in-time-recovery
gcloud sql databases create finance --instance=finance-db
gcloud sql users create finance_app --instance=finance-db --password='CHOOSE-A-STRONG-PASSWORD'

# Connection string for Cloud Run (unix socket mounted at /cloudsql)
printf 'postgresql+psycopg://finance_app:CHOOSE-A-STRONG-PASSWORD@/finance?host=/cloudsql/%s:%s:finance-db' \
  $PROJECT_ID $REGION | gcloud secrets create database-url --data-file=-

# Runtime identity for the API and the migration job
gcloud iam service-accounts create finance-api
for ROLE in roles/cloudsql.client roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:finance-api@$PROJECT_ID.iam.gserviceaccount.com" --role=$ROLE
done
```

Set a **billing budget alert** (Billing → Budgets & alerts). Cloud SQL is the only part that costs money while idle.

## 2. Firebase

1. In the Firebase console, **Add project** → choose the existing GCP project above.
2. **Authentication → Sign-in method**: enable *Email/Password* and *Google*. Add your Hosting domain under *Authorized domains*.
3. **Project settings → Your apps → Web app**: register an app and copy `apiKey` and `authDomain`.
4. Copy `.firebaserc.example` to `.firebaserc` and fill in the project IDs.

## 3. GitHub Actions without key files (Workload Identity Federation)

```bash
gcloud iam service-accounts create github-deployer
for ROLE in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser \
            roles/firebasehosting.admin roles/serviceusage.serviceUsageConsumer roles/cloudsql.client roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com" --role=$ROLE
done

gcloud iam workload-identity-pools create github --location=global
gcloud iam workload-identity-pools providers create-oidc github-oidc --location=global \
  --workload-identity-pool=github --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='shriyeole/bytesmith-finance'"

PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud iam service-accounts add-iam-policy-binding github-deployer@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/shriyeole/bytesmith-finance"
```

In GitHub → *Settings → Environments → staging → Variables*, add:

| Variable | Value |
| --- | --- |
| `GCP_PROJECT_ID` | your project ID |
| `GCP_WIF_PROVIDER` | `projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github/providers/github-oidc` |
| `GCP_DEPLOY_SA` | `github-deployer@<PROJECT_ID>.iam.gserviceaccount.com` |
| `CLOUD_SQL_INSTANCE` | `<PROJECT_ID>:asia-south1:finance-db` |
| `FIREBASE_API_KEY` | from step 2 |
| `FIREBASE_AUTH_DOMAIN` | from step 2 |

After that, every green CI run on `main` builds the image, runs `alembic upgrade head` as the
`finance-migrate` Cloud Run Job, deploys the API, then deploys the frontend.

## 3b. AI setup chat (Gemini) — optional

New users land on a chat (`/start`) that fills in their profile, income, spending, savings,
loans, insurance, family and goals. It needs a Gemini API key; without one the chat shows a
notice and the step-by-step forms still work.

1. Create a key at https://aistudio.google.com/apikey (pick project `finance-tracker-a4751`).
   Use a key on a project with billing enabled: on the free tier Google may use prompts to
   improve its products, which is not acceptable for users' financial details.
2. Store it in Secret Manager (Cloud Shell), never in the repo:
   ```bash
   printf '%s' 'PASTE-KEY-HERE' | gcloud secrets create gemini-api-key --replication-policy=automatic --data-file=-
   ```
   (`finance-api` already has `secretAccessor`.) To rotate: `gcloud secrets versions add gemini-api-key --data-file=-`.
3. In GitHub → Settings → Secrets and variables → Actions → Variables, add `GEMINI_SECRET` = `gemini-api-key`.
   The next deploy passes it to Cloud Run as `GEMINI_API_KEY`.

Optional settings: `GEMINI_MODEL` (default `gemini-3.8-flash`), `ASSISTANT_DAILY_MESSAGES` (default 60 per user per day).
Locally, put `GEMINI_API_KEY=...` in `backend/.env` (git-ignored).

## 4. Running locally

| Mode | Command |
| --- | --- |
| Quick (SQLite, dev login) | `cd backend && pip install -r requirements-dev.txt && uvicorn app.main:app --reload --port 8080` |
| Like production (Postgres) | `docker compose up --build` |
| Frontend | `cd frontend && npm install && npm run dev` → http://localhost:5173 |
| Tests | `cd backend && pytest` |
| New migration after model changes | `cd backend && alembic revision --autogenerate -m "what changed"` |

In dev mode the API trusts `Authorization: Bearer dev:<any-id>`. The server refuses to start in
staging/production unless `AUTH_MODE=firebase`, a Postgres `DATABASE_URL` and `AUTO_CREATE_TABLES=false` are set.
