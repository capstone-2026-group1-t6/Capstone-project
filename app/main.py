from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.routers import health, query

app = FastAPI(
    title=settings.app_name,
    description="Multipurpose RAG platform: classify -> retrieve -> generate",
)

app.include_router(health.router)
app.include_router(query.router)

# Exposes GET /metrics in Prometheus text format, plus default HTTP request
# count/latency histograms — Module 11 component.
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/")
async def root() -> dict:
    return {"service": settings.app_name, "environment": settings.environment}
