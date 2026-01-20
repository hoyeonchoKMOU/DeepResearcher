"""FastAPI Application Entry Point."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import traceback

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    settings = get_settings()
    logger.info(
        "Starting DeepResearcher",
        debug=settings.debug,
        project_id=settings.gcp_project_id,
    )
    yield
    logger.info("Shutting down DeepResearcher")


app = FastAPI(
    title="DeepResearcher",
    description="Research Orchestration Multi-Agent System with Antigravity OAuth",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler to log all errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all exceptions and log them."""
    print(f"\n{'='*60}")
    print(f"[GLOBAL ERROR] Unhandled exception!")
    print(f"[GLOBAL ERROR] Path: {request.url.path}")
    print(f"[GLOBAL ERROR] Method: {request.method}")
    print(f"[GLOBAL ERROR] Exception type: {type(exc).__name__}")
    print(f"[GLOBAL ERROR] Exception: {str(exc)}")
    print(f"[GLOBAL ERROR] Traceback:")
    print(traceback.format_exc())
    print(f"{'='*60}\n")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__}
    )


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "name": "DeepResearcher",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}


# Import and include routers
from backend.api.routes import auth, research, websocket, literature, literature_search

# Share projects reference between routers
# The research router loads projects from storage, and literature/search routers need access to the same data
literature.set_projects_reference(research._projects)
literature_search.set_projects_reference(research._projects)

# Router registration order matters!
# research.router (prefix /api/research) must come BEFORE literature routers:
# - research.router handles: /v3, /v3/create, /v3/{id}/status, /v3/{id}/rename,
#   /v3/{id}/process/research-experiment/*, /v3/{id}/process/paper-writing/*, /v3/{id}/documents/*
# - literature routers (prefix /api/research/v3) handle:
#   /{id}/process/literature-organization/*, /{id}/process/literature-search/*
#
# If literature routers come first, they capture ALL /api/research/v3/* requests
# and return 404 for routes they don't have (like /rename).
app.include_router(auth.router)
app.include_router(research.router)           # /api/research - handles most v3 routes
app.include_router(literature.router)         # /api/research/v3/*/literature-organization
app.include_router(literature_search.router)  # /api/research/v3/*/literature-search
app.include_router(websocket.router)


if __name__ == "__main__":
    import uvicorn
    print("[STARTUP] Starting DeepResearcher server...")
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
