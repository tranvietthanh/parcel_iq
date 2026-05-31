# OZ Property Report Developer Checklist

Complete this checklist to verify your development environment is properly configured and all services are working.

---

## Phase 1: Prerequisites ✓

- [ ] **Docker & Docker Compose installed**
  ```bash
  docker compose --version
  # Should show: Docker Compose version v2.x+
  ```

- [ ] **pnpm installed**
  ```bash
  pnpm --version
  # Should show: v8.x+
  ```

- [ ] **uv (Python) installed**
  ```bash
  uv --version
  # Should show: uv x.y.z
  ```

- [ ] **PostgreSQL client (psql) available**
  ```bash
  psql --version
  # Should show: psql (PostgreSQL) 14+
  ```

- [ ] **Make available**
  ```bash
  make --version
  # Should show: GNU Make 4.x+
  ```

---

## Phase 2: Environment Setup ✓

- [ ] **.env file exists in repository root**
  ```bash
  ls -la .env | grep -v ".env.example"
  # Should show: -rw-r--r-- .env
  ```

- [ ] **Environment variables are set**
  ```bash
  grep "POSTGRES_USER" .env
  grep "POSTGRES_PASSWORD" .env
  grep "REDIS_URL" .env
  # Should all return values
  ```

- [ ] **All service .env.example files exist**
  ```bash
  find . -name ".env.example" | sort
  # Should show 6 files:
  # apps/admin-web/.env.example
  # apps/public-web/.env.example
  # services/admin-backend/.env.example
  # services/llm-parser-worker/.env.example
  # services/public-api/.env.example
  # services/scraper-worker/.env.example
  ```

---

## Phase 3: Infrastructure Startup ✓

- [ ] **Docker containers can start**
  ```bash
  make infra-up
  # Wait 10 seconds
  docker compose ps
  # All containers should show "Up" status
  ```

- [ ] **PostgreSQL is healthy**
  ```bash
  make db-shell
  # Should open psql prompt
  \q
  # Exit without error
  ```

- [ ] **Redis is reachable**
  ```bash
  docker compose exec redis redis-cli ping
  # Should return: PONG
  ```

- [ ] **MinIO is accessible**
  ```bash
  curl -s http://localhost:9001 | grep -q "MinIO"
  # Should return without error (MinIO web UI loads)
  ```

---

## Phase 4: Database Migrations ✓

- [ ] **Migrations can run**
  ```bash
  make db-migrate
  # Should show: "Upgrade complete"
  ```

- [ ] **All 11 tables are created**
  ```bash
  make db-shell
  # In psql:
  \dt
  # Should show 11 tables starting with admin_activity_log, data_source_configs, ...
  \q
  ```

- [ ] **Extensions are loaded**
  ```bash
  make db-shell
  # In psql:
  SELECT extname FROM pg_extension WHERE extname LIKE '%postgis%';
  # Should return: postgis | 3.4.x
  \q
  ```

---

## Phase 5: Python Dependencies ✓

- [ ] **All Python services have uv.lock files**
  ```bash
  find services -name "uv.lock" | wc -l
  # Should return 5 (one per service + shared package)
  ```

- [ ] **Python dependencies can sync**
  ```bash
  make py-sync
  # Should complete without errors
  ```

- [ ] **Shared types are installable**
  ```bash
  cd shared/py-types && uv run python -c "from parceliq_types.llm_output import LlmOutput; print('OK')"
  # Should print: OK
  ```

---

## Phase 6: Node/Frontend Dependencies ✓

- [ ] **pnpm can install dependencies**
  ```bash
  pnpm install
  # Should complete without errors
  ```

- [ ] **Frontend test dependencies are installed**
  ```bash
  cd apps/public-web && pnpm list vitest
  # Should show: vitest@x.y.z
  ```

- [ ] **TypeScript is available**
  ```bash
  cd apps/public-web && npx tsc --version
  # Should show: Version x.y.z
  ```

---

## Phase 7: API Services ✓

- [ ] **Public API can start**
  ```bash
  cd services/public-api && timeout 10 uv run uvicorn app.main:app --port 8080 2>&1 | grep -i "startup"
  # Should show: "Application startup complete"
  ```

- [ ] **Admin API can start**
  ```bash
  cd services/admin-backend && timeout 10 uv run uvicorn app.main:app --port 8082 2>&1 | grep -i "startup"
  # Should show: "Application startup complete"
  ```

- [ ] **Public API docs are accessible**
  ```bash
  # Start API in background, then:
  curl -s http://localhost:8080/docs | grep -q "swagger-ui"
  # Should return true (docs page loads)
  ```

---

## Phase 8: Worker Services ✓

- [ ] **Scraper Worker can initialize**
  ```bash
  cd services/scraper-worker && timeout 5 uv run celery -A app.celery_app --help 2>&1 | grep -q "celery"
  # Should show celery help without error
  ```

- [ ] **LLM Parser Worker can initialize**
  ```bash
  cd services/llm-parser-worker && timeout 5 uv run celery -A app.celery_app --help 2>&1 | grep -q "celery"
  # Should show celery help without error
  ```

- [ ] **Playwright is installed (for scraper)**
  ```bash
  cd services/scraper-worker && uv run python -c "import playwright; print('OK')"
  # Should print: OK
  ```

---

## Phase 9: Python Tests ✓

- [ ] **Public API tests pass**
  ```bash
  cd services/public-api && uv run pytest tests/ -q
  # Should show: 49 passed
  ```

- [ ] **Admin Backend tests pass**
  ```bash
  cd services/admin-backend && uv run pytest tests/ -q
  # Should show: 24 passed
  ```

- [ ] **Scraper Worker unit tests pass**
  ```bash
  cd services/scraper-worker && uv run pytest tests/unit/ -q
  # Should show: 72 passed
  ```

- [ ] **LLM Parser Worker unit tests pass**
  ```bash
  cd services/llm-parser-worker && uv run pytest tests/unit/ -q
  # Should show: 77 passed (~50 unit tests)
  ```

---

## Phase 10: Frontend Tests ✓

- [ ] **Public Web tests pass**
  ```bash
  cd apps/public-web && pnpm test --run
  # Should show: Test Files 8 passed (8)
  #             Tests 25 passed (25)
  ```

- [ ] **Frontend build works**
  ```bash
  cd apps/public-web && pnpm build
  # Should complete without errors and show:
  # - Routes optimized
  # - Fonts optimized
  # - Build complete
  ```

---

## Phase 11: Full Stack Startup ✓

- [ ] **All services can start together**
  ```bash
  # In separate terminals:
  make infra-up                          # Terminal 1
  sleep 5
  cd services/public-api && uv run uvicorn app.main:app --reload --port 8080 2>&1 | tail -1
  # Expected: "Uvicorn running on..."
  
  # (Repeat for admin-backend, worker-scraper, worker-llm)
  # Should all start without errors
  ```

- [ ] **Public Web can start**
  ```bash
  cd apps/public-web && pnpm dev
  # Should show: "ready - started server on 0.0.0.0:3000"
  ```

- [ ] **Services are reachable**
  ```bash
  curl http://localhost:8080/api/health
  curl http://localhost:8082/stats
  curl http://localhost:3000
  # All should return HTTP 200 (or successful response)
  ```

---

## Phase 12: Manual Feature Testing ✓

### Public Web (http://localhost:3000)

- [ ] **Map loads and is interactive**
  - [ ] Mapbox map visible
  - [ ] Default view shows Sydney area (zoom 5)
  - [ ] Can pan and zoom

- [ ] **Search omnibox works**
  - [ ] Type "Paddington" → autocomplete appears
  - [ ] Results appear in < 500ms
  - [ ] Clicking result doesn't error

- [ ] **Property pins load**
  - [ ] Perform pan/zoom on map
  - [ ] API request sent (watch Network tab)
  - [ ] Pins appear on map

- [ ] **Lite panel opens**
  - [ ] Click a pin → right panel slides in
  - [ ] Shows address, beds, baths, cars, land, value, yield
  - [ ] Shows school catchments if available
  - [ ] "Unlock Full Report" button visible

- [ ] **Sign in flow works**
  - [ ] Click user avatar (top-right) → Clerk modal
  - [ ] Can sign up or continue with email
  - [ ] Modal closes on success

- [ ] **Unlock flow works**
  - [ ] Sign in first
  - [ ] Click "Unlock Full Report"
  - [ ] Redirects to Stripe checkout
  - [ ] Test card form visible

---

## Phase 13: API Manual Testing ✓

### Public API (http://localhost:8080)

- [ ] **Search endpoint works**
  ```bash
  curl "http://localhost:8080/api/search?bbox=150.5,-34.1,152.0,-33.5" \
    -H "Turnstile-Token: dummy"
  # Should return GeoJSON with pins (even if empty)
  ```

- [ ] **Properties endpoint works**
  ```bash
  curl "http://localhost:8080/api/properties/test-id/lite"
  # Should return property object or 404 (depends on data)
  ```

- [ ] **Health check passes**
  ```bash
  curl http://localhost:8080/api/health
  # Should return: {"status": "ok"}
  ```

### Admin API (http://localhost:8082)

- [ ] **Stats endpoint works**
  ```bash
  curl -H "X-Service-Token: dev-service-token-change-in-prod" \
    http://localhost:8082/stats
  # Should return JSON with stats
  ```

---

## Phase 14: Final Verification ✓

- [ ] **All tests pass when run together**
  ```bash
  make test-all
  # Should show: ~260 tests passing
  # Exits with code 0 (success)
  ```

- [ ] **No critical errors in logs**
  ```bash
  docker compose logs | grep -i "error" | grep -v "handled" | head -5
  # Should show no errors (or only handled errors)
  ```

- [ ] **Database is responsive**
  ```bash
  make db-shell
  SELECT count(*) FROM properties;
  # Should return a number (even if 0)
  \q
  ```

- [ ] **README/docs are accessible**
  ```bash
  cat README.md | head -20
  cat QUICKSTART.md | head -20
  cat TESTING.md | head -20
  # All should be readable
  ```

---

## Quick Check (5 minutes)

If you want to quickly verify everything is working:

```bash
#!/bin/bash
set -e

echo "✓ Checking prerequisites..."
docker compose --version > /dev/null
pnpm --version > /dev/null
uv --version > /dev/null

echo "✓ Starting infrastructure..."
make infra-up
docker compose ps | grep healthy > /dev/null || (echo "Infra not healthy" && exit 1)

echo "✓ Running migrations..."
make db-migrate

echo "✓ Running Python tests..."
make test-python

echo "✓ Running frontend tests..."
make test-frontend

echo "✓ All checks passed!"
```

Save this as `check-dev-env.sh`, then run:
```bash
chmod +x check-dev-env.sh
./check-dev-env.sh
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `docker compose: command not found` | Install Docker Desktop or `docker-compose` |
| `psql: could not connect` | Run `make infra-up` |
| `pytest: no tests found` | Run `make py-sync` first |
| `pnpm: command not found` | Install pnpm: `npm install -g pnpm` |
| Tests fail with import errors | Run `make py-sync && pnpm install` |
| Container exits immediately | Check logs: `docker compose logs service-name` |

---

## You're Ready! 🚀

Once all items are checked:

1. **Start developing:** `make dev-full`
2. **View the app:** http://localhost:3000
3. **Monitor logs:** `make infra-logs` (in another terminal)
4. **Run tests:** `make test-all`
5. **Read docs:** `cat QUICKSTART.md` and `TESTING.md`

---

**Questions?** Check [QUICKSTART.md](QUICKSTART.md) or [TESTING.md](TESTING.md) for detailed guides.
