"""REST and SSE API endpoints for the PyRobot management console."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from pyrobot.audit.ledger import AuditAction
from pyrobot.console.auth import (
    ConsoleRole,
    authenticate_request,
    get_configured_tokens,
    require_role,
    sign_session,
    validate_live_unlock,
)
from pyrobot.console.supervisor import ConsoleConfig, RuntimeSupervisor
from pyrobot.logging_config import get_logger
from pyrobot.risk.kill_switch import KillSwitchReason

logger = get_logger("console_api")


class LoginRequest(BaseModel):
    token: str


class ConfigUpdateRequest(BaseModel):
    profile: Optional[str] = None
    symbols: Optional[List[str]] = None
    signal_source: Optional[str] = None
    bar_interval: Optional[float] = None
    n_bars: Optional[int] = None
    seed: Optional[int] = None
    initial_balance: Optional[float] = None
    mode: Optional[str] = None
    dry_run: Optional[bool] = None


class KillSwitchActivateRequest(BaseModel):
    reason: str = "MANUAL_CONSOLE_TRIGGER"
    detail: str = "Activated by manager from console"
    confirmed: bool = False


class KillSwitchResetRequest(BaseModel):
    reason: str = "MANUAL_CONSOLE_RESET"
    confirmed: bool = False


class LiveUnlockRequest(BaseModel):
    confirmation_phrase: str
    second_confirmation: bool = False


def create_api_router(supervisor: RuntimeSupervisor) -> APIRouter:
    """Factory creating configured API router wired to the active RuntimeSupervisor."""
    router = APIRouter(prefix="/api")

    # ── Authentication ────────────────────────────────────────────────────────

    @router.post("/auth/login")
    def login(payload: LoginRequest, response: Response) -> Dict[str, Any]:
        tokens = get_configured_tokens()
        token = payload.token.strip()
        if token not in tokens:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid access token",
            )
        role = tokens[token]
        signed_cookie = sign_session(role)
        response.set_cookie(
            key="session",
            value=signed_cookie,
            httponly=True,
            samesite="lax",
            max_age=86400,
        )
        return {"status": "ok", "role": role.value}

    @router.post("/auth/logout")
    def logout(response: Response) -> Dict[str, Any]:
        response.delete_cookie("session")
        return {"status": "ok"}

    @router.get("/auth/me")
    def get_me(role: ConsoleRole = Depends(authenticate_request)) -> Dict[str, Any]:
        return {
            "role": role.value,
            "can_control": role == ConsoleRole.MANAGER,
            "can_audit": role in (ConsoleRole.MANAGER, ConsoleRole.DEV),
        }

    # ── Telemetry & Monitoring (VIEWER+) ──────────────────────────────────────

    @router.get("/overview")
    def get_overview(_role: ConsoleRole = Depends(require_role(ConsoleRole.VIEWER))) -> Dict[str, Any]:
        return supervisor.get_overview()

    @router.get("/positions")
    def get_positions(_role: ConsoleRole = Depends(require_role(ConsoleRole.VIEWER))) -> List[Dict[str, Any]]:
        return supervisor.get_positions()

    @router.get("/orders")
    def get_orders(
        state: Optional[str] = Query(None, description="Filter by order state"),
        _role: ConsoleRole = Depends(require_role(ConsoleRole.VIEWER)),
    ) -> List[Dict[str, Any]]:
        return supervisor.get_orders(state=state)

    @router.get("/signals")
    def get_signals(
        limit: int = Query(50, ge=1, le=500),
        _role: ConsoleRole = Depends(require_role(ConsoleRole.VIEWER)),
    ) -> List[Dict[str, Any]]:
        return supervisor.get_signals(limit=limit)

    @router.get("/metrics/history")
    def get_metrics_history(
        limit: int = Query(200, ge=10, le=2000),
        _role: ConsoleRole = Depends(require_role(ConsoleRole.VIEWER)),
    ) -> List[Dict[str, Any]]:
        metrics_file = Path(supervisor.config.metrics_path)
        if not metrics_file.exists():
            return []
        try:
            records: List[Dict[str, Any]] = []
            with metrics_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
            return records[-limit:]
        except Exception as exc:
            logger.warning("Failed to read metrics history: %s", exc)
            return []

    @router.get("/stream")
    async def sse_stream(
        request: Request,
        once: bool = False,
        _role: ConsoleRole = Depends(require_role(ConsoleRole.VIEWER)),
    ) -> StreamingResponse:
        """Server-Sent Events (SSE) streaming overview telemetry to connected clients."""

        async def event_generator():
            try:
                # Send initial snapshot immediately
                overview = supervisor.get_overview()
                yield f"data: {json.dumps(overview)}\n\n"
                if once:
                    return

                while True:
                    for _ in range(20):
                        if await request.is_disconnected():
                            return
                        await asyncio.sleep(0.1)
                    overview = supervisor.get_overview()
                    yield f"data: {json.dumps(overview)}\n\n"
            except (asyncio.CancelledError, GeneratorExit):
                return

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Audit Ledger (DEV+) ───────────────────────────────────────────────────

    @router.get("/audit")
    def get_audit(
        action: Optional[str] = Query(None),
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        _role: ConsoleRole = Depends(require_role(ConsoleRole.DEV)),
    ) -> List[Dict[str, Any]]:
        return supervisor.get_audit_events(action=action, limit=limit, offset=offset)

    # ── Control Plane (MANAGER only) ──────────────────────────────────────────

    @router.post("/control/start")
    def control_start(_role: ConsoleRole = Depends(require_role(ConsoleRole.MANAGER))) -> Dict[str, Any]:
        success = supervisor.start()
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=supervisor.last_error or "Failed to start supervisor",
            )
        return {"status": "ok", "state": supervisor.state.value}

    @router.post("/control/stop")
    def control_stop(_role: ConsoleRole = Depends(require_role(ConsoleRole.MANAGER))) -> Dict[str, Any]:
        success = supervisor.stop()
        return {"status": "ok" if success else "error", "state": supervisor.state.value}

    @router.post("/control/pause")
    def control_pause(_role: ConsoleRole = Depends(require_role(ConsoleRole.MANAGER))) -> Dict[str, Any]:
        success = supervisor.pause()
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot pause: loop is not running",
            )
        return {"status": "ok", "state": supervisor.state.value}

    @router.post("/control/resume")
    def control_resume(_role: ConsoleRole = Depends(require_role(ConsoleRole.MANAGER))) -> Dict[str, Any]:
        success = supervisor.resume()
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot resume: loop is not paused",
            )
        return {"status": "ok", "state": supervisor.state.value}

    @router.post("/control/config")
    def control_update_config(
        payload: ConfigUpdateRequest,
        _role: ConsoleRole = Depends(require_role(ConsoleRole.MANAGER)),
    ) -> Dict[str, Any]:
        current_dict = supervisor.config.to_dict()
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        current_dict.update(updates)
        new_config = ConsoleConfig.from_dict(current_dict)
        success = supervisor.apply_config(new_config)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=supervisor.last_error or "Failed to apply configuration",
            )
        return {"status": "ok", "config": supervisor.config.to_dict()}

    @router.get("/control/risk-limits")
    def get_risk_limits(_role: ConsoleRole = Depends(require_role(ConsoleRole.MANAGER))) -> Dict[str, Any]:
        return supervisor.get_risk_limits()

    @router.patch("/control/risk-limits")
    def update_risk_limits(
        payload: Dict[str, Any],
        _role: ConsoleRole = Depends(require_role(ConsoleRole.MANAGER)),
    ) -> Dict[str, Any]:
        try:
            supervisor.update_risk_limits(payload)
            return {"status": "ok", "limits": supervisor.get_risk_limits()}
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Risk limits validation error: {exc}",
            )

    @router.post("/control/kill-switch/activate")
    def activate_kill_switch(
        payload: KillSwitchActivateRequest,
        _role: ConsoleRole = Depends(require_role(ConsoleRole.MANAGER)),
    ) -> Dict[str, Any]:
        if not payload.confirmed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Confirmation is required to activate the emergency kill switch.",
            )
        if supervisor.pipeline and supervisor.pipeline.kill_switch:
            supervisor.pipeline.kill_switch.activate(
                reason=KillSwitchReason.OPERATOR,
                detail=payload.detail,
            )
            supervisor.audit_ledger.record(
                action=AuditAction.KILL_SWITCH_TRIGGERED,
                details={"reason": payload.reason, "detail": payload.detail, "operator": "MANAGER"},
            )
        return {"status": "ok", "kill_switch_active": True}

    @router.post("/control/kill-switch/reset")
    def reset_kill_switch(
        payload: KillSwitchResetRequest,
        _role: ConsoleRole = Depends(require_role(ConsoleRole.MANAGER)),
    ) -> Dict[str, Any]:
        if not payload.confirmed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Confirmation is required to reset the kill switch.",
            )
        if supervisor.pipeline and supervisor.pipeline.kill_switch:
            supervisor.pipeline.kill_switch.reset(confirmed=True)
            supervisor.audit_ledger.record(
                action=AuditAction.KILL_SWITCH_RESET,
                details={"reason": payload.reason, "operator": "MANAGER"},
            )
        return {"status": "ok", "kill_switch_active": False}

    @router.post("/control/live-unlock")
    def control_live_unlock(
        payload: LiveUnlockRequest,
        request: Request,
        role: ConsoleRole = Depends(require_role(ConsoleRole.MANAGER)),
    ) -> Dict[str, Any]:
        client_ip = request.client.host if request.client else "unknown"
        valid, msg = validate_live_unlock(
            role=role,
            confirmation_phrase=payload.confirmation_phrase,
            second_confirmation=payload.second_confirmation,
            audit_ledger=supervisor.audit_ledger,
            client_ip=client_ip,
        )
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=msg,
            )
        supervisor.config.allow_live_trading = True
        return {"status": "ok", "message": msg}

    return router
