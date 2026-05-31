"""FastAPI application factory — lifespan, CORS, rate limiter, security headers."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core.database import close_db_pool, create_db_pool
from app.core.rate_limit import limiter
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import health, my_properties, properties, saved, schools, search, sitemap, users, zones
from app.routers.credit_purchases import router as credit_purchases_router
from app.routers.credits import router as credits_router, precheck_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create DB pool.  Shutdown: close it."""
    await create_db_pool(app)
    yield
    await close_db_pool(app)


app = FastAPI(
    title="OZ Property Report Public API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
)

# ── Rate limiter ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middleware (order matters — last added = first executed) ───────────────────
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ozpropertyreport.com",
        "http://localhost:3000",  # dev
    ],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Turnstile-Token"],
    allow_credentials=True,
)

app.include_router(search.router, prefix="/api/search")
app.include_router(zones.router, prefix="/api/zones")
app.include_router(schools.router, prefix="/api/schools")
app.include_router(properties.router, prefix="/api/properties")
app.include_router(credits_router, prefix="/api/credits")
app.include_router(credit_purchases_router, prefix="/api/credits")
app.include_router(precheck_router, prefix="/api/properties")
app.include_router(my_properties.router, prefix="/api/properties")
app.include_router(users.router, prefix="/api/users")
app.include_router(saved.router, prefix="/api/saved")
app.include_router(health.router, prefix="/api")
app.include_router(sitemap.router, prefix="/api/sitemap")
