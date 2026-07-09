from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe — used by Docker Compose healthcheck and CI smoke test."""
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict:
    """Readiness probe — extend this once real indices/DB connections exist,
    so orchestration can tell 'process is up' apart from 'can serve queries'.
    """
    return {"status": "ready"}
