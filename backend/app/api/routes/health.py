"""Scaffold liveness and infrastructure readiness endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.app.db.health import check_database

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "learning-guidance-agent", "stage": "development"}


@router.get("/health/ready")
def readiness(request: Request) -> JSONResponse:
    result = check_database(request.app.state.database_engine)
    executor = request.app.state.executor
    result["scheduler"] = "ok" if executor and executor.ready else "not_ready"
    if result["status"] == "ok" and result["scheduler"] != "ok":
        result["status"] = "not_ready"
    return JSONResponse(result, status_code=200 if result["status"] == "ok" else 503)
