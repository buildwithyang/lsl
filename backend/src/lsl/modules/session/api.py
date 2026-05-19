from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from lsl.modules.session.schema import (
    ApiResponse,
    CreateSessionRequest,
    SessionData,
    SessionListResponseData,
    UpdateSessionRequest,
)
from lsl.modules.session.service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


def get_session_service(request: Request) -> SessionService:
    service = getattr(request.app.state, "session_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Session service is not initialized")
    return cast(SessionService, service)


@router.post("", response_model=ApiResponse[SessionData])
def create_session(
    payload: CreateSessionRequest,
    session_service: SessionService = Depends(get_session_service),
):
    try:
        session = session_service.create_session(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ApiResponse(data=session)


@router.get("", response_model=ApiResponse[SessionListResponseData])
def list_sessions(
    limit: int = 20,
    offset: int = 0,
    query: str | None = None,
    status: int | None = None,
    session_service: SessionService = Depends(get_session_service),
):
    try:
        items = session_service.list_sessions(
            limit=limit,
            offset=offset,
            query=query,
            status=status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ApiResponse(data=SessionListResponseData(items=items))


@router.get("/{session_id}", response_model=ApiResponse[SessionData])
def get_session(
    session_id: str,
    refresh: bool = True,
    session_service: SessionService = Depends(get_session_service),
):
    try:
        session = session_service.get_session(session_id, auto_refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ApiResponse(data=session)


@router.patch("/{session_id}", response_model=ApiResponse[SessionData])
def update_session(
    session_id: str,
    payload: UpdateSessionRequest,
    session_service: SessionService = Depends(get_session_service),
):
    try:
        session = session_service.update_session(session_id=session_id, payload=payload)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "session not found" else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ApiResponse(data=session)


@router.delete("/{session_id}", response_model=ApiResponse[dict])
def delete_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    try:
        deleted = session_service.delete_session(session_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="session not found")
    return ApiResponse(data={"session_id": session_id, "deleted": True})
