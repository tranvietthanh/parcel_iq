from pathlib import Path

from dotenv import load_dotenv

# Load .env into os.environ so that shared libraries (e.g. pdf-renderer)
# which read config via os.getenv() can see these values.
# pydantic-settings only loads .env into its own Settings model, not os.environ.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.database import create_db_pool, close_db_pool
from app.routers import (
    stats,
    reports,
    data_sources,
    queue,
    lgas,
    analytics,
    tasks,
    properties,
    users,
)
from app.routers.reconciliation import router as reconciliation_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Sets up database pool on startup and closes it on shutdown.
    """
    # Startup
    await create_db_pool(app)
    yield
    # Shutdown
    await close_db_pool(app)


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    This is the Admin Backend API - a ClusterIP-only service with no internet ingress.
    All requests come from Next.js Server Actions with X-Service-Token verification.
    """
    app = FastAPI(
        title="OZ Property Report Admin Backend API",
        description="Internal-only admin API (ClusterIP, no internet exposure)",
        version="1.0.0",
        lifespan=lifespan,
    )
    
    # CORS - only allow admin-web origin (K8s internal)
    # In production, this would be more restrictive, but since it's ClusterIP-only
    # and behind NetworkPolicy, the risk is minimal
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # ClusterIP-only, NetworkPolicy-restricted
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Register routers
    app.include_router(stats.router)
    app.include_router(reports.router)
    app.include_router(data_sources.router)
    app.include_router(queue.router)
    
    app.include_router(lgas.router)
    app.include_router(analytics.router)
    app.include_router(tasks.router)
    app.include_router(properties.router)
    app.include_router(users.router)
    app.include_router(reconciliation_router)
    
    # Health check endpoint (no auth required)
    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "admin-backend"}
    
    return app


# Create app instance
app = create_app()
