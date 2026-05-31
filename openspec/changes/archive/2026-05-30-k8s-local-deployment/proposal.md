## Why

OZ Property Report currently has no Kubernetes manifests. All seven application services (public-web, admin-web, public-api, admin-backend, scraper-worker, llm-parser-worker) are only runnable natively via `make dev-full`, relying on the developer's local Python/Node runtime. Infrastructure dependencies (Postgres, Redis, MinIO, Flower) run in Docker Compose.

To progress toward a production-ready platform and make the deployment process reproducible and environment-agnostic, we need:

- Docker images built from existing Dockerfiles for all application services and pushed to a container registry
- K8s manifests targeting a remote K3s cluster that mirrors the topology in `docs/01-system-architecture.md`
- A single Makefile ergonomic so any developer with `docker` login and `kubectl` configured can go from code to live cluster with two commands:
  ```
  make build-docker tag=1.0.0
  make deploy tag=1.0.0
  ```

**Deployment model:** Developer machine → `docker build` + `docker push` → container registry → remote K3s cluster pulls images + `kubectl apply` manifests. No CI/CD pipeline required.

This change does **not** require any new application code. It is purely infrastructure-as-code.

## What Changes

- **New:** `apps/admin-web/Dockerfile` — the only service currently missing a Dockerfile
- **New:** `infra/k8s/` directory with all K8s manifests (Deployments, Services, ConfigMaps, Secrets, NetworkPolicies, PersistentVolumeClaims, Ingress)
- **New:** K8s manifests for all 6 application services + 4 infrastructure services (Postgres/PostGIS, Redis, MinIO, Flower)
- **New:** `infra/k8s/network-policies/` — enforces Admin Backend is ClusterIP-only, reachable only from admin-web pod
- **Extend:** `Makefile` with `build-docker`, `deploy`, `k8s-status`, `k8s-logs`, `k8s-teardown` targets

## Capabilities

### New Capabilities

- `k8s-remote-deploy`: Full stack deployable to a remote K3s cluster from any developer machine via `make build-docker tag=X && make deploy tag=X`

### Modified Capabilities

- `dev-workflow`: Makefile extended with docker + k8s lifecycle targets (no existing targets modified)

## Impact

**Infrastructure**
- New `infra/k8s/` directory — all manifests committed to repo
- `infra/k8s/secrets.example.yaml` with placeholder values and instructions to generate the real Secret from `.env`
- A `make k8s-secrets` helper that applies a K8s Secret from the local `.env` file directly to the remote cluster (the generated YAML file itself is gitignored)
- Explicit CPU and memory resource requests/limits for all 10 services, tuned for the target 3-node K3s cluster (3×4 vCPU / 3×16 GiB RAM). Total requests sum to ~1.5 CPU / ~2.5 GiB, well within cluster capacity after accounting for K3s system workloads.
- PVCs use the `longhorn` StorageClass for replicated, persistent storage across nodes.

**Makefile**
- `REGISTRY` variable (default: `ghcr.io/your-org`) — configurable via environment or `make ... REGISTRY=myregistry.io/myorg`
- `make build-docker tag=<tag>` — builds all 6 service images tagged `$(REGISTRY)/ozpr-<service>:<tag>`
- `make deploy tag=<tag>` — pushes images, applies manifests, waits for DB migration Job to complete, rolls out application Deployments
- `make k8s-status` — `kubectl get all -n ozpropertyreport`
- `make k8s-logs svc=<service>` — tail logs for a named Deployment
- `make k8s-hosts` — prints required DNS entries (hostname → K3s node IP)
- `make k8s-admin` — port-forward admin-web, minio console, and flower to localhost
- `make k8s-init-data lga_source=... suburb_source=... gnaf_source=...` — bootstrap VIC reference data via port-forward to cluster Postgres
- `make k8s-teardown` — delete the namespace (hard reset)

**Network / Security**
- Only `public-web` and `public-api` have internet-facing Ingress (with TLS via cert-manager/letsencrypt-prod)
- `admin-web`, `minio console`, and `flower` have **no ingress** — accessible only via `kubectl port-forward` (`make k8s-admin`)
- K8s NetworkPolicy ensures `admin-backend` is only reachable from `admin-web` pod (matches architecture doc rule)
- All secrets applied directly to the remote cluster via `kubectl`; never committed to git

## Rollout Strategy

1. Add missing `apps/admin-web/Dockerfile`
2. Create `infra/k8s/` manifests (namespace → config/secrets → PVCs → infrastructure → migration Job → application services → ingress → network policies)
3. Extend Makefile with `build-docker` and `deploy` targets
4. Smoke-test end-to-end: `make build-docker tag=dev && make deploy tag=dev` against a remote K3s cluster with `KUBECONFIG` pointing to it
5. Validate admin-web → admin-backend connectivity and public-api external access
