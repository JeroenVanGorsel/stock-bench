"""FastAPI app for the dashboard and control plane."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import STATIC_DIR, get_settings
from .logging_utils import setup_logging
from .orchestrator import MarketOrchestrator
from .storage import SQLiteRepository


logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    log_path = setup_logging()
    settings = get_settings()
    repository = SQLiteRepository(settings.database_path)
    orchestrator = MarketOrchestrator(repository)
    orchestrator.bootstrap()

    app = FastAPI(title="Stock Bench")
    app.state.repository = repository
    app.state.orchestrator = orchestrator
    logger.info("api app initialized | database=%s log=%s", settings.database_path, log_path)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/market")
    async def market() -> dict:
        return orchestrator.market_summary()

    @app.get("/api/tasks")
    async def tasks(limit: int = 50) -> list[dict]:
        return [task.to_dict() for task in repository.list_tasks(limit=limit)]

    @app.post("/api/rounds/run")
    async def run_round() -> dict:
        try:
            result = await orchestrator.run_one_round()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result.to_dict()

    @app.post("/api/rounds/run-batch")
    async def run_batch(count: int = 3) -> dict:
        try:
            results = await orchestrator.run_batch(count)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"count": len(results), "rounds": [item.to_dict() for item in results]}

    @app.post("/api/rounds/run-sweep")
    async def run_sweep(count: int = 50) -> dict:
        try:
            return await orchestrator.run_sweep(count)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
