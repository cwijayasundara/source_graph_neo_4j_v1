"""Financial Services Context Graph — FastAPI Application."""

import logging
import os
import warnings
from contextlib import asynccontextmanager

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.context_graph_client import connect_neo4j, close_neo4j, is_connected
from app.memory import (
    close_memory,
    connect_memory,
    get_client,
    get_error_category,
    get_error_detail,
    get_error_message,
)
from app.routes import router

# Custom API route modules
from app.routes_dashboard import router as dashboard_router, init_dashboard_service
from app.services.dashboard_service import DashboardService
from app.routes_transactions import router as txn_router, init_transactions
from app.routes_merchants import router as merch_router, init_merchants
from app.routes_accounts import router as acct_router, init_accounts
from app.routes_graph import router as graph_router, init_graph
from app.routes_ingest import router as ingest_router

logger = logging.getLogger(__name__)

# Backend connection state
_neo4j_available = False
_memory_available = False
_neo4j_sync_driver = None  # synchronous driver for custom API routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle.

    On the NAMS backend, we only initialize the memory client — there is no
    bolt Neo4j to connect to. On the self-hosted bolt backend, we connect to
    Neo4j (which in turn initializes the memory integration).
    """
    global _neo4j_available, _memory_available, _neo4j_sync_driver

    if settings.memory_backend == "nams":
        try:
            await connect_memory()
            _memory_available = get_client() is not None
            if _memory_available:
                logger.info("NAMS memory client connected")
            else:
                # connect_memory() already logged the classified error.
                # Re-state it here so the startup banner is self-contained.
                msg = get_error_message() or "NAMS memory client unavailable"
                logger.warning("Starting in degraded mode: %s", msg)
        except Exception as e:
            _memory_available = False
            logger.warning("NAMS unavailable — starting in degraded mode: %s", e)
    else:
        try:
            await connect_neo4j()
            _neo4j_available = True
            _memory_available = True
            logger.info("Neo4j connected successfully")
        except Exception as e:
            _neo4j_available = False
            _memory_available = False
            logger.warning("Neo4j unavailable — starting in degraded mode: %s", e)

        if _neo4j_available:
            try:
                from app.vector_client import create_vector_index
                await create_vector_index()
            except Exception as e:
                logger.warning("Vector index creation failed (non-fatal): %s", e)

            # Initialize custom API routes with a synchronous Neo4j driver
            try:
                from neo4j import GraphDatabase

                neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
                neo4j_user = os.environ.get("NEO4J_USERNAME", "neo4j")
                neo4j_password = os.environ.get("NEO4J_PASSWORD", "financegraph")
                _neo4j_sync_driver = GraphDatabase.driver(
                    neo4j_uri, auth=(neo4j_user, neo4j_password)
                )

                init_dashboard_service(DashboardService(_neo4j_sync_driver))
                init_transactions(_neo4j_sync_driver)
                init_merchants(_neo4j_sync_driver)
                init_accounts(_neo4j_sync_driver)
                init_graph(_neo4j_sync_driver)
                logger.info("Custom API routes initialized with Neo4j driver")
            except Exception as e:
                logger.warning("Custom API route initialization failed (non-fatal): %s", e)

    yield

    if settings.memory_backend == "nams":
        if _memory_available:
            await close_memory()
    else:
        if _neo4j_available:
            await close_neo4j()
        if _neo4j_sync_driver is not None:
            _neo4j_sync_driver.close()


def get_neo4j_status() -> bool:
    """Check if Neo4j is available (bolt backend only)."""
    return _neo4j_available


def get_memory_status() -> bool:
    """Check if the memory backend is available."""
    return _memory_available

app = FastAPI(
    title="Financial Services Context Graph",
    description="Investment management, trading, compliance, and risk assessment",
    version="0.1.0",
    lifespan=lifespan,
)


CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    f"http://localhost:{settings.frontend_port}",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom API routers (dashboard, transactions, merchants, accounts, graph, ingest)
app.include_router(dashboard_router)
app.include_router(txn_router)
app.include_router(merch_router)
app.include_router(acct_router)
app.include_router(graph_router)
app.include_router(ingest_router)

# Include generated routes after custom routers so specific paths such as
# /api/graph/finance-overview are not captured by /api/graph/{entity_name}.
app.include_router(router, prefix="/api")


@app.get("/health")
async def health():
    """Health check endpoint with memory backend connectivity status."""
    if settings.memory_backend == "nams":
        memory_ok = get_memory_status()
        body = {
            "status": "ok" if memory_ok else "degraded",
            "memory_backend": "nams",
            "nams": memory_ok,
            "domain": "financial-services",
            "version": "0.1.0",
        }
        if not memory_ok:
            category = get_error_category()
            if category:
                body["nams_error"] = category
                body["nams_error_message"] = get_error_message()
                body["nams_error_detail"] = get_error_detail()
            body["nams_dashboard"] = "https://memory.neo4jlabs.com"
        return body
    neo4j_ok = is_connected()
    return {
        "status": "ok" if neo4j_ok else "degraded",
        "memory_backend": "bolt",
        "neo4j": neo4j_ok,
        "domain": "financial-services",
        "version": "0.1.0",
    }
