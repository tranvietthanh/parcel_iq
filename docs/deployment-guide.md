# OZ Property Report — K3s Deployment Guide

Complete guide for deploying OZ Property Report to a remote K3s cluster. Covers pre-flight checks, step-by-step deployment, post-deployment verification, data initialization, and troubleshooting.

---

## 1. Pre-Deployment Checklist

Complete **every** item below before running `make deploy`. A single missed step will cause pod failures that are hard to debug once everything is starting up simultaneously.

### 1.1 Local Machine

```bash
# ── Docker ────────────────────────────────────────────────────────────────────
# Logged into your container registry?
docker login ghcr.io          # or your registry
docker info | grep Username   # confirm session is active

# ── kubectl ───────────────────────────────────────────────────────────────────
# Pointed at the correct cluster?
kubectl config current-context         # should show your K3s context
kubectl get nodes                      # should list k3s-master, k3s-node01, k3s-node02

# ── envsubst ──────────────────────────────────────────────────────────────────
which envsubst                         # required by `make deploy`

# ── REGISTRY set ──────────────────────────────────────────────────────────────
export REGISTRY=ghcr.io/your-org       # replace with your actual registry
echo $REGISTRY                         # verify it's not the placeholder
```

> [!IMPORTANT]
> **Private Registry:** If your registry is private (e.g., private GHCR, private Docker Hub, ECR), you **must** be logged in via `docker login` on the machine running `make deploy`. The deploy process automatically copies your Docker credentials to the cluster as a `regcred` Kubernetes secret. All app pods reference this secret via `imagePullSecrets` — without it, K3s nodes cannot pull your images and pods will fail with `ImagePullBackOff`.
>
> **GitHub PAT for GHCR:** Use a Personal Access Token with `read:packages` scope:
> ```bash
> echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin
> ```

### 1.2 Root `.env` File

The root `.env` file is the **single source of truth** for all secrets pushed to the cluster. Every key listed in [`infra/k8s/secrets.example.yaml`](../infra/k8s/secrets.example.yaml) must be present with a real value.

```bash
# Verify .env exists and has no <PLACEHOLDER> values
cat .env | grep -c PLACEHOLDER        # must return 0

# Minimum required keys (check these carefully)
grep -E '^(POSTGRES_USER|POSTGRES_PASSWORD|POSTGRES_DB)=' .env
grep -E '^(DATABASE_URL|DATABASE_URL_SYNC)=' .env
grep -E '^(CLERK_PUBLIC_PUBLISHABLE_KEY|CLERK_PUBLIC_SECRET_KEY)=' .env
grep -E '^(CLERK_ADMIN_PUBLISHABLE_KEY|CLERK_ADMIN_SECRET_KEY)=' .env
grep -E '^(ADMIN_SERVICE_TOKEN|MINIO_ACCESS_KEY|MINIO_SECRET_KEY)=' .env
```

> [!CAUTION]
> **DATABASE_URL vs DATABASE_URL_SYNC** — You need both:
> - `DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/db` (FastAPI services)
> - `DATABASE_URL_SYNC=postgresql+psycopg2://user:pass@postgres:5432/db` (Celery workers + migrations)
>
> Note the hostnames use `postgres` (K8s service name), **not** `localhost`.

### 1.3 Cluster Prerequisites

```bash
# ── Namespace doesn't exist yet (first deploy) or is healthy (re-deploy) ─────
kubectl get ns ozpropertyreport 2>/dev/null || echo "Namespace doesn't exist yet (OK for first deploy)"

# ── Longhorn storage is available ─────────────────────────────────────────────
kubectl get storageclass longhorn       # must exist — PVCs depend on it
kubectl get nodes -o custom-columns=NAME:.metadata.name,CPU:.status.allocatable.cpu,MEMORY:.status.allocatable.memory

# ── cert-manager is running ──────────────────────────────────────────────────
kubectl get clusterissuer letsencrypt-prod   # must show READY=True
kubectl get pods -n cert-manager             # all pods Running

# ── Traefik is running ────────────────────────────────────────────────────────
kubectl get pods -n kube-system | grep traefik   # should show 1/1 Running
```

### 1.4 DNS (Required for TLS)

Let's Encrypt HTTP-01 challenge requires **real public DNS**. Before deploying with TLS, create A records:

| Domain | Type | Value |
|---|---|---|
| `ozpropertyreport.com` | A | Any K3s node IP (e.g. `192.168.10.185`) |

```bash
# Verify DNS is propagated
dig ozpropertyreport.com +short         # should return the node IP
```

> [!NOTE]
> If DNS is not ready yet, the deploy will succeed but TLS certs will fail to issue. You can deploy first and configure DNS after — cert-manager will retry automatically.

---

## 2. Build Images

```bash
# Set your tag and registry
export REGISTRY=ghcr.io/your-org
TAG=v1.0.0

# Build all 7 images (6 services + 1 migration)
make build-docker tag=$TAG
```

### What Gets Built

| Image | Source | Context |
|---|---|---|
| `ozpr-public-api` | `services/public-api/Dockerfile` | `services/public-api/` |
| `ozpr-admin-backend` | `services/admin-backend/Dockerfile` | `services/admin-backend/` |
| `ozpr-public-web` | `apps/public-web/Dockerfile` | `.` (repo root) |
| `ozpr-admin-web` | `apps/admin-web/Dockerfile` | `.` (repo root) |
| `ozpr-scraper-worker` | `services/scraper-worker/Dockerfile` | `services/scraper-worker/` |
| `ozpr-llm-parser-worker` | `services/llm-parser-worker/Dockerfile` | `services/llm-parser-worker/` |
| `ozpr-db-migrate` | `shared/db-migrations/Dockerfile` | `shared/db-migrations/` |

### Quick Validation

```bash
# Confirm all 7 images exist locally
docker images | grep "ozpr-.*:$TAG"
# Should show 7 rows
```

---

## 3. Deploy

```bash
make deploy tag=$TAG REGISTRY=$REGISTRY
```

The `deploy` target runs these steps in order:

```
1. Push all 7 images to the registry
2. Apply namespace + configmap
3. Apply secrets from .env → ozpr-secrets
4. Apply PVCs (Postgres 10Gi, Redis 2Gi, MinIO 10Gi on Longhorn)
5. Apply infrastructure (Postgres, Redis, MinIO, Flower)
6. Wait for Postgres StatefulSet to be ready
7. Delete old migration Job, apply new one, wait for completion
8. Apply all 6 application Deployments (envsubst injects IMAGE_TAG + REGISTRY)
9. Apply Ingress + NetworkPolicy
```

You'll see a confirmation prompt with the cluster context before anything is applied.

---

## 4. Post-Deployment Verification

Run these checks **in order** after `make deploy` completes.

### 4.1 All Pods Running

```bash
make k8s-status

# Expected: all pods show Running (except db-migrate which shows Completed)
# Watch for: CrashLoopBackOff, ImagePullBackOff, Pending
```

Wait until all pods are Running before proceeding. If any pod is stuck, jump to [Troubleshooting](#7-troubleshooting).

### 4.2 Pod Health Detail

```bash
# Check each service individually
kubectl get pods -n ozpropertyreport -o wide

# Describe any pod that isn't Running
kubectl describe pod <pod-name> -n ozpropertyreport
```

### 4.3 Migration Job

```bash
# Should show Succeeded
kubectl get job db-migrate -n ozpropertyreport

# Check migration logs
kubectl logs job/db-migrate -n ozpropertyreport
# Should end with: "alembic upgrade head" success message
```

### 4.4 Infrastructure Health

```bash
# Postgres — can we connect?
kubectl exec -it statefulset/postgres -n ozpropertyreport -- \
  pg_isready -U parceliq -d parceliq
# Response: localhost:5432 - accepting connections

# Redis — is it responding?
kubectl exec -it deploy/redis -n ozpropertyreport -- redis-cli ping
# Response: PONG

# MinIO — health check
kubectl exec -it deploy/minio -n ozpropertyreport -- \
  curl -sf http://localhost:9000/minio/health/live
# Response: (empty 200 OK)
```

### 4.5 Application Health Endpoints

```bash
# Public API — internal check via kubectl exec
kubectl exec -it deploy/public-web -n ozpropertyreport -- \
  wget -qO- http://public-api:8080/api/health
# Should return JSON health response

# Admin Backend — internal check
kubectl exec -it deploy/admin-web -n ozpropertyreport -- \
  wget -qO- http://admin-backend:8082/health
# Should return JSON health response
```

### 4.6 Ingress & TLS

```bash
# Check Ingress resources
kubectl get ingress -n ozpropertyreport
# Should show the public-web and admin-web ingresses with hosts assigned

# Check TLS certificates
kubectl get certificate -n ozpropertyreport
# Should show public-web-tls (and admin-web-tls if you expose admin-web via ingress)
# (may take 1-2 minutes after first deploy for cert-manager to issue)

# Test public endpoints (after DNS is configured)
curl -sI https://ozpropertyreport.com | head -5
```

### 4.7 NetworkPolicy Enforcement

```bash
# admin-backend should NOT be reachable from public-web
kubectl exec -it deploy/public-web -n ozpropertyreport -- \
  wget -qO- --timeout=3 http://admin-backend:8082/health 2>&1
# Expected: download timed out (connection blocked by NetworkPolicy)

# admin-backend SHOULD be reachable from admin-web
kubectl exec -it deploy/admin-web -n ozpropertyreport -- \
  wget -qO- --timeout=3 http://admin-backend:8082/health
# Expected: JSON health response
```

### 4.8 Admin Surfaces (Port-Forward)

```bash
make k8s-admin
# Opens:
#   http://localhost:3001  ← admin-web (sign in with admin Clerk)
#   http://localhost:9001  ← MinIO console (use MINIO_ACCESS_KEY/SECRET_KEY)
#   http://localhost:5555  ← Flower (Celery task monitor)

# Press Ctrl+C to stop all port-forwards
```

---

## 5. Data Initialization (First Deploy Only)

After the first deploy, the database has schema but no data. Bootstrap VIC reference data:

### 5.1 Download Source Data

| Dataset | Source | Expected File |
|---|---|---|
| LGA boundaries | [ABS ASGS](https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/digital-boundary-files) | `LGA_2024_AUST_GDA2020.shp` |
| Suburb boundaries | [ABS ASGS](https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/digital-boundary-files) | `SAL_2021_AUST_GDA2020.shp` |
| School catchments | Victorian Dept. of Education | `school_catchments_vic.geojson` |
| School locations | [ACARA My School](https://www.myschool.edu.au/media-centre/data-assets) | `vic_schools_2024.csv` |
| G-NAF addresses | [data.gov.au](https://data.gov.au/dataset/geocoded-national-address-file-g-naf) | `gnaf_feb2026.zip` |

### 5.2 Run Import

```bash
make k8s-init-data \
  lga_source=/path/to/LGA_2024_AUST_GDA2020.shp \
  suburb_source=/path/to/SAL_2021_AUST_GDA2020.shp \
  catchment_source=/path/to/school_catchments_vic.geojson \
  school_source=/path/to/vic_schools_2024.csv \
  gnaf_source=/path/to/gnaf_feb2026.zip
```

This port-forwards Postgres to `localhost:15432`, runs all 6 import steps sequentially, creates MinIO buckets, then cleans up.

> [!IMPORTANT]
> The G-NAF import (step 5/6) can take **30–60 minutes** and requires **≥16 GiB RAM** on the machine running the import. Do not interrupt it.

### 5.2.1 More Stable Option for Long Runs

If your network or `kubectl port-forward` is unstable, run the long steps independently so you can retry without re-running all 6 steps:

```bash
# Run once for steps 1-4 + buckets
make k8s-init-data \
  lga_source=/path/to/LGA_2024_AUST_GDA2020.shp \
  suburb_source=/path/to/SAL_2021_AUST_GDA2020.shp \
  catchment_source=/path/to/school_catchments_vic.geojson \
  school_source=/path/to/vic_schools_2024.csv \
  gnaf_source=/path/to/gnaf_feb2026.zip

# If step 5 fails or you want to run it separately
make k8s-import-gnaf source=/path/to/gnaf_feb2026.zip state=VIC batch=100000

# Then run step 6 separately (can be retried safely)
make k8s-create-properties state=VIC batch=1000
```

Both scripts now include retry + reconnect behavior for transient PostgreSQL disconnects, and both imports are idempotent (`ON CONFLICT DO NOTHING`), so rerunning is safe.

### 5.3 Verify Data

```bash
# Port-forward Postgres for verification queries
kubectl port-forward -n ozpropertyreport svc/postgres 15432:5432 &

psql postgresql://parceliq:$PG_PASS@localhost:15432/parceliq -c "
  SELECT zone_type, count(*)
  FROM spatial_zones
  WHERE state = 'VIC'
  GROUP BY zone_type
  ORDER BY zone_type;
"
# Expected:
#  LGA              | ~80
#  SCHOOL_CATCHMENT | hundreds
#  SUBURB           | hundreds

psql postgresql://parceliq:$PG_PASS@localhost:15432/parceliq -c "
  SELECT count(*) FROM schools WHERE state = 'VIC';
"
# Expected: thousands

psql postgresql://parceliq:$PG_PASS@localhost:15432/parceliq -c "
  SELECT count(*) FROM properties WHERE state = 'VIC';
"
# Expected: millions (matching G-NAF count)

# Kill the port-forward
kill %1
```

---

## 6. Re-Deployment (Code Updates)

For subsequent deploys after code changes:

```bash
# 1. Build updated images with a new tag
make build-docker tag=v1.0.1

# 2. Push and rolling-update all deployments
make deploy tag=v1.0.1 REGISTRY=$REGISTRY

# 3. Verify
make k8s-status
```

### Partial Updates

If only one service changed, you can skip rebuilding everything:

```bash
# Rebuild just the changed service
docker build -t $REGISTRY/ozpr-public-api:v1.0.1 services/public-api/
docker push $REGISTRY/ozpr-public-api:v1.0.1

# Update just that deployment
IMAGE_TAG=v1.0.1 REGISTRY=$REGISTRY envsubst '$$IMAGE_TAG $$REGISTRY' \
  < infra/k8s/apps/public-api.yaml | kubectl apply -f -

# Restart pods to pull new image
kubectl rollout restart deploy/public-api -n ozpropertyreport
kubectl rollout status deploy/public-api -n ozpropertyreport
```

### Secrets Update

If secrets change (new API key, rotated token):

```bash
# Edit .env with new values, then:
make k8s-secrets

# Restart pods to pick up new secret values
kubectl rollout restart deploy/public-api -n ozpropertyreport
kubectl rollout restart deploy/admin-backend -n ozpropertyreport
# ... restart any pods that use the changed secrets
```

### Schema Migration Only

If only DB migrations changed:

```bash
# Rebuild just the migration image
docker build -t $REGISTRY/ozpr-db-migrate:v1.0.1 shared/db-migrations/
docker push $REGISTRY/ozpr-db-migrate:v1.0.1

# Re-run the migration Job
kubectl delete job db-migrate -n ozpropertyreport --ignore-not-found
IMAGE_TAG=v1.0.1 REGISTRY=$REGISTRY envsubst '$$IMAGE_TAG $$REGISTRY' \
  < infra/k8s/jobs/db-migrate.yaml | kubectl apply -f -
kubectl wait --for=condition=complete job/db-migrate -n ozpropertyreport --timeout=180s
```

---

## 7. Troubleshooting

### Pod Status Issues

| Symptom | Likely Cause | Diagnosis | Fix |
|---|---|---|---|
| `ImagePullBackOff` | Registry auth or wrong image name | `kubectl describe pod <name> -n ozpropertyreport` — check Events for pull error | `docker login`, verify `REGISTRY` matches pushed images, check if `imagePullSecrets` needed |
| `CrashLoopBackOff` | App fails to start (missing env var, bad config) | `make k8s-logs svc=<service>` — check startup error | Fix `.env` → `make k8s-secrets` → `kubectl rollout restart deploy/<service> -n ozpropertyreport` |
| `Pending` | No node has enough resources, or PVC can't bind | `kubectl describe pod <name>` — check Events for scheduling failure | Check node resources: `kubectl top nodes`, check PVC: `kubectl get pvc -n ozpropertyreport` |
| `Init:Error` or `Init:CrashLoopBackOff` | Init container failed | `kubectl logs <pod> -c <init-container> -n ozpropertyreport` | Fix the init container issue, usually a dependency not ready |
| `ErrImagePull` | Image doesn't exist in registry | `docker images \| grep ozpr` — is it built? `docker push` — is it pushed? | Build and push the missing image |

### Migration Job Failures

```bash
# Check migration logs
kubectl logs job/db-migrate -n ozpropertyreport

# Common issues:
# 1. "connection refused" → Postgres not ready yet
#    Fix: wait for Postgres, then re-run:
kubectl rollout status statefulset/postgres -n ozpropertyreport
kubectl delete job db-migrate -n ozpropertyreport --ignore-not-found
IMAGE_TAG=$TAG REGISTRY=$REGISTRY envsubst '$$IMAGE_TAG $$REGISTRY' \
  < infra/k8s/jobs/db-migrate.yaml | kubectl apply -f -

# 2. "FATAL: password authentication failed" → wrong DATABASE_URL_SYNC
#    Fix: check .env, make k8s-secrets, re-run migration

# 3. "Can't locate revision" → migration file missing from image
#    Fix: rebuild ozpr-db-migrate with the correct shared/db-migrations content
```

### TLS Certificate Issues

```bash
# Check certificate status
kubectl get certificate -n ozpropertyreport
kubectl describe certificate public-web-tls -n ozpropertyreport

# Check cert-manager logs
kubectl logs -n cert-manager deploy/cert-manager --tail=50

# Common issues:
# 1. "Waiting for HTTP-01 challenge" → DNS not pointing to cluster
#    Fix: create A records, wait for propagation (5-10 min)
#
# 2. "too many certificates already issued" → Let's Encrypt rate limit
#    Fix: wait 1 hour, or use staging issuer temporarily
#
# 3. Certificate stuck in "Issuing" → Traefik not routing ACME challenge
#    Fix: kubectl get ingress -A — ensure no conflicting IngressRoutes
```

### Connectivity Issues

```bash
# ── public-web can't reach public-api ─────────────────────────────────────────
kubectl exec -it deploy/public-web -n ozpropertyreport -- \
  wget -qO- --timeout=5 http://public-api:8080/api/health
# If this fails, check public-api pod is Running and Service exists:
kubectl get svc public-api -n ozpropertyreport
kubectl get endpoints public-api -n ozpropertyreport
# Endpoints should show a pod IP — if empty, labels don't match

# ── admin-web can't reach admin-backend ───────────────────────────────────────
kubectl exec -it deploy/admin-web -n ozpropertyreport -- \
  wget -qO- --timeout=5 http://admin-backend:8082/health
# If blocked: check NetworkPolicy allows admin-web → admin-backend
kubectl get networkpolicy -n ozpropertyreport -o yaml

# ── Celery workers not picking up tasks ───────────────────────────────────────
# Check Redis connectivity from worker
kubectl exec -it deploy/scraper-worker -n ozpropertyreport -- \
  python -c "import redis; r=redis.from_url('redis://redis:6379/0'); print(r.ping())"
# Check worker logs for connection errors
make k8s-logs svc=scraper-worker
```

### Storage Issues

```bash
# Check PVC status (all should be Bound)
kubectl get pvc -n ozpropertyreport
# If Pending: Longhorn may not have enough space
kubectl get nodes -o custom-columns=NAME:.metadata.name,DISK:.status.allocatable.ephemeral-storage

# Check Longhorn volumes
kubectl get volumes.longhorn.io -n longhorn-system

# Postgres data directory permissions
kubectl exec -it statefulset/postgres -n ozpropertyreport -- \
  ls -la /var/lib/postgresql/data/
```

### Performance Issues

```bash
# Node resource usage
kubectl top nodes

# Pod resource usage
kubectl top pods -n ozpropertyreport --sort-by=memory

# If a pod is OOMKilled (check Events in describe):
kubectl describe pod <name> -n ozpropertyreport | grep -A5 "Last State"
# Increase memory limits in the manifest, rebuild, redeploy
```

### Nuclear Options

```bash
# Restart a single service
kubectl rollout restart deploy/<service> -n ozpropertyreport

# Restart ALL application pods (infrastructure stays running)
for svc in public-api admin-backend public-web admin-web scraper-worker llm-parser-worker; do
  kubectl rollout restart deploy/$svc -n ozpropertyreport
done

# Full teardown and redeploy (WARNING: destroys all data)
make k8s-teardown    # type 'yes' to confirm
make deploy tag=$TAG REGISTRY=$REGISTRY
make k8s-init-data ...
```

---

## 8. Quick Reference

### Makefile Targets

| Command | Description |
|---|---|
| `make build-docker tag=<tag>` | Build all 7 Docker images |
| `make deploy tag=<tag> REGISTRY=<reg>` | Push images and deploy everything |
| `make k8s-secrets` | Apply secrets from `.env` to cluster |
| `make k8s-status` | Show all resources in namespace |
| `make k8s-logs svc=<name>` | Tail logs for a deployment |
| `make k8s-admin` | Port-forward admin-web, MinIO, Flower |
| `make k8s-hosts` | Print `/etc/hosts` entries |
| `make k8s-init-data ...` | Bootstrap VIC reference data |
| `make k8s-import-gnaf ...` | Run step 5 (G-NAF import) independently |
| `make k8s-create-properties ...` | Run step 6 (property creation) independently |
| `make k8s-teardown` | Delete everything (irreversible!) |

### Key Namespace Resources

| Resource | Name | Notes |
|---|---|---|
| Namespace | `ozpropertyreport` | All resources live here |
| Secret | `ozpr-secrets` | All sensitive values |
| ConfigMap | `ozpr-config` | Non-sensitive config |
| StatefulSet | `postgres` | Postgres 16 + PostGIS |
| Deployment | `redis` | Redis 7 with AOF |
| Deployment | `minio` | S3-compatible storage |
| Deployment | `flower` | Celery monitoring UI |
| Deployment | `public-api` | FastAPI, port 8080 |
| Deployment | `admin-backend` | FastAPI, port 8082 (no ingress) |
| Deployment | `public-web` | Next.js, port 3000 |
| Deployment | `admin-web` | Next.js, port 3001 (no ingress) |
| Deployment | `scraper-worker` | Celery + Playwright |
| Deployment | `llm-parser-worker` | Celery + LLM API |
| Job | `db-migrate` | Alembic migrations |

### Useful kubectl Commands

```bash
# Quick pod overview
kubectl get pods -n ozpropertyreport -o wide

# Watch pods in real-time
kubectl get pods -n ozpropertyreport -w

# Get events sorted by time (great for debugging)
kubectl get events -n ozpropertyreport --sort-by='.lastTimestamp' | tail -20

# Shell into a pod
kubectl exec -it deploy/<service> -n ozpropertyreport -- sh

# Port-forward Postgres for direct SQL
kubectl port-forward -n ozpropertyreport svc/postgres 15432:5432
psql postgresql://parceliq:PASSWORD@localhost:15432/parceliq
```
