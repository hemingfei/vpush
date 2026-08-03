"""应用入口：FastAPI + 调度器生命周期。"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import create_api_router
from .config import load_config
from .db import DB
from .fetchers import build_fetchers
from .notifiers import build_notifiers
from .scheduler import Scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app(config=None, db_path: str | Path | None = None) -> FastAPI:
    config = config or load_config()
    if db_path is not None:
        config.db_path = str(db_path)
    db = DB(config.db_path)
    fetchers = build_fetchers(config)
    notifiers = build_notifiers(config)
    scheduler = Scheduler(db, fetchers, notifiers, config.polling)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(scheduler.run())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        db.close()

    app = FastAPI(title="大V订阅", lifespan=lifespan)
    app.state.db = db

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    app.include_router(create_api_router(db, config.web.password))
    app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
    return app


app = create_app()
