# =============================================================================
# ParcelIQ — Makefile
# Infrastructure, database, Python services, Next.js apps, and Docker operations.
# =============================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Docker registry for K8s image publishing
# Override via environment or: make build-docker tag=X REGISTRY=myregistry.io/myorg
REGISTRY ?= ghcr.io/your-org
INTERNAL_API_URL ?= http://public-api:8080

# Load .env if it exists (for POSTGRES_USER, etc.)
ifneq (,$(wildcard .env))
	include .env
	export
endif

# Database URL for Alembic (plain psycopg2 — not asyncpg)
DB_URL ?= postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@localhost:$(POSTGRES_PORT)/$(POSTGRES_DB)

# ─── Infrastructure ──────────────────────────────────────────────────────────

.PHONY: infra-up
infra-up: ## Start Docker infrastructure (Postgres, Redis, MinIO, Flower)
	docker compose up -d
	@echo "Waiting for services to become healthy..."
	@docker compose ps

.PHONY: infra-down
infra-down: ## Stop Docker infrastructure
	docker compose down

.PHONY: infra-reset
infra-reset: ## Stop Docker infrastructure AND wipe all data volumes
	docker compose down -v
	@echo "All volumes destroyed. Run 'make infra-up && make db-migrate' to start fresh."

.PHONY: infra-status
infra-status: ## Show Docker infrastructure status
	docker compose ps

.PHONY: infra-logs
infra-logs: ## Tail infrastructure logs (all containers)
	docker compose logs -f --tail=50

# ─── Database ────────────────────────────────────────────────────────────────

.PHONY: db-migrate
db-migrate: ## Run all Alembic migrations (upgrade to head)
	cd shared/db-migrations && DATABASE_URL=$(DB_URL) uv run alembic upgrade head

.PHONY: db-rollback
db-rollback: ## Roll back one Alembic migration
	cd shared/db-migrations && DATABASE_URL=$(DB_URL) uv run alembic downgrade -1

.PHONY: db-revision
db-revision: ## Create a new Alembic migration (usage: make db-revision msg="add foo column")
	@if [ -z "$(msg)" ]; then echo "Usage: make db-revision msg=\"description\""; exit 1; fi
	cd shared/db-migrations && DATABASE_URL=$(DB_URL) uv run alembic revision --autogenerate -m "$(msg)"

.PHONY: db-history
db-history: ## Show Alembic migration history
	cd shared/db-migrations && DATABASE_URL=$(DB_URL) uv run alembic history --verbose

.PHONY: db-shell
db-shell: ## Open psql shell to local database
	psql $(DB_URL)

.PHONY: db-reset
db-reset: infra-reset infra-up ## Destroy DB volume, restart infra, re-run migrations
	@echo "Waiting for Postgres to be ready..."
	@until docker compose exec -T postgres pg_isready -U $(POSTGRES_USER) -d $(POSTGRES_DB) 2>/dev/null; do sleep 1; done
	$(MAKE) db-migrate

# ─── MinIO ───────────────────────────────────────────────────────────────────

.PHONY: minio-buckets
minio-buckets: ## Create required MinIO buckets
	bash infra/scripts/create_buckets.sh

# ─── Python Services ─────────────────────────────────────────────────────────

.PHONY: py-sync
py-sync: ## Install/sync Python dependencies for all services
	cd shared/pdf-renderer && uv sync
	cd services/public-api && uv sync --extra dev
	cd services/admin-backend && uv sync --extra dev
	cd services/scraper-worker && uv sync --extra dev
	cd services/llm-parser-worker && uv sync --extra dev
	cd shared/py-types && uv sync
	cd shared/db-migrations && uv sync

.PHONY: api-public
api-public: ## Start Public API (FastAPI, port 8080)
	cd services/public-api && uv run uvicorn app.main:app --reload --port 8080 --log-level debug

.PHONY: api-admin
api-admin: ## Start Admin Backend API (FastAPI, port 8082)
	cd services/admin-backend && uv run uvicorn app.main:app --reload --port 8082 --log-level debug

.PHONY: worker-scraper
worker-scraper: ## Start Scraper Worker (Celery, single concurrency)
	cd services/scraper-worker && uv run celery -A app.celery_app worker \
		--queues data_acquisition_queue \
		--concurrency 1 \
		--loglevel debug \
		--pool solo \
		-n scraper@%h


.PHONY: worker-llm
worker-llm: ## Start LLM Parser Worker (Celery, single concurrency)
	cd services/llm-parser-worker && uv run celery -A app.celery_app worker \
		--queues llm_processing_queue \
		--concurrency 1 \
		--loglevel debug \
		-n llm_parser@%h

.PHONY: worker-llm-debug
worker-llm-debug: ## Start LLM Parser Worker in debugger-friendly solo mode
	cd services/llm-parser-worker && uv run celery -A app.celery_app worker \
		--queues llm_processing_queue \
		--concurrency 1 \
		--loglevel debug \
		--pool solo \
		-n llm_parser@%h

# ─── Next.js Apps ────────────────────────────────────────────────────────────

.PHONY: web-public
web-public: ## Start Public Web app (Next.js, port 3000)
	pnpm --filter public-web dev

.PHONY: web-admin
web-admin: ## Start Admin Web app (Next.js, port 3001)
	pnpm --filter admin-web dev

.PHONY: web-build
web-build: ## Build both Next.js apps for production
	pnpm --filter public-web build
	pnpm --filter admin-web build

# ─── Testing ─────────────────────────────────────────────────────────────────

.PHONY: test-public-api
.PHONY: test-public-api
test-public-api: ## Run Public API tests
	cd services/public-api && uv run pytest tests/ -v --cov=app --cov-report=term-missing

.PHONY: test-admin-backend
test-admin-backend: ## Run Admin Backend API tests
	cd services/admin-backend && uv run pytest tests/ -v --cov=app --cov-report=term-missing

.PHONY: test-scraper
test-scraper: ## Run Scraper Worker unit tests
	cd services/scraper-worker && uv run pytest tests/unit/ -v

.PHONY: test-llm
test-llm: ## Run LLM Parser Worker unit tests
	cd services/llm-parser-worker && uv run pytest tests/unit/ -v

.PHONY: test-python
test-python: test-public-api test-admin-backend test-scraper test-llm ## Run all Python tests

.PHONY: test-frontend
test-frontend: ## Run all frontend (TypeScript/Next.js) tests
	pnpm --filter public-web test
	pnpm --filter admin-web exec vitest run --passWithNoTests

.PHONY: test-all
test-all: test-python test-frontend ## Run all tests (Python + TypeScript)
	@echo ""
	@echo "✓ All tests completed!"

# ─── Playwright ──────────────────────────────────────────────────────────────

.PHONY: playwright-install
playwright-install: ## Install Playwright browsers for scraper worker
	cd services/scraper-worker && uv run playwright install chromium

# ─── Composite Commands ─────────────────────────────────────────────────────

.PHONY: setup
setup: ## First-time setup: install all deps, start infra, run migrations
	pnpm install
	$(MAKE) py-sync
	$(MAKE) infra-up
	@echo "Waiting for Postgres to be ready..."
	@until docker compose exec -T postgres pg_isready -U $(POSTGRES_USER) -d $(POSTGRES_DB) 2>/dev/null; do sleep 1; done
	$(MAKE) db-migrate
	@echo ""
	@echo "✓ Setup complete. Run 'make dev-full' to start all services."

.PHONY: dev-full
dev-full: ## Start everything: infra + all backend services + frontend apps
	@echo "Starting infrastructure..."
	$(MAKE) infra-up
	@echo ""
	@echo "Start these in separate terminals:"
	@echo "  make api-public         # Terminal 1 — Public API (port 8080)"
	@echo "  make api-admin          # Terminal 2 — Admin Backend API (port 8082)"
	@echo "  make worker-scraper     # Terminal 3 — Scraper Worker"
	@echo "  make worker-llm         # Terminal 4 — LLM Parser Worker"
	@echo "  make worker-llm-debug   # Optional: debugger-friendly solo worker"
	@echo "  make web-public         # Terminal 5 — Public Web (port 3000)"
	@echo "  make web-admin          # Terminal 6 — Admin Web (port 3001)"

# ─── Data Import ─────────────────────────────────────────────────────────────

.PHONY: import-spatial-zones
import-spatial-zones: ## Import spatial zones (usage: make import-spatial-zones type=LGA source=/path/to/file.shp [state=VIC] - source supports glob: /path/*.geojson)
	@if [ -z "$(type)" ] || [ -z "$(source)" ]; then \
		echo "Usage: make import-spatial-zones type=LGA|SUBURB|SCHOOL_CATCHMENT source=/path/to/file.shp [state=VIC]"; \
		echo "       Glob patterns are supported: source=/path/to/*.geojson"; \
		exit 1; \
	fi
	cd infra/scripts && DATABASE_URL=$(DB_URL) uv run python import_spatial_zones.py --type $(type) --source "$(source)" $(if $(state),--state $(state))

.PHONY: import-schools
import-schools: ## Import school locations (usage: make import-schools source=/path/to/schools.csv [state=VIC] [truncate=1] [link=1])
	@if [ -z "$(source)" ]; then \
		echo "Usage: make import-schools source=/path/to/schools.csv [state=VIC] [truncate=1] [link=1]"; \
		exit 1; \
	fi
	@state_arg="$(state)"; \
	if [ -z "$$state_arg" ]; then \
		for st in VIC NSW QLD SA WA TAS ACT NT; do \
			case "$(source)" in \
				*/$$st/*) state_arg="$$st"; break ;; \
			esac; \
		done; \
	fi; \
	if [ -z "$$state_arg" ]; then \
		echo "ERROR: Could not infer state from source path. Pass state=VIC|NSW|QLD|SA|WA|TAS|ACT|NT"; \
		exit 1; \
	fi; \
	echo "Using state=$$state_arg"; \
	cd infra/scripts && DATABASE_URL=$(DB_URL) uv run python import_schools.py \
		--source "$(source)" --state "$$state_arg" \
		$(if $(truncate),--truncate) \
		$(if $(link),--link-catchments)

.PHONY: import-gnaf
import-gnaf: ## Import G-NAF data (usage: make import-gnaf source=/path/to/gnaf.zip)
	@if [ -z "$(source)" ]; then echo "Usage: make import-gnaf source=/path/to/gnaf_feb2026.zip"; exit 1; fi
	cd infra/scripts && DATABASE_URL=$(DB_URL) uv run python import_gnaf.py --state VIC --source $(source)

.PHONY: create-properties
create-properties: ## Create properties from GNAF thin import (usage: make create-properties [state=VIC] [limit=10000] [batch=1000])
	cd infra/scripts && DATABASE_URL=$(DB_URL) uv run python create_properties_from_gnaf.py $(if $(state),--state $(state)) $(if $(limit),--limit $(limit)) $(if $(batch),--batch-size $(batch))

# ─── K8s Deploy (Remote K3s) ─────────────────────────────────────────────────

SERVICES := public-api admin-backend public-web admin-web scraper-worker llm-parser-worker

.PHONY: build-docker
build-docker: ## Build all 7 Docker images (usage: make build-docker tag=<tag>)
	@if [ -z "$(tag)" ]; then echo "Usage: make build-docker tag=<tag>"; exit 1; fi
	@if [ -z "$(CLERK_PUBLIC_PUBLISHABLE_KEY)" ]; then echo "ERROR: CLERK_PUBLIC_PUBLISHABLE_KEY is required in root .env for public-web build."; exit 1; fi
	@if [ -z "$(NEXT_PUBLIC_MAPBOX_TOKEN)" ]; then echo "ERROR: NEXT_PUBLIC_MAPBOX_TOKEN is required in root .env for public-web build."; exit 1; fi
	@if [ -z "$(NEXT_PUBLIC_CREDIT_PURCHASE_ENABLED)" ]; then echo "ERROR: NEXT_PUBLIC_CREDIT_PURCHASE_ENABLED is required in root .env for public-web build."; exit 1; fi
	@if [ -z "$(NEXT_PUBLIC_TURNSTILE_SITE_KEY)" ]; then echo "ERROR: NEXT_PUBLIC_TURNSTILE_SITE_KEY is required in root .env for public-web build."; exit 1; fi
	@if [ -z "$(CLERK_ADMIN_PUBLISHABLE_KEY)" ]; then echo "ERROR: CLERK_ADMIN_PUBLISHABLE_KEY is required in root .env for admin-web build."; exit 1; fi
	@echo "Building images with tag $(tag) for registry $(REGISTRY)..."
	docker build -t $(REGISTRY)/ozpr-public-api:$(tag) -f services/public-api/Dockerfile .
	@echo "  ✓ $(REGISTRY)/ozpr-public-api:$(tag)"
	docker build -t $(REGISTRY)/ozpr-admin-backend:$(tag) -f services/admin-backend/Dockerfile .
	@echo "  ✓ $(REGISTRY)/ozpr-admin-backend:$(tag)"
	docker build -t $(REGISTRY)/ozpr-public-web:$(tag) \
		--build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$(CLERK_PUBLIC_PUBLISHABLE_KEY) \
		--build-arg NEXT_PUBLIC_MAPBOX_TOKEN=$(NEXT_PUBLIC_MAPBOX_TOKEN) \
		--build-arg NEXT_PUBLIC_CREDIT_PURCHASE_ENABLED=$(NEXT_PUBLIC_CREDIT_PURCHASE_ENABLED) \
		--build-arg NEXT_PUBLIC_TURNSTILE_SITE_KEY=$(NEXT_PUBLIC_TURNSTILE_SITE_KEY) \
		--build-arg INTERNAL_API_URL=$(INTERNAL_API_URL) \
		-f apps/public-web/Dockerfile .
	@echo "  ✓ $(REGISTRY)/ozpr-public-web:$(tag)"
	docker build -t $(REGISTRY)/ozpr-admin-web:$(tag) \
		--build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$(CLERK_ADMIN_PUBLISHABLE_KEY) \
		-f apps/admin-web/Dockerfile .
	@echo "  ✓ $(REGISTRY)/ozpr-admin-web:$(tag)"
	docker build -t $(REGISTRY)/ozpr-scraper-worker:$(tag) -f services/scraper-worker/Dockerfile .
	@echo "  ✓ $(REGISTRY)/ozpr-scraper-worker:$(tag)"
	docker build -t $(REGISTRY)/ozpr-llm-parser-worker:$(tag) -f services/llm-parser-worker/Dockerfile .
	@echo "  ✓ $(REGISTRY)/ozpr-llm-parser-worker:$(tag)"
	docker build -t $(REGISTRY)/ozpr-db-migrate:$(tag) shared/db-migrations/
	@echo "  ✓ $(REGISTRY)/ozpr-db-migrate:$(tag)"
	@echo ""
	@echo "All images built. Run 'make deploy tag=$(tag)' to push and deploy."

.PHONY: deploy
deploy: ## Push images and deploy to remote K3s (usage: make deploy tag=<tag> [REGISTRY=yourregistry])
	@if [ -z "$(tag)" ]; then echo "Usage: make deploy tag=<tag>"; exit 1; fi
	@if [ "$(REGISTRY)" = "ghcr.io/your-org" ]; then \
		echo "ERROR: REGISTRY is not set. Override via: make deploy tag=$(tag) REGISTRY=yourregistry.io/yourorg"; \
		exit 1; \
	fi
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Deploying to: $$(kubectl config current-context)"
	@echo "  Registry:     $(REGISTRY)"
	@echo "  Image tag:    $(tag)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@read -p "Press Enter to continue, Ctrl+C to abort: "
	@echo ""
	@echo "→ Pushing images..."
	docker push $(REGISTRY)/ozpr-public-api:$(tag)
	docker push $(REGISTRY)/ozpr-admin-backend:$(tag)
	docker push $(REGISTRY)/ozpr-public-web:$(tag)
	docker push $(REGISTRY)/ozpr-admin-web:$(tag)
	docker push $(REGISTRY)/ozpr-scraper-worker:$(tag)
	docker push $(REGISTRY)/ozpr-llm-parser-worker:$(tag)
	docker push $(REGISTRY)/ozpr-db-migrate:$(tag)
	@echo ""
	@echo "→ Applying namespace and config..."
	kubectl apply -f infra/k8s/namespace.yaml
	kubectl apply -f infra/k8s/configmap.yaml
	$(MAKE) k8s-secrets
	$(MAKE) k8s-registry-secret
	@echo ""
	@echo "→ Applying PVCs..."
	kubectl apply -f infra/k8s/pvc/
	@echo ""
	@echo "→ Applying infrastructure services..."
	kubectl apply -f infra/k8s/infrastructure/
	kubectl rollout status statefulset/postgres -n ozpropertyreport --timeout=120s
	@echo ""
	@echo "→ Running DB migrations..."
	kubectl delete job db-migrate -n ozpropertyreport --ignore-not-found
	IMAGE_TAG=$(tag) REGISTRY=$(REGISTRY) envsubst '$$IMAGE_TAG $$REGISTRY' < infra/k8s/jobs/db-migrate.yaml | kubectl apply -f -
	kubectl wait --for=condition=complete job/db-migrate -n ozpropertyreport --timeout=180s
	@echo ""
	@echo "→ Deploying application services..."
	IMAGE_TAG=$(tag) REGISTRY=$(REGISTRY) envsubst '$$IMAGE_TAG $$REGISTRY' < infra/k8s/apps/public-api.yaml | kubectl apply -f -
	IMAGE_TAG=$(tag) REGISTRY=$(REGISTRY) envsubst '$$IMAGE_TAG $$REGISTRY' < infra/k8s/apps/admin-backend.yaml | kubectl apply -f -
	IMAGE_TAG=$(tag) REGISTRY=$(REGISTRY) envsubst '$$IMAGE_TAG $$REGISTRY' < infra/k8s/apps/public-web.yaml | kubectl apply -f -
	IMAGE_TAG=$(tag) REGISTRY=$(REGISTRY) envsubst '$$IMAGE_TAG $$REGISTRY' < infra/k8s/apps/admin-web.yaml | kubectl apply -f -
	IMAGE_TAG=$(tag) REGISTRY=$(REGISTRY) envsubst '$$IMAGE_TAG $$REGISTRY' < infra/k8s/apps/scraper-worker.yaml | kubectl apply -f -
	IMAGE_TAG=$(tag) REGISTRY=$(REGISTRY) envsubst '$$IMAGE_TAG $$REGISTRY' < infra/k8s/apps/llm-parser-worker.yaml | kubectl apply -f -
	@echo ""
	@echo "→ Applying ingress and network policies..."
	kubectl apply -f infra/k8s/ingress/
	kubectl apply -f infra/k8s/network-policies/
	@echo ""
	@echo "✓ Deploy complete! Run 'make k8s-status' to check pod health."

.PHONY: k8s-secrets
k8s-secrets: ## Apply secrets from .env to remote cluster (never written to disk)
	@if [ ! -f .env ]; then echo "ERROR: .env file not found. Copy from secrets.example.yaml and fill in values."; exit 1; fi
	kubectl create secret generic ozpr-secrets \
		--from-env-file=.env \
		-n ozpropertyreport \
		--dry-run=client -o yaml | kubectl apply -f -
	@echo "✓ ozpr-secrets applied to cluster."

.PHONY: k8s-registry-secret
k8s-registry-secret: ## Create docker-registry secret for private image pulls
	@DOCKER_CONFIG=$${DOCKER_CONFIG:-$$HOME/.docker}; \
	if [ ! -f "$$DOCKER_CONFIG/config.json" ]; then \
		echo "ERROR: No Docker config found at $$DOCKER_CONFIG/config.json"; \
		echo "Run 'docker login' first to authenticate with your registry."; \
		exit 1; \
	fi; \
	kubectl create secret generic regcred \
		--from-file=.dockerconfigjson=$$DOCKER_CONFIG/config.json \
		--type=kubernetes.io/dockerconfigjson \
		-n ozpropertyreport \
		--dry-run=client -o yaml | kubectl apply -f -
	@echo "✓ regcred (docker-registry) secret applied. Pods can now pull from private registries."

.PHONY: k8s-status
k8s-status: ## Show all K8s resources in the ozpropertyreport namespace
	kubectl get all -n ozpropertyreport

.PHONY: k8s-logs
k8s-logs: ## Tail logs for a deployment (usage: make k8s-logs svc=<service>)
	@if [ -z "$(svc)" ]; then echo "Usage: make k8s-logs svc=<service> (e.g. svc=public-api)"; exit 1; fi
	kubectl logs -f -n ozpropertyreport deploy/$(svc) --tail=100

.PHONY: k8s-hosts
k8s-hosts: ## Print /etc/hosts entries for the cluster (public domains only)
	@NODE_IP=$$(kubectl get nodes -o wide --no-headers | head -1 | awk '{print $$6}'); \
	echo ""; \
	echo "Add these entries to /etc/hosts (use any K3s node IP):"; \
	echo ""; \
	echo "  $$NODE_IP  ozpropertyreport.com"; \
	echo ""; \
	echo "NOTE: TLS cert via Let's Encrypt requires real public DNS, not /etc/hosts."

.PHONY: k8s-admin
k8s-admin: ## Port-forward admin-web, minio console, and flower to localhost
	@echo "Starting port-forwards for admin surfaces (Ctrl+C to stop all)..."
	@echo "  admin-web     → http://localhost:3001"
	@echo "  minio console → http://localhost:9001"
	@echo "  flower        → http://localhost:5555"
	@echo ""
	kubectl port-forward -n ozpropertyreport svc/admin-web 3001:3001 &
	kubectl port-forward -n ozpropertyreport svc/minio 9001:9001 &
	kubectl port-forward -n ozpropertyreport svc/flower 5555:5555 &
	@wait

.PHONY: k8s-teardown
k8s-teardown: ## DELETE the ozpropertyreport namespace and all resources (irreversible!)
	@echo "⚠️  WARNING: This will permanently delete ALL resources in the ozpropertyreport namespace,"
	@echo "   including Postgres data, MinIO objects, and all PVCs."
	@read -p "Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" != "yes" ]; then echo "Aborted."; exit 1; fi
	kubectl delete namespace ozpropertyreport
	@echo "✓ Namespace deleted."

.PHONY: k8s-init-data
k8s-init-data: ## Bootstrap VIC reference data on cluster (usage: make k8s-init-data lga_source=<path> suburb_source=<path> catchment_source=<path> school_source=<path> gnaf_source=<path>)
	@if [ -z "$(lga_source)" ] || [ -z "$(suburb_source)" ] || [ -z "$(catchment_source)" ] || [ -z "$(school_source)" ] || [ -z "$(gnaf_source)" ]; then \
		echo "Usage: make k8s-init-data \\"; \
		echo "  lga_source=/path/to/LGA_2024_AUST_GDA2020.shp \\"; \
		echo "  suburb_source=/path/to/SAL_2021_AUST_GDA2020.shp \\"; \
		echo "  catchment_source=/path/to/school_catchments_vic.geojson \\"; \
		echo "  school_source=/path/to/vic_schools_2024.csv \\"; \
		echo "  gnaf_source=/path/to/gnaf_feb2026.zip"; \
		exit 1; \
	fi
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  VIC Data Initialization — connecting via port-forward"
	@echo "  Target cluster: $$(kubectl config current-context)"
	@echo "  Tip: for long runs, use make k8s-import-gnaf then make k8s-create-properties"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@# Extract DB credentials from K8s secret
	@PG_USER=$$(kubectl get secret ozpr-secrets -n ozpropertyreport -o jsonpath='{.data.POSTGRES_USER}' | base64 -d); \
	PG_PASS=$$(kubectl get secret ozpr-secrets -n ozpropertyreport -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d); \
	PG_DB=$$(kubectl get secret ozpr-secrets -n ozpropertyreport -o jsonpath='{.data.POSTGRES_DB}' | base64 -d); \
	K8S_DB_URL="postgresql://$$PG_USER:$$PG_PASS@localhost:15432/$$PG_DB"; \
	\
	echo "→ Starting Postgres port-forward (cluster:5432 → localhost:15432)..."; \
	kubectl port-forward -n ozpropertyreport svc/postgres 15432:5432 &>/dev/null & \
	PG_PF_PID=$$!; \
	sleep 3; \
	\
	echo "→ [1/6] Importing LGA boundaries (VIC)..."; \
	(cd infra/scripts && DATABASE_URL=$$K8S_DB_URL uv run python import_spatial_zones.py \
		--type LGA --source "$(lga_source)" --state VIC) || { kill $$PG_PF_PID 2>/dev/null; exit 1; }; \
	\
	echo "→ [2/6] Importing suburb boundaries (VIC)..."; \
	(cd infra/scripts && DATABASE_URL=$$K8S_DB_URL uv run python import_spatial_zones.py \
		--type SUBURB --source "$(suburb_source)" --state VIC) || { kill $$PG_PF_PID 2>/dev/null; exit 1; }; \
	\
	echo "→ [3/6] Importing school catchment zones (VIC)..."; \
	(cd infra/scripts && DATABASE_URL=$$K8S_DB_URL uv run python import_spatial_zones.py \
		--type SCHOOL_CATCHMENT --source "$(catchment_source)" --state VIC) || { kill $$PG_PF_PID 2>/dev/null; exit 1; }; \
	\
	echo "→ [4/6] Importing school locations (VIC, with catchment linking)..."; \
	(cd infra/scripts && DATABASE_URL=$$K8S_DB_URL uv run python import_schools.py \
		--source "$(school_source)" --state VIC --link-catchments) || { kill $$PG_PF_PID 2>/dev/null; exit 1; }; \
	\
	echo "→ [5/6] Importing G-NAF addresses (VIC)..."; \
	(cd infra/scripts && DATABASE_URL=$$K8S_DB_URL uv run python import_gnaf.py \
		--state VIC --source "$(gnaf_source)") || { kill $$PG_PF_PID 2>/dev/null; exit 1; }; \
	\
	echo "→ [6/6] Creating properties from G-NAF (VIC)..."; \
	(cd infra/scripts && DATABASE_URL=$$K8S_DB_URL uv run python create_properties_from_gnaf.py \
		--state VIC) || { kill $$PG_PF_PID 2>/dev/null; exit 1; }; \
	\
	echo ""; \
	echo "→ Creating MinIO buckets..."; \
	MINIO_PF_PID=""; \
	kubectl port-forward -n ozpropertyreport svc/minio 19000:9000 &>/dev/null & \
	MINIO_PF_PID=$$!; \
	sleep 3; \
	MINIO_PORT=19000 \
	MINIO_ROOT_USER=$$(kubectl get secret ozpr-secrets -n ozpropertyreport -o jsonpath='{.data.MINIO_ACCESS_KEY}' | base64 -d) \
	MINIO_ROOT_PASSWORD=$$(kubectl get secret ozpr-secrets -n ozpropertyreport -o jsonpath='{.data.MINIO_SECRET_KEY}' | base64 -d) \
	bash infra/scripts/create_buckets.sh || { kill $$PG_PF_PID $$MINIO_PF_PID 2>/dev/null; exit 1; }; \
	\
	echo "→ Stopping port-forwards..."; \
	kill $$PG_PF_PID $$MINIO_PF_PID 2>/dev/null || true; \
	\
	echo ""; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	echo "  ✓ VIC data initialization complete!"; \
	echo "  Run 'make k8s-admin' to open admin surfaces and verify data."; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

.PHONY: k8s-import-gnaf
k8s-import-gnaf: ## Import G-NAF to cluster DB only (usage: make k8s-import-gnaf source=<path> [state=VIC] [batch=100000])
	@if [ -z "$(source)" ]; then \
		echo "Usage: make k8s-import-gnaf source=/path/to/gnaf_feb2026.zip [state=VIC] [batch=100000]"; \
		exit 1; \
	fi
	@STATE="$(state)"; \
	if [ -z "$$STATE" ]; then STATE="VIC"; fi; \
	BATCH="$(batch)"; \
	if [ -z "$$BATCH" ]; then BATCH="25000"; fi; \
	PG_USER=$$(kubectl get secret ozpr-secrets -n ozpropertyreport -o jsonpath='{.data.POSTGRES_USER}' | base64 -d); \
	PG_PASS=$$(kubectl get secret ozpr-secrets -n ozpropertyreport -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d); \
	PG_DB=$$(kubectl get secret ozpr-secrets -n ozpropertyreport -o jsonpath='{.data.POSTGRES_DB}' | base64 -d); \
	K8S_DB_URL="postgresql://$$PG_USER:$$PG_PASS@localhost:15432/$$PG_DB"; \
	echo "→ Starting Postgres port-forward (cluster:5432 → localhost:15432)..."; \
	kubectl port-forward -n ozpropertyreport svc/postgres 15432:5432 &>/dev/null & \
	PG_PF_PID=$$!; \
	sleep 3; \
	echo "→ Importing G-NAF (state=$$STATE, batch=$$BATCH)..."; \
	(cd infra/scripts && DATABASE_URL=$$K8S_DB_URL uv run python import_gnaf.py --state $$STATE --batch-size $$BATCH --source "$(source)") || { kill $$PG_PF_PID 2>/dev/null; exit 1; }; \
	kill $$PG_PF_PID 2>/dev/null || true; \
	echo "✓ G-NAF import completed."

.PHONY: k8s-create-properties
k8s-create-properties: ## Create properties in cluster DB only (usage: make k8s-create-properties [state=VIC] [limit=100000] [batch=1000])
	@STATE="$(state)"; \
	if [ -z "$$STATE" ]; then STATE="VIC"; fi; \
	BATCH="$(batch)"; \
	if [ -z "$$BATCH" ]; then BATCH="1000"; fi; \
	LIMIT_FLAG=""; \
	if [ -n "$(limit)" ]; then LIMIT_FLAG="--limit $(limit)"; fi; \
	PG_USER=$$(kubectl get secret ozpr-secrets -n ozpropertyreport -o jsonpath='{.data.POSTGRES_USER}' | base64 -d); \
	PG_PASS=$$(kubectl get secret ozpr-secrets -n ozpropertyreport -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d); \
	PG_DB=$$(kubectl get secret ozpr-secrets -n ozpropertyreport -o jsonpath='{.data.POSTGRES_DB}' | base64 -d); \
	K8S_DB_URL="postgresql://$$PG_USER:$$PG_PASS@localhost:15432/$$PG_DB"; \
	echo "→ Starting Postgres port-forward (cluster:5432 → localhost:15432)..."; \
	kubectl port-forward -n ozpropertyreport svc/postgres 15432:5432 &>/dev/null & \
	PG_PF_PID=$$!; \
	sleep 3; \
	echo "→ Creating properties (state=$$STATE, batch=$$BATCH)..."; \
	(cd infra/scripts && DATABASE_URL=$$K8S_DB_URL uv run python create_properties_from_gnaf.py --state $$STATE --batch-size $$BATCH $$LIMIT_FLAG) || { kill $$PG_PF_PID 2>/dev/null; exit 1; }; \
	kill $$PG_PF_PID 2>/dev/null || true; \
	echo "✓ Properties creation completed."

# ─── Help ────────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help message
	@echo "ParcelIQ Development Commands"
	@echo "────────────────────────────────────────────────────────"
	@echo ""
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Quick Start:"
	@echo "  make setup              First-time setup (install deps, start infra)"
	@echo "  make dev-full           Start all services (shows terminal commands)"
	@echo ""
	@echo "Most Common Commands:"
	@echo "  make api-admin          Start admin backend (port 8082)"
	@echo "  make web-admin          Start admin web app (port 3001)"
	@echo "  make worker-scraper     Start scraper worker"
	@echo "  make worker-llm         Start LLM parser worker"
	@echo "  make worker-llm-debug   Start LLM parser worker in solo debug mode"
