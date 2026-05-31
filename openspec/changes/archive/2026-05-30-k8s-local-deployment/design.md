## Context

The existing architecture (`docs/01-system-architecture.md`) defines the target K8s topology: a single `ozpropertyreport` namespace on K3s with two internet-facing apps behind Traefik and five internal-only services. Dockerfiles already exist for all services except `apps/admin-web`.

**Deployment model:** Developer machine builds images with Docker, pushes them to a container registry (developer is assumed to be already logged in), then applies K8s manifests to a remote K3s cluster via `kubectl` (KUBECONFIG already configured). No CI/CD pipeline is involved.

This design translates the documented architecture into concrete K8s manifests and Makefile targets.

## Goals / Non-Goals

**Goals**
- All 6 application services deployable to a remote K3s cluster via `make build-docker tag=<tag> && make deploy tag=<tag>`
- Configurable `REGISTRY` variable — developer sets their own registry prefix, Makefile uses it for image names
- All secrets applied to the remote cluster via `kubectl` from the local `.env` file — never committed to git
- Admin backend NetworkPolicy: only admin-web pod may reach port 8082 (enforced at K8s level)
- DB migrations run as a K8s Job and complete before application pods start
- Infrastructure services (Postgres/PostGIS, Redis, MinIO, Flower) run in-cluster with PVCs for data persistence

**Non-Goals**
- CI/CD pipeline setup (GitHub Actions, ArgoCD, etc.)
- Helm chart packaging
- Production resource limits tuning / HPA
- Multi-environment (staging/prod) manifests — single environment, parameterised by `tag`
- TLS certificate automation (Traefik with self-signed or existing cert is acceptable)

## Decisions

### Decision 1: Namespace

Single namespace `ozpropertyreport`. All manifests use `namespace: ozpropertyreport`. NetworkPolicies and RBAC are namespace-scoped.

### Decision 2: Image naming and registry

```
$(REGISTRY)/ozpr-public-web:<tag>
$(REGISTRY)/ozpr-admin-web:<tag>
$(REGISTRY)/ozpr-public-api:<tag>
$(REGISTRY)/ozpr-admin-backend:<tag>
$(REGISTRY)/ozpr-scraper-worker:<tag>
$(REGISTRY)/ozpr-llm-parser-worker:<tag>
```

`REGISTRY` defaults to `ghcr.io/your-org` but must be overridden per-developer. Set it in `.env` or export it: `export REGISTRY=myregistry.io/myorg`. The Makefile reads it with `REGISTRY ?= ghcr.io/your-org`.

`imagePullPolicy: Always` on all application containers so the cluster always pulls the latest pushed image for a given tag.

### Decision 3: Secret management

A `make k8s-secrets` Makefile target applies a K8s Secret directly to the remote cluster from the local `.env`:

```bash
kubectl create secret generic ozpr-secrets \
  --from-env-file=.env \
  --namespace=ozpropertyreport \
  --dry-run=client -o yaml | kubectl apply -f -
```

The generated YAML is never written to disk (piped directly). Only `infra/k8s/secrets.example.yaml` is committed — with all values replaced by `<PLACEHOLDER>` — as a reference for required keys.

Non-sensitive configuration (service hostnames, ports, environment name) goes in a ConfigMap `ozpr-config`.

### Decision 4: Infrastructure services in-cluster

All infrastructure services run inside K3s. The remote K3s cluster replaces Docker Compose for production deployment:

| Service | Kind | Storage | StorageClass |
|---|---|---|---|
| Postgres/PostGIS 16 | StatefulSet | PVC 10Gi | longhorn |
| Redis 7 | Deployment | PVC 2Gi (AOF persistence) | longhorn |
| MinIO | Deployment | PVC 10Gi | longhorn |
| Flower | Deployment | none | — |

All infrastructure services use ClusterIP Services (not exposed externally except MinIO console via IngressRoute for admin access).

### Decision 5: Application service topology

| Service | Kind | Replicas | Service type |
|---|---|---|---|
| public-web | Deployment | 1 | ClusterIP (Traefik IngressRoute) |
| admin-web | Deployment | 1 | ClusterIP (Traefik IngressRoute) |
| public-api | Deployment | 1 | ClusterIP (Traefik IngressRoute) |
| admin-backend | Deployment | 1 | ClusterIP only — NO ingress |
| scraper-worker | Deployment | 1 | None (no Service needed) |
| llm-parser-worker | Deployment | 1 | None (no Service needed) |

### Decision 6: NetworkPolicy for admin-backend

```yaml
kind: NetworkPolicy
spec:
  podSelector:
    matchLabels:
      app: admin-backend
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: admin-web
      ports:
        - port: 8082
  policyTypes:
    - Ingress
```

This enforces the hard architecture rule from AGENTS.md: admin-backend has zero internet exposure regardless of any Traefik misconfiguration.

### Decision 7: DB migration Job

A Kubernetes Job `db-migrate` runs `alembic upgrade head` using the `ozpr-public-api` image (which has `psycopg2` and the migration files). Applied before application Deployments in `make deploy`:

```bash
# Delete any previous completed/failed job
kubectl delete job db-migrate -n ozpropertyreport --ignore-not-found
# Apply fresh job
kubectl apply -f infra/k8s/jobs/db-migrate.yaml
# Wait up to 3 minutes
kubectl wait --for=condition=complete job/db-migrate -n ozpropertyreport --timeout=180s
```

### Decision 8: Image tag substitution in manifests

All Deployment manifests use an `IMAGE_TAG` placeholder. `make deploy` pipes manifests through `envsubst` before applying:

```bash
IMAGE_TAG=$(tag) REGISTRY=$(REGISTRY) envsubst < infra/k8s/apps/public-web.yaml | kubectl apply -f -
```

This avoids Helm or Kustomize as a dependency for the initial implementation.

### Decision 9: Ingress (standard K8s Ingress with Traefik)

The cluster runs **Traefik v2.11.20** (K3s built-in) exposed as a `LoadBalancer` service via ServiceLB/klipper on all 3 nodes (`192.168.10.185`, `192.168.10.186`, `192.168.10.187`). Both Traefik-native `IngressRoute` CRDs and standard `Ingress` resources are supported.

**Decision: Use standard `Ingress` with `ingressClassName: traefik`** — matching the existing cluster pattern (`stirling-pdf` namespace) and remaining portable if the ingress controller is ever replaced.

**Internet-facing Ingress** (host-based routing with TLS):
- `ozpropertyreport.com` → public-web:3000
- `api.ozpropertyreport.com` → public-api:8080

**No Ingress — port-forward only** (admin surfaces have zero internet exposure):
- `admin-web:3001` → access via `kubectl port-forward deploy/admin-web 3001:3001 -n ozpropertyreport`
- `minio:9001` (console) → access via `kubectl port-forward deploy/minio 9001:9001 -n ozpropertyreport`
- `flower:5555` → access via `kubectl port-forward deploy/flower 5555:5555 -n ozpropertyreport`

A `make k8s-admin` target wraps the port-forward commands for convenience.

TLS: Enabled via **cert-manager** using the existing `letsencrypt-prod` ClusterIssuer (already working on the cluster for `stirling-pdf`). Each public Ingress resource includes:

```yaml
metadata:
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: traefik
  tls:
    - hosts:
        - <hostname>
      secretName: <service>-tls   # cert-manager auto-creates this
  rules:
    - host: <hostname>
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: <service>
                port:
                  number: <port>
```

TLS secret names:

| Ingress | Host | Secret |
|---|---|---|
| public-web | `ozpropertyreport.com` | `public-web-tls` |
| public-api | `api.ozpropertyreport.com` | `public-api-tls` |

> **Prerequisite:** The domains must have real DNS A records pointing to the K3s node IPs (`192.168.10.185-187`) for the ACME HTTP-01 challenge to succeed. For local `/etc/hosts` testing without real DNS, TLS will not work — use `--insecure` or skip cert-manager annotations temporarily. `make k8s-hosts` prints the required entries.

### Decision 10: admin-web Dockerfile

The missing `apps/admin-web/Dockerfile` follows the same multi-stage Next.js pattern as `apps/public-web/Dockerfile`:
1. `deps` stage: `node:22-alpine` + `pnpm install --frozen-lockfile`
2. `builder` stage: `NEXT_TELEMETRY_DISABLED=1 pnpm build`
3. `runner` stage: `node:22-alpine`, copies `.next/standalone` + `.next/static`

Both Next.js apps must have `output: 'standalone'` in `next.config.js` for the standalone runner to work.

### Decision 11: Resource Allocations

All pods specify explicit `resources` blocks tuned for the target cluster: **3 nodes × 4 vCPU / 16 GiB RAM** (12 vCPU / ~47 GiB total allocatable). After reserving capacity for K3s system workloads (Traefik, CoreDNS, Longhorn, local-path-provisioner, metrics-server — typically ~2–3 vCPU / 4–6 GiB across the cluster), the application workloads below comfortably fit.

#### Resource Allocation Table (Cluster-Fitted Profile)

| Service | Requests | Limits | Notes |
| :--- | :--- | :--- | :--- |
| **postgres** | 250m CPU / 512Mi | 1000m CPU / 2Gi | Heaviest infra service — bounded to 1 core |
| **redis** | 50m CPU / 64Mi | 200m CPU / 256Mi | Lightweight; AOF persistence |
| **minio** | 100m CPU / 128Mi | 500m CPU / 512Mi | Object storage for scraped documents |
| **flower** | 25m CPU / 48Mi | 100m CPU / 128Mi | Monitoring UI only |
| **public-web** | 100m CPU / 128Mi | 500m CPU / 512Mi | Next.js standalone server |
| **admin-web** | 100m CPU / 128Mi | 500m CPU / 512Mi | Next.js standalone server |
| **public-api** | 150m CPU / 192Mi | 500m CPU / 512Mi | FastAPI — handles investor queries |
| **admin-backend** | 100m CPU / 128Mi | 250m CPU / 384Mi | FastAPI — internal only |
| **scraper-worker** | 200m CPU / 384Mi | 1000m CPU / 1Gi | Playwright + Celery — needs burst CPU |
| **llm-parser-worker** | 100m CPU / 128Mi | 500m CPU / 512Mi | Celery — CPU-light (offloads to API) |
| **db-migrate (Job)** | 50m CPU / 64Mi | 250m CPU / 256Mi | Runs once per deploy, then exits |
| | | | |
| **Total Requests** | **1225m CPU / ~1.9 GiB** | — | ~10% of cluster CPU, ~4% of cluster RAM |
| **Total Limits** | — | **5300m CPU / ~6.5 GiB** | ~44% of cluster CPU, ~14% of cluster RAM |

**Rationale:** Requests are kept lean so the scheduler can place all 10 pods easily (even if they land on a single node they'd only need ~1.2 cores and ~1.9 GiB). Limits allow burst headroom for Postgres queries, scraper Playwright sessions, and API request spikes without letting any single pod monopolize a node.

### Decision 12: StorageClass

The cluster has both `local-path` and `longhorn` StorageClasses available. PVCs will use `longhorn` explicitly:

- **Why longhorn:** Provides replicated block storage across nodes, so data survives node failure. Supports `ReadWriteOnce` with automatic replica placement. The cluster has ~160–190 GiB free per node after existing PVCs.
- **PVC sizing (reduced from original):** Postgres 10Gi (down from 20Gi — sufficient for development/staging data), Redis 2Gi, MinIO 10Gi. Total: 22Gi new storage — well within available capacity.
- **Longhorn replica count:** Default (usually 3, one per node). Can be tuned via Longhorn StorageClass parameters if needed.

### Decision 13: Data Initialization on Cluster

After a fresh deploy, the database is empty (migrations create schema only). The bootstrap import pipeline from `docs/current_data_flow.md` must be run to seed reference data before the platform is usable. A `make k8s-init-data` target automates this, scoped to **VIC state only**:

1. **Port-forward** Postgres from the cluster to `localhost:15432` (avoids conflicting with any local Postgres on 5432)
2. **Import LGA boundaries** — `import_spatial_zones.py --type LGA --source <path> --state VIC`
3. **Import suburb boundaries** — `import_spatial_zones.py --type SUBURB --source <path> --state VIC`
4. **Import school catchment zones** — `import_spatial_zones.py --type SCHOOL_CATCHMENT --source <path> --state VIC`
5. **Import school locations** — `import_schools.py --source <path> --state VIC --link-catchments`
6. **Import G-NAF addresses** — `import_gnaf.py --state VIC --source <path>`
7. **Create properties from G-NAF** — `create_properties_from_gnaf.py --state VIC`
8. **Create MinIO buckets** — port-forward MinIO, run `create_buckets.sh`
9. **Kill port-forwards** and print summary

Each step runs sequentially and exits on failure. The user must provide paths to the source data files:

```bash
make k8s-init-data \
  lga_source=/path/to/LGA_2024_AUST_GDA2020.shp \
  suburb_source=/path/to/SAL_2021_AUST_GDA2020.shp \
  catchment_source=/path/to/school_catchments_vic.geojson \
  school_source=/path/to/vic_schools_2024.csv \
  gnaf_source=/path/to/gnaf_feb2026.zip
```

The `DATABASE_URL` is overridden to `postgresql://<user>:<pass>@localhost:15432/<db>` using credentials from the `ozpr-secrets` K8s Secret (read via `kubectl get secret`). The import scripts run locally using the `infra/scripts/.venv/` Python environment — they connect to the cluster DB through the port-forward tunnel.

> **Note:** This is a one-time bootstrap. Data files (G-NAF zip, ABS shapefiles, school CSVs) are not committed to the repo — they must be downloaded separately by the operator.

## File Layout

```
infra/k8s/
├── namespace.yaml
├── configmap.yaml
├── secrets.example.yaml          # Committed — placeholder values only
├── pvc/
│   ├── postgres-pvc.yaml         # 20Gi
│   ├── redis-pvc.yaml            # 2Gi
│   └── minio-pvc.yaml            # 10Gi
├── infrastructure/
│   ├── postgres.yaml             # StatefulSet + ClusterIP Service
│   ├── redis.yaml                # Deployment + ClusterIP Service
│   ├── minio.yaml                # Deployment + ClusterIP Service
│   └── flower.yaml               # Deployment + ClusterIP Service
├── apps/
│   ├── public-web.yaml           # Deployment + ClusterIP Service (IMAGE_TAG placeholder)
│   ├── admin-web.yaml            # Deployment + ClusterIP Service (IMAGE_TAG placeholder)
│   ├── public-api.yaml           # Deployment + ClusterIP Service (IMAGE_TAG placeholder)
│   ├── admin-backend.yaml        # Deployment + ClusterIP Service (IMAGE_TAG placeholder)
│   ├── scraper-worker.yaml       # Deployment only (IMAGE_TAG placeholder)
│   └── llm-parser-worker.yaml    # Deployment only (IMAGE_TAG placeholder)
├── ingress/
│   ├── public-web-ingress.yaml    # standard Ingress (ingressClassName: traefik, TLS)
│   └── public-api-ingress.yaml    # standard Ingress (ingressClassName: traefik, TLS)
├── network-policies/
│   └── admin-backend-isolation.yaml
└── jobs/
    └── db-migrate.yaml           # IMAGE_TAG placeholder
```

## Makefile Targets

```makefile
REGISTRY ?= ghcr.io/your-org    # Override via env or make ... REGISTRY=...
TAG       ?= latest              # Override via make ... tag=1.0.0

# Build all Docker images (developer must be logged into registry)
make build-docker tag=1.0.0

# Build + push + deploy to remote cluster (full workflow)
make deploy tag=1.0.0

# Apply secrets from .env to remote cluster
make k8s-secrets

# Supporting targets
make k8s-status                  # kubectl get all -n ozpropertyreport
make k8s-logs svc=<name>         # kubectl logs -f deploy/<name>
make k8s-hosts                   # Print /etc/hosts entries (K3s node IP + domains)
make k8s-admin                   # Port-forward admin-web (3001), minio console (9001), flower (5555)
make k8s-init-data               # Bootstrap VIC reference data (LGA, suburbs, G-NAF, properties, MinIO buckets)
make k8s-teardown                # kubectl delete namespace ozpropertyreport
```

`make build-docker tag=<tag>` builds all 6 images using `$(REGISTRY)/ozpr-<svc>:$(tag)`.

`make deploy tag=<tag>` orchestrates:
1. `docker push` all 6 images to the registry
2. `kubectl apply` namespace, configmap, secrets (via `make k8s-secrets`)
3. `kubectl apply` PVCs and infrastructure Deployments/StatefulSets
4. Wait for Postgres readiness: `kubectl rollout status statefulset/postgres`
5. Delete + apply `db-migrate` Job → `kubectl wait --for=condition=complete`
6. `envsubst` → `kubectl apply` for all 6 application Deployments
7. `kubectl apply` Ingress (public-web + public-api only) and NetworkPolicies

## Risks / Mitigations

1. **Risk:** `REGISTRY` not set — images pushed to wrong location
   - **Mitigation:** `make deploy` validates `REGISTRY` is not the default placeholder before pushing; prints clear error

2. **Risk:** `KUBECONFIG` not pointing to the correct remote cluster
   - **Mitigation:** `make deploy` prints current kubectl context at start: `kubectl config current-context`; developer confirms before proceeding

3. **Risk:** Next.js `output: standalone` not enabled in both apps
   - **Mitigation:** Check `next.config.js` in both apps as task 1.2; add `output: 'standalone'` if missing

4. **Risk:** `secrets.yaml` accidentally written to disk and committed
   - **Mitigation:** Secrets are piped directly via `--dry-run=client -o yaml | kubectl apply -f -` — never written to disk; `infra/k8s/secrets.yaml` added to `.gitignore` as a belt-and-suspenders guard

5. **Risk:** DB migration Job fails mid-deploy, leaving app pods running stale code
   - **Mitigation:** `kubectl wait --timeout=180s` — if migration fails, `make deploy` exits non-zero before applying application Deployments
