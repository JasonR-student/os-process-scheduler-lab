from __future__ import annotations

import asyncio
import inspect
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import Response

from .models import SessionConfig
from .real_scheduler import RealSession
from .simulation import SimulationSession


router = APIRouter(prefix="/api")
socket_router = APIRouter()


def sessions(request: Request) -> dict[str, Any]:
    return request.app.state.sessions


def get_session(request: Request, session_id: str) -> Any:
    session = sessions(request).get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


async def call_session(session: Any, method: str) -> dict[str, Any]:
    result = getattr(session, method)()
    if inspect.isawaitable(result):
        return await result
    return result


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    return {
        "ok": True,
        "service": "os-process-scheduler-lab",
        "port": 4001,
        "sessions": len(sessions(request)),
    }


@router.post("/sessions")
async def create_session(request: Request, config: SessionConfig) -> dict[str, Any]:
    session = (
        RealSession(config)
        if config.mode == "real"
        else SimulationSession(config)
    )
    sessions(request)[session.id] = session
    return {"session": session.snapshot()}


@router.get("/sessions/{session_id}")
async def read_session(request: Request, session_id: str) -> dict[str, Any]:
    return {"session": get_session(request, session_id).snapshot()}


@router.get("/sessions/{session_id}/snapshot")
async def snapshot(request: Request, session_id: str) -> dict[str, Any]:
    return {"snapshot": get_session(request, session_id).snapshot()}


@router.post("/sessions/{session_id}/start")
async def start_session(request: Request, session_id: str) -> dict[str, Any]:
    return {"snapshot": await call_session(get_session(request, session_id), "start")}


@router.post("/sessions/{session_id}/pause")
async def pause_session(request: Request, session_id: str) -> dict[str, Any]:
    return {"snapshot": await call_session(get_session(request, session_id), "pause")}


@router.post("/sessions/{session_id}/step")
async def step_session(request: Request, session_id: str) -> dict[str, Any]:
    return {"snapshot": await call_session(get_session(request, session_id), "step")}


@router.post("/sessions/{session_id}/back")
async def back_session(request: Request, session_id: str) -> dict[str, Any]:
    session = get_session(request, session_id)
    if session.mode == "real":
        raise HTTPException(
            status_code=409,
            detail="real PID mode does not support rewind",
        )
    return {"snapshot": await call_session(session, "back")}


@router.post("/sessions/{session_id}/reset")
async def reset_session(request: Request, session_id: str) -> dict[str, Any]:
    return {"snapshot": await call_session(get_session(request, session_id), "reset")}


@router.post("/sessions/{session_id}/stop")
async def stop_session(request: Request, session_id: str) -> dict[str, Any]:
    return {"snapshot": await call_session(get_session(request, session_id), "stop")}


@router.get("/sessions/{session_id}/report")
async def report(request: Request, session_id: str) -> dict[str, Any]:
    return {"report": get_session(request, session_id).report()}


@router.get("/sessions/{session_id}/export")
async def export_session(
    request: Request, session_id: str, format: str = "json"
) -> Response:
    if format not in {"json", "csv"}:
        raise HTTPException(status_code=400, detail="format must be json or csv")
    content, media_type = get_session(request, session_id).export(format)
    filename = f"session-{session_id}.{format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@socket_router.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    session = websocket.app.state.sessions.get(session_id)
    if session is None:
        await websocket.send_json(
            {"type": "error", "payload": {"message": "session not found"}}
        )
        await websocket.close(code=4404)
        return

    queue = session.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat", "time": session.now})
    except Exception:
        session.unsubscribe(queue)
