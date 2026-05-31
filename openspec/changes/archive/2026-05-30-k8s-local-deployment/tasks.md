## 1. Prerequisite: Admin Web Dockerfile

- [x] 1.1 Add `apps/admin-web/Dockerfile` with multi-stage build (deps → builder → runner), mirroring `apps/public-web/Dockerfile`
- [x] 1.2 Verify `next.config.js` in both `apps/public-web` and `apps/admin-web` has `output: 'standalone'`; add it if missing
- [ ] 1.3 Smoke-test: `docker build -t ozpr-admin-web:dev apps/admin-web/` builds successfully on developer machine

## 2. K8s Manifests — Namespace & Shared Config

- [x] 2.1 Create `infra/k8s/namespace.yaml` (namespace `ozpropertyreport`)
- [x] 2.2 Create `infra/k8s/configmap.yaml` with non-sensitive env vars: `ENVIRONMENT`, `LOG_LEVEL`, internal service hostnames (`POSTGRES_HOST=postgres`, `REDIS_URL=redis://redis:6379/0`, `MINIO_ENDPOINT=http://minio:9000`), app ports
- [x] 2.3 Create `infra/k8s/secrets.example.yaml` with all required secret keys set to `<PLACEHOLDER>` — committed as documentation
- [x] 2.4 Add `infra/k8s/secrets.yaml` to `.gitignore`

## 3. K8s Manifests — Persistent Volumes

- [x] 3.1 Create `infra/k8s/pvc/postgres-pvc.yaml` (10Gi, ReadWriteOnce, storageClassName: longhorn)
- [x] 3.2 Create `infra/k8s/pvc/redis-pvc.yaml` (2Gi, ReadWriteOnce, storageClassName: longhorn, for AOF persistence)
- [x] 3.3 Create `infra/k8s/pvc/minio-pvc.yaml` (10Gi, ReadWriteOnce, storageClassName: longhorn)

## 4. K8s Manifests — Infrastructure Services

All infrastructure manifests should include explicit CPU and memory resource requests/limits using the Cluster-Fitted Profile values.

- [x] 4.1 Create `infra/k8s/infrastructure/postgres.yaml` (StatefulSet `postgis/postgis:16-3.4` + ClusterIP Service on port 5432; use PVC from 3.1; resource requests `250m`/`512Mi`, limits `1000m`/`2Gi`)
- [x] 4.2 Create `infra/k8s/infrastructure/redis.yaml` (Deployment `redis:7-alpine` + ClusterIP Service on port 6379; use PVC from 3.2 with AOF `appendonly yes`; resource requests `50m`/`64Mi`, limits `200m`/`256Mi`)
- [x] 4.3 Create `infra/k8s/infrastructure/minio.yaml` (Deployment `minio/minio:latest` + ClusterIP Service on ports 9000/9001; use PVC from 3.3; resource requests `100m`/`128Mi`, limits `500m`/`512Mi`)
- [x] 4.4 Create `infra/k8s/infrastructure/flower.yaml` (Deployment `mher/flower:2.0` + ClusterIP Service on port 5555; reads `CELERY_BROKER_URL` from ConfigMap; resource requests `25m`/`48Mi`, limits `100m`/`128Mi`)

## 5. K8s Manifests — DB Migration Job

- [x] 5.1 Create `infra/k8s/jobs/db-migrate.yaml` — K8s Job using `${REGISTRY}/ozpr-public-api:${IMAGE_TAG}`, CMD `["alembic", "upgrade", "head"]` in the `shared/db-migrations` directory, `restartPolicy: Never`, env from `ozpr-secrets`

## 6. K8s Manifests — Application Services

All application Deployment manifests use `${REGISTRY}/ozpr-<svc>:${IMAGE_TAG}` as the image (substituted by `envsubst` in `make deploy`), specify `imagePullPolicy: Always`, and include CPU and memory resource requests/limits matching the Cluster-Fitted Profile.

- [x] 6.1 Create `infra/k8s/apps/public-api.yaml` (Deployment + ClusterIP Service port 8080; env from `ozpr-secrets` + `ozpr-config`; resources: requests `150m`/`192Mi`, limits `500m`/`512Mi`)
- [x] 6.2 Create `infra/k8s/apps/admin-backend.yaml` (Deployment + ClusterIP Service port 8082; env from `ozpr-secrets` + `ozpr-config`; resources: requests `100m`/`128Mi`, limits `250m`/`384Mi`)
- [x] 6.3 Create `infra/k8s/apps/public-web.yaml` (Deployment + ClusterIP Service port 3000; `NEXT_PUBLIC_API_URL` injected from ConfigMap; resources: requests `100m`/`128Mi`, limits `500m`/`512Mi`)
- [x] 6.4 Create `infra/k8s/apps/admin-web.yaml` (Deployment + ClusterIP Service port 3001; `ADMIN_BACKEND_URL=http://admin-backend:8082` from ConfigMap; resources: requests `100m`/`128Mi`, limits `500m`/`512Mi`)
- [x] 6.5 Create `infra/k8s/apps/scraper-worker.yaml` (Deployment, no Service; env from `ozpr-secrets`; resources: requests `200m`/`384Mi`, limits `1000m`/`1Gi`)
- [x] 6.6 Create `infra/k8s/apps/llm-parser-worker.yaml` (Deployment, no Service; env from `ozpr-secrets`; resources: requests `100m`/`128Mi`, limits `500m`/`512Mi`)

## 7. K8s Manifests — Ingress & Network Policy

- [x] 7.1 Create `infra/k8s/ingress/public-web-ingress.yaml` (standard Ingress, `ingressClassName: traefik`, host `ozpropertyreport.com` → public-web:3000, annotation `cert-manager.io/cluster-issuer: letsencrypt-prod`, tls secretName `public-web-tls`)
- [x] 7.2 Create `infra/k8s/ingress/public-api-ingress.yaml` (standard Ingress, `ingressClassName: traefik`, host `api.ozpropertyreport.com` → public-api:8080, annotation `cert-manager.io/cluster-issuer: letsencrypt-prod`, tls secretName `public-api-tls`)
- [x] 7.3 Create `infra/k8s/network-policies/admin-backend-isolation.yaml` — deny all ingress to `admin-backend` except from pods with label `app: admin-web` on port 8082

## 8. Makefile Targets

- [x] 8.1 Add `REGISTRY ?= ghcr.io/your-org` variable at the top of the Makefile (with comment: override via env or `make ... REGISTRY=yourregistry`)
- [x] 8.2 Add `build-docker` target: builds all 6 images as `$(REGISTRY)/ozpr-<svc>:$(tag)`; requires `tag` param; prints each image name as it builds
- [x] 8.3 Add `deploy` target that:
  - Validates `tag` param is provided and `REGISTRY` is not the default placeholder
  - Prints current kubectl context and prompts `[Enter to continue, Ctrl+C to abort]`
  - `docker push`es all 6 images
  - `kubectl apply -f infra/k8s/namespace.yaml`
  - `kubectl apply -f infra/k8s/configmap.yaml`
  - Runs `make k8s-secrets` (applies secrets from `.env`)
  - `kubectl apply -f infra/k8s/pvc/`
  - `kubectl apply -f infra/k8s/infrastructure/`
  - `kubectl rollout status statefulset/postgres -n ozpropertyreport`
  - Deletes existing `db-migrate` Job, applies fresh one, `kubectl wait --for=condition=complete --timeout=180s`
  - `envsubst` → `kubectl apply` all 6 application Deployment manifests with `IMAGE_TAG=$(tag) REGISTRY=$(REGISTRY)`
  - `kubectl apply -f infra/k8s/ingress/`
  - `kubectl apply -f infra/k8s/network-policies/`
- [x] 8.4 Add `k8s-secrets` target: `kubectl create secret generic ozpr-secrets --from-env-file=.env -n ozpropertyreport --dry-run=client -o yaml | kubectl apply -f -`
- [x] 8.5 Add `k8s-status` target: `kubectl get all -n ozpropertyreport`
- [x] 8.6 Add `k8s-logs` target: `kubectl logs -f -n ozpropertyreport deploy/$(svc) --tail=100` (requires `svc` param)
- [x] 8.7 Add `k8s-hosts` target: fetches K3s node external IP via `kubectl get nodes -o wide` and prints `/etc/hosts` entries for `ozpropertyreport.com` and `api.ozpropertyreport.com`
- [x] 8.8 Add `k8s-admin` target: runs `kubectl port-forward` for admin-web (localhost:3001), minio console (localhost:9001), and flower (localhost:5555) in background, prints access URLs
- [x] 8.9 Add `k8s-teardown` target: prints warning and prompts confirmation, then `kubectl delete namespace ozpropertyreport`
- [x] 8.10 Add `k8s-init-data` target that:
  - Validates `lga_source`, `suburb_source`, `catchment_source`, `school_source`, `gnaf_source` params are provided
  - Starts `kubectl port-forward` for Postgres (cluster 5432 → localhost:15432) in background
  - Reads DB credentials from `ozpr-secrets` K8s Secret via `kubectl get secret`
  - Constructs `DATABASE_URL=postgresql://<user>:<pass>@localhost:15432/<db>`
  - Runs `import_spatial_zones.py --type LGA --source $(lga_source) --state VIC`
  - Runs `import_spatial_zones.py --type SUBURB --source $(suburb_source) --state VIC`
  - Runs `import_spatial_zones.py --type SCHOOL_CATCHMENT --source $(catchment_source) --state VIC`
  - Runs `import_schools.py --source $(school_source) --state VIC --link-catchments`
  - Runs `import_gnaf.py --state VIC --source $(gnaf_source)`
  - Runs `create_properties_from_gnaf.py --state VIC`
  - Starts `kubectl port-forward` for MinIO (cluster 9000 → localhost:19000) in background
  - Runs `create_buckets.sh` (with MinIO endpoint overridden to localhost:19000)
  - Kills all port-forwards and prints summary
  - Each step exits on failure (set -e)
- [x] 8.11 Add all new targets to the `help` output with descriptions

## 9. Documentation

- [x] 9.1 Add "Deploying to Remote K3s" section in `docs/09-local-dev.md` covering: prerequisites (`docker` login + `kubectl` configured), `REGISTRY` setup, `make build-docker tag=X`, `make deploy tag=X`, DNS requirements, and troubleshooting
- [x] 9.2 Add `infra/k8s/secrets.example.yaml` comment header with instructions for first-time setup
- [ ] 9.3 Update `QUICKSTART.md` with the two-command deploy workflow and `REGISTRY` prerequisite
- [x] 9.4 Update `docs/01-system-architecture.md` to note that `infra/k8s/` manifests are committed

## 10. Smoke Test

- [ ] 10.1 `make build-docker tag=dev` — all 6 images build without error on developer machine
- [ ] 10.2 `make k8s-secrets` — secret `ozpr-secrets` applied to remote cluster with correct keys
- [ ] 10.3 `make deploy tag=dev REGISTRY=<your-registry>` — all pods reach `Running` state
- [ ] 10.4 `kubectl get pods -n ozpropertyreport` — confirm all pods Running, no CrashLoopBackOff
- [ ] 10.5 Verify public-web is reachable: `curl -H "Host: ozpropertyreport.com" https://<K3s-node-IP>/`
- [ ] 10.6 Verify public-api docs: `curl -H "Host: api.ozpropertyreport.com" https://<K3s-node-IP>/docs`
- [ ] 10.7 Verify admin console loads via port-forward: `make k8s-admin`, then browse `http://localhost:3001`
- [ ] 10.8 Verify NetworkPolicy: `kubectl exec -it deploy/public-web -n ozpropertyreport -- wget -q --timeout=3 http://admin-backend:8082/stats` — must timeout/refuse
- [ ] 10.9 `make k8s-teardown` — cleanly removes all resources; `kubectl get ns ozpropertyreport` returns NotFound

## 11. Data Initialization Smoke Test

- [ ] 11.1 `make k8s-init-data lga_source=<path> suburb_source=<path> catchment_source=<path> school_source=<path> gnaf_source=<path>` — runs to completion without error
- [ ] 11.2 Verify LGA data: port-forward Postgres, run `SELECT count(*) FROM spatial_zones WHERE zone_type='LGA' AND state='VIC'` — expect ~80 rows
- [ ] 11.3 Verify suburb data: `SELECT count(*) FROM spatial_zones WHERE zone_type='SUBURB' AND state='VIC'` — expect hundreds of rows
- [ ] 11.4 Verify school catchments: `SELECT count(*) FROM spatial_zones WHERE zone_type='SCHOOL_CATCHMENT' AND state='VIC'` — expect hundreds of rows
- [ ] 11.5 Verify school locations: `SELECT count(*) FROM schools WHERE state='VIC'` — expect thousands of rows
- [ ] 11.6 Verify G-NAF data: `SELECT count(*) FROM gnaf_addresses WHERE state='VIC'` — expect millions of rows
- [ ] 11.7 Verify properties: `SELECT count(*) FROM properties WHERE state='VIC'` — expect same order as G-NAF
- [ ] 11.8 Verify MinIO buckets: `make k8s-admin`, browse `http://localhost:9001`, confirm `raw-scrape-cache` and `ozpr-db-backups` buckets exist
