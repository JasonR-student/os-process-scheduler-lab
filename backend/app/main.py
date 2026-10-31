from __future__ import annotations

from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import router
from .models import SessionConfig
from .simulation import SimulationSession


@asynccontextmanager
async def lifespan(app: FastAPI):
    live_session = SimulationSession(
        SessionConfig(
            mode="simulation",
            continuous=True,
            initial_processes=6,
            max_processes=48,
            tick_ms=1000,
        ),
        session_id="live",
    )
    app.state.sessions["live"] = live_session
    await live_session.start()
    yield
    for session in tuple(app.state.sessions.values()):
        try:
            await session.stop()
        except Exception:
            pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="OS Process Scheduler Lab",
        description="Interactive operating systems scheduling laboratory.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.sessions = {}
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    from .api import socket_router

    app.include_router(socket_router)

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    return app


app = create_app()
