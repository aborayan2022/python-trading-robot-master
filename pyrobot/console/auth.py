"""Authentication and Role-Based Access Control (RBAC) for the management console.

Defines three roles:
    - MANAGER: Full administrative and execution control.
    - DEV: Telemetry, metrics, logs, and tamper-evident audit ledger inspection (no control).
    - VIEWER: Overview, positions, orders, charts, and reporting only.

Tokens are configured via `PYROBOT_CONSOLE_TOKENS` and sessions are cryptographically
signed with HMAC-SHA256 via `PYROBOT_CONSOLE_SECRET`.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from enum import Enum
from typing import Callable, Dict, Optional, Tuple

from fastapi import Cookie, Depends, Header, HTTPException, status

from pyrobot.audit.ledger import AuditAction, AuditLedger
from pyrobot.logging_config import get_logger

logger = get_logger("console_auth")

DEFAULT_SECRET = "pyrobot-console-hmac-secret-dev-2026"
LIVE_CONFIRMATION_PHRASE = "I UNDERSTAND THE RISKS OF LIVE TRADING"


class ConsoleRole(str, Enum):
    """User authorization roles with hierarchical permissions."""

    VIEWER = "viewer"
    DEV = "dev"
    MANAGER = "manager"


# Numerical level for permission hierarchy: MANAGER > DEV > VIEWER
ROLE_LEVELS: Dict[ConsoleRole, int] = {
    ConsoleRole.VIEWER: 1,
    ConsoleRole.DEV: 2,
    ConsoleRole.MANAGER: 3,
}


def get_configured_tokens() -> Dict[str, ConsoleRole]:
    """Parse PYROBOT_CONSOLE_TOKENS env var or return safe development defaults.

    Format: `manager:token1,dev:token2,viewer:token3`
    """
    raw = os.environ.get("PYROBOT_CONSOLE_TOKENS", "").strip()
    tokens: Dict[str, ConsoleRole] = {}

    if raw:
        for pair in raw.split(","):
            pair = pair.strip()
            if ":" in pair:
                r_name, tok = pair.split(":", 1)
                r_name = r_name.strip().lower()
                tok = tok.strip()
                try:
                    role = ConsoleRole(r_name)
                    tokens[tok] = role
                except ValueError:
                    logger.warning("Unknown role '%s' in PYROBOT_CONSOLE_TOKENS", r_name)

    if not tokens:
        # Development / test fallbacks
        tokens = {
            "manager-token": ConsoleRole.MANAGER,
            "dev-token": ConsoleRole.DEV,
            "viewer-token": ConsoleRole.VIEWER,
        }

    return tokens


def get_console_secret() -> str:
    """Retrieve secret key for HMAC session cookie signing."""
    return os.environ.get("PYROBOT_CONSOLE_SECRET", DEFAULT_SECRET)


def sign_session(role: ConsoleRole, max_age_seconds: int = 86400) -> str:
    """Create a tamper-proof signed session string: role:expiry:signature."""
    secret = get_console_secret().encode("utf-8")
    expiry = int(time.time()) + max_age_seconds
    payload = f"{role.value}:{expiry}"
    sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_session(session_cookie: str) -> Optional[ConsoleRole]:
    """Verify HMAC signature and expiry of a session cookie."""
    try:
        parts = session_cookie.split(":")
        if len(parts) != 3:
            return None
        role_str, expiry_str, sig = parts
        expiry = int(expiry_str)
        if time.time() > expiry:
            return None  # Expired

        payload = f"{role_str}:{expiry_str}"
        secret = get_console_secret().encode("utf-8")
        expected_sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(sig, expected_sig):
            return None

        return ConsoleRole(role_str)
    except Exception:
        return None


def authenticate_request(
    authorization: Optional[str] = Header(None),
    session: Optional[str] = Cookie(None),
) -> ConsoleRole:
    """Extract and validate credentials from Authorization header or session cookie."""
    tokens = get_configured_tokens()

    # 1. Bearer Token
    if authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            tok = parts[1]
            if tok in tokens:
                return tokens[tok]

    # 2. Session Cookie
    if session:
        role = verify_session(session)
        if role is not None:
            return role

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide a valid Bearer token or session cookie.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(min_role: ConsoleRole) -> Callable[[ConsoleRole], ConsoleRole]:
    """FastAPI dependency factory enforcing minimum role hierarchy."""

    def dependency(current_role: ConsoleRole = Depends(authenticate_request)) -> ConsoleRole:
        if ROLE_LEVELS.get(current_role, 0) < ROLE_LEVELS.get(min_role, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: action requires role '{min_role.value}', but you have '{current_role.value}'",
            )
        return current_role

    return dependency


def validate_live_unlock(
    role: ConsoleRole,
    confirmation_phrase: str,
    second_confirmation: bool,
    audit_ledger: AuditLedger,
    client_ip: str = "unknown",
) -> Tuple[bool, str]:
    """Validate 2-step approval and environment lock for live trading.

    Records every attempt (success or failure) to the tamper-evident AuditLedger.
    """
    allow_env = os.environ.get("PYROBOT_ALLOW_LIVE_TRADING", "").strip().lower() == "true"

    if role != ConsoleRole.MANAGER:
        err = "Only MANAGER role can request live trading unlock."
        audit_ledger.record(
            action=AuditAction.CONTROL_ACTION,
            details={
                "action": "LIVE_UNLOCK_ATTEMPT",
                "success": False,
                "reason": err,
                "role": role.value,
                "client_ip": client_ip,
            },
        )
        return False, err

    if not allow_env:
        err = (
            "Live trading is locked by environment. Set PYROBOT_ALLOW_LIVE_TRADING=true "
            "on the server before attempting unlock."
        )
        audit_ledger.record(
            action=AuditAction.CONTROL_ACTION,
            details={
                "action": "LIVE_UNLOCK_ATTEMPT",
                "success": False,
                "reason": "PYROBOT_ALLOW_LIVE_TRADING_NOT_TRUE",
                "client_ip": client_ip,
            },
        )
        return False, err

    if confirmation_phrase.strip() != LIVE_CONFIRMATION_PHRASE:
        err = f"Confirmation phrase mismatch. Expected exactly: '{LIVE_CONFIRMATION_PHRASE}'"
        audit_ledger.record(
            action=AuditAction.CONTROL_ACTION,
            details={
                "action": "LIVE_UNLOCK_ATTEMPT",
                "success": False,
                "reason": "INVALID_CONFIRMATION_PHRASE",
                "client_ip": client_ip,
            },
        )
        return False, err

    if not second_confirmation:
        err = "Second step confirmation checkbox is required."
        audit_ledger.record(
            action=AuditAction.CONTROL_ACTION,
            details={
                "action": "LIVE_UNLOCK_ATTEMPT",
                "success": False,
                "reason": "MISSING_SECOND_CONFIRMATION",
                "client_ip": client_ip,
            },
        )
        return False, err

    # Passed all 4 guards
    audit_ledger.record(
        action=AuditAction.CONTROL_ACTION,
        details={
            "action": "LIVE_UNLOCK_SUCCESS",
            "success": True,
            "role": role.value,
            "client_ip": client_ip,
        },
    )
    return True, "Live trading unlocked successfully."
