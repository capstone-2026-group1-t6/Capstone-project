from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.routers import health, query, ingest


@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield
    query.shutdown_graph_driver()


app = FastAPI(
    title=settings.app_name,
    description="Multipurpose RAG platform: classify -> retrieve -> generate",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins in dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(query.router)
app.include_router(ingest.router)

# Exposes GET /metrics in Prometheus text format, plus default HTTP request
# count/latency histograms — Module 11 component.
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/")
async def root() -> dict:
    return {"service": settings.app_name, "environment": settings.environment}
