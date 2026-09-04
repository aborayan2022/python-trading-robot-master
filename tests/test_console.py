"""Tests for PyRobot Management Console: API, RBAC, Supervisor, and Safety Gates."""

import json
import os
import time
from typing import Dict
from unittest.mock import patch

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from pyrobot.console.app import create_app
from pyrobot.console.supervisor import ConsoleConfig, RuntimeSupervisor, SupervisorState


@pytest.fixture
def test_supervisor(tmp_path) -> RuntimeSupervisor:
    """Fixture providing a fresh isolated RuntimeSupervisor."""
    audit_file = str(tmp_path / "test_audit.jsonl")
    metrics_file = str(tmp_path / "test_metrics.jsonl")
    config = ConsoleConfig(
        profile="replay",
        symbols=["MSFT", "AAPL"],
        signal_source="example",
        bar_interval=0.01,
        n_bars=200,
        seed=42,
        initial_balance=100_000.0,
        audit_path=audit_file,
        metrics_path=metrics_file,
    )
    supervisor = RuntimeSupervisor(config)
    yield supervisor
    supervisor.stop(timeout=2.0)


@pytest.fixture
def client(test_supervisor: RuntimeSupervisor, tmp_path) -> TestClient:
    """Fixture providing a TestClient configured with test tokens."""
    tokens_env = "manager:test-manager-token,dev:test-dev-token,viewer:test-viewer-token"
    settings_path = str(tmp_path / "console_settings.json")
    with patch.dict(os.environ, {"PYROBOT_CONSOLE_TOKENS": tokens_env}):
        app = create_app(test_supervisor, settings_path=settings_path)
        with TestClient(app) as test_client:
            yield test_client


def auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── RBAC & Authentication Matrix ─────────────────────────────────────────────


class TestConsoleRBACMatrix:
    """Verifies 401/403 role matrix across all endpoint categories."""

    def test_unauthenticated_request_rejected(self, client: TestClient):
        res = client.get("/api/overview")
        assert res.status_code == 401

        res = client.post("/api/control/start")
        assert res.status_code == 401

    def test_viewer_role_access(self, client: TestClient):
        headers = auth_headers("test-viewer-token")

        # Viewer can read monitoring endpoints
        assert client.get("/api/overview", headers=headers).status_code == 200
        assert client.get("/api/positions", headers=headers).status_code == 200
        assert client.get("/api/orders", headers=headers).status_code == 200
        assert client.get("/api/signals", headers=headers).status_code == 200
        assert client.get("/api/metrics/history", headers=headers).status_code == 200

        # Viewer is forbidden from audit
        assert client.get("/api/audit", headers=headers).status_code == 403

        # Viewer is forbidden from control plane
        assert client.post("/api/control/start", headers=headers).status_code == 403
        assert client.post("/api/control/stop", headers=headers).status_code == 403
        assert client.patch("/api/control/risk-limits", json={}, headers=headers).status_code == 403

    def test_dev_role_access(self, client: TestClient):
        headers = auth_headers("test-dev-token")

        # Dev can read telemetry and audit
        assert client.get("/api/overview", headers=headers).status_code == 200
        assert client.get("/api/audit", headers=headers).status_code == 200

        # Dev is forbidden from control plane
        assert client.post("/api/control/start", headers=headers).status_code == 403
        assert client.post("/api/control/stop", headers=headers).status_code == 403
        assert client.patch("/api/control/risk-limits", json={}, headers=headers).status_code == 403

    def test_manager_role_access(self, client: TestClient, test_supervisor: RuntimeSupervisor):
        headers = auth_headers("test-manager-token")

        # Manager can read everything
        assert client.get("/api/overview", headers=headers).status_code == 200
        assert client.get("/api/audit", headers=headers).status_code == 200
        assert client.get("/api/control/risk-limits", headers=headers).status_code == 200

        # Manager can control
        res = client.post("/api/control/start", headers=headers)
        assert res.status_code == 200
        assert test_supervisor.state in (SupervisorState.RUNNING, SupervisorState.STARTING)

    def test_login_endpoint_sets_signed_cookie(self, client: TestClient):
        res = client.post("/api/auth/login", json={"token": "test-manager-token"})
        assert res.status_code == 200
        assert res.json()["role"] == "manager"
        session_cookie = res.cookies.get("session")
        assert session_cookie is not None

        # Subsequent request with cookie succeeds without Bearer header
        me_res = client.get("/api/auth/me", headers={"Cookie": f"session={session_cookie}"})
        assert me_res.status_code == 200
        assert me_res.json()["role"] == "manager"
        assert me_res.json()["can_control"] is True

    def test_invalid_token_rejected(self, client: TestClient):
        res = client.post("/api/auth/login", json={"token": "wrong-token"})
        assert res.status_code == 401


# ── Supervisor Lifecycle & Control Tests ──────────────────────────────────────


class TestSupervisorLifecycle:
    """Verifies start, pause, resume, stop, and dynamic re-configuration."""

    def test_lifecycle_start_pause_resume_stop(self, test_supervisor: RuntimeSupervisor):
        assert test_supervisor.state == SupervisorState.STOPPED

        # 1. Start
        started = test_supervisor.start()
        assert started is True
        assert test_supervisor.state == SupervisorState.RUNNING

        # 2. Pause
        paused = test_supervisor.pause()
        assert paused is True
        assert test_supervisor.state == SupervisorState.PAUSED
        assert test_supervisor.loop is not None
        assert test_supervisor.loop.is_paused is True

        # 3. Resume
        resumed = test_supervisor.resume()
        assert resumed is True
        assert test_supervisor.state == SupervisorState.RUNNING
        assert test_supervisor.loop.is_paused is False

        # 4. Stop
        stopped = test_supervisor.stop()
        assert stopped is True
        assert test_supervisor.state == SupervisorState.STOPPED

    def test_apply_config_restarts_cleanly(self, test_supervisor: RuntimeSupervisor):
        test_supervisor.start()
        assert test_supervisor.config.symbols == ["MSFT", "AAPL"]

        new_config = ConsoleConfig(
            profile="replay",
            symbols=["NVDA", "TSLA"],
            signal_source="example",
            bar_interval=0.5,
            n_bars=500,
            audit_path=test_supervisor.config.audit_path,
            metrics_path=test_supervisor.config.metrics_path,
        )

        success = test_supervisor.apply_config(new_config)
        assert success is True
        assert test_supervisor.config.symbols == ["NVDA", "TSLA"]
        assert test_supervisor.state == SupervisorState.RUNNING


# ── Risk Limits & Safety Gates Tests ─────────────────────────────────────────


class TestRiskLimitsAndSafetyGates:
    """Verifies validated PATCH limits, kill switch triggers, and live unlock."""

    def test_patch_valid_risk_limits(self, client: TestClient, test_supervisor: RuntimeSupervisor):
        headers = auth_headers("test-manager-token")
        test_supervisor.start()

        payload = {"max_position_size_pct": 0.08, "default_stop_distance_pct": 0.025}
        res = client.patch("/api/control/risk-limits", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["limits"]["max_position_size_pct"] == 0.08
        assert data["limits"]["default_stop_distance_pct"] == 0.025

    def test_patch_invalid_risk_limits_rejected(self, client: TestClient):
        headers = auth_headers("test-manager-token")
        # Position size <= 0 is invalid
        res = client.patch("/api/control/risk-limits", json={"max_position_size_pct": -0.1}, headers=headers)
        assert res.status_code == 400

        # Drawdown > 0.50 is invalid
        res = client.patch("/api/control/risk-limits", json={"max_portfolio_drawdown_pct": 0.80}, headers=headers)
        assert res.status_code == 400

    def test_kill_switch_activate_and_reset(self, client: TestClient, test_supervisor: RuntimeSupervisor):
        headers = auth_headers("test-manager-token")
        test_supervisor.start()

        # Reject unconfirmed activation
        unconfirmed = client.post(
            "/api/control/kill-switch/activate",
            json={"reason": "TEST", "confirmed": False},
            headers=headers,
        )
        assert unconfirmed.status_code == 400

        # Confirm activation
        confirmed = client.post(
            "/api/control/kill-switch/activate",
            json={"reason": "TEST", "detail": "test alert", "confirmed": True},
            headers=headers,
        )
        assert confirmed.status_code == 200
        overview = client.get("/api/overview", headers=headers).json()
        assert overview["kill_switch_active"] is True

        # Confirm reset
        reset_res = client.post(
            "/api/control/kill-switch/reset",
            json={"reason": "TEST_RESET", "confirmed": True},
            headers=headers,
        )
        assert reset_res.status_code == 200
        overview_after = client.get("/api/overview", headers=headers).json()
        assert overview_after["kill_switch_active"] is False

    def test_live_unlock_safety_gate(self, client: TestClient, test_supervisor: RuntimeSupervisor):
        headers = auth_headers("test-manager-token")

        # 1. Rejected if env var is missing/false
        with patch.dict(os.environ, {"PYROBOT_ALLOW_LIVE_TRADING": "false"}):
            res = client.post(
                "/api/control/live-unlock",
                json={
                    "confirmation_phrase": "I UNDERSTAND THE RISKS OF LIVE TRADING",
                    "second_confirmation": True,
                },
                headers=headers,
            )
            assert res.status_code == 400
            assert "locked by environment" in res.json()["detail"]

        # 2. Rejected with incorrect phrase
        with patch.dict(os.environ, {"PYROBOT_ALLOW_LIVE_TRADING": "true"}):
            res = client.post(
                "/api/control/live-unlock",
                json={
                    "confirmation_phrase": "WRONG PHRASE",
                    "second_confirmation": True,
                },
                headers=headers,
            )
            assert res.status_code == 400
            assert "phrase mismatch" in res.json()["detail"]

        # 3. Rejected without second confirmation
        with patch.dict(os.environ, {"PYROBOT_ALLOW_LIVE_TRADING": "true"}):
            res = client.post(
                "/api/control/live-unlock",
                json={
                    "confirmation_phrase": "I UNDERSTAND THE RISKS OF LIVE TRADING",
                    "second_confirmation": False,
                },
                headers=headers,
            )
            assert res.status_code == 400
            assert "Second step" in res.json()["detail"]

        # 4. Succeeds when all 4 guards are met
        with patch.dict(os.environ, {"PYROBOT_ALLOW_LIVE_TRADING": "true"}):
            res = client.post(
                "/api/control/live-unlock",
                json={
                    "confirmation_phrase": "I UNDERSTAND THE RISKS OF LIVE TRADING",
                    "second_confirmation": True,
                },
                headers=headers,
            )
            assert res.status_code == 200
            assert res.json()["status"] == "ok"
            assert test_supervisor.config.allow_live_trading is True


# ── Audit Trail & Telemetry Tests ────────────────────────────────────────────


class TestAuditTrailAndTelemetry:
    """Verifies control action auditing, data freshness, and SSE streaming."""

    def test_control_actions_recorded_in_audit_ledger(self, client: TestClient, test_supervisor: RuntimeSupervisor):
        headers = auth_headers("test-manager-token")

        # Start supervisor
        client.post("/api/control/start", headers=headers)
        # Update limits
        client.patch("/api/control/risk-limits", json={"max_position_size_pct": 0.07}, headers=headers)
        # Stop supervisor
        client.post("/api/control/stop", headers=headers)

        # Retrieve audit events via API
        audit_res = client.get("/api/audit", headers=headers)
        assert audit_res.status_code == 200
        events = audit_res.json()
        assert len(events) > 0

        # Verify CONTROL_ACTION is present in audit chain
        control_events = [e for e in events if e.get("action") == "CONTROL_ACTION"]
        assert len(control_events) >= 3

        # Verify audit file integrity
        assert test_supervisor.audit_ledger.verify_integrity() is True

    def test_overview_telemetry_and_data_freshness(self, client: TestClient, test_supervisor: RuntimeSupervisor):
        headers = auth_headers("test-viewer-token")
        test_supervisor.start()

        # Let loop process at least one bar
        start_t = time.time()
        while time.time() - start_t < 3.0:
            overview = client.get("/api/overview", headers=headers).json()
            if overview.get("bars_processed", 0) > 0:
                break
            time.sleep(0.05)

        res = client.get("/api/overview", headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert "equity" in data
        assert "drawdown" in data
        assert "data_freshness" in data
        assert "market_session" in data
        assert "alpaca_status" in data

    def test_sse_stream_initial_event(self, client: TestClient):
        headers = auth_headers("test-viewer-token")
        response = client.get("/api/stream?once=true", headers=headers)
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        lines = response.text.strip().split("\n")
        data_line = next(line for line in lines if line.startswith("data:"))
        payload_str = data_line.replace("data:", "").strip()
        payload = json.loads(payload_str)
        assert "equity" in payload
        assert "state" in payload


# ── Console Settings / Theme API ──────────────────────────────────────────────


class TestConsoleSettingsTheme:
    """Theme/branding settings endpoints: RBAC, validation, persistence, reset."""

    def test_get_theme_requires_manager(self, client):
        assert client.get("/api/settings/theme").status_code == 401
        assert client.get("/api/settings/theme", headers=auth_headers("test-viewer-token")).status_code == 403
        assert client.get("/api/settings/theme", headers=auth_headers("test-dev-token")).status_code == 403

    def test_get_theme_returns_defaults(self, client):
        res = client.get("/api/settings/theme", headers=auth_headers("test-manager-token"))
        assert res.status_code == 200
        data = res.json()
        assert data["theme"]["primary_color"] == "#3b82f6"
        assert data["branding"]["platform_name"] == "PyRobot"

    def test_put_theme_persists_valid_partial_update(self, client):
        headers = auth_headers("test-manager-token")
        payload = {"theme": {"primary_color": "#ff0000"}, "branding": {"platform_name": "Custom"}}
        res = client.put("/api/settings/theme", json=payload, headers=headers)
        assert res.status_code == 200
        assert res.json()["settings"]["theme"]["primary_color"] == "#ff0000"
        assert res.json()["settings"]["branding"]["platform_name"] == "Custom"
        # Unchanged fields must survive the merge
        assert "accent_color" in res.json()["settings"]["theme"]

        # Persistence check: a fresh GET reflects the change
        get_res = client.get("/api/settings/theme", headers=headers)
        assert get_res.json()["theme"]["primary_color"] == "#ff0000"

    def test_put_theme_empty_body_rejected(self, client):
        res = client.put("/api/settings/theme", json={}, headers=auth_headers("test-manager-token"))
        assert res.status_code == 400

    def test_post_theme_reset_restores_defaults(self, client):
        headers = auth_headers("test-manager-token")
        client.put("/api/settings/theme", json={"theme": {"primary_color": "#00ff00"}}, headers=headers)
        res = client.post("/api/settings/theme/reset", headers=headers)
        assert res.status_code == 200
        assert res.json()["settings"]["theme"]["primary_color"] == "#3b82f6"

    def test_put_theme_rejects_non_manager(self, client):
        assert client.put("/api/settings/theme", json={"theme": {}}, headers=auth_headers("test-dev-token")).status_code == 403
        assert client.post("/api/settings/theme/reset", headers=auth_headers("test-viewer-token")).status_code == 403

    def test_put_theme_rejects_invalid_hex(self, client):
        headers = auth_headers("test-manager-token")
        res = client.put("/api/settings/theme", json={"theme": {"primary_color": "red"}}, headers=headers)
        assert res.status_code == 422
        res = client.put("/api/settings/theme", json={"theme": {"primary_color": "#12"}}, headers=headers)
        assert res.status_code == 422

    def test_put_theme_rejects_unknown_key(self, client):
        headers = auth_headers("test-manager-token")
        res = client.put("/api/settings/theme", json={"theme": {"not_a_real_color": "#ff0000"}}, headers=headers)
        assert res.status_code == 422

    def test_put_theme_rejects_unsafe_logo_url(self, client):
        headers = auth_headers("test-manager-token")
        bad = "javascript:alert(1)"
        res = client.put("/api/settings/theme", json={"branding": {"logo_url": bad}}, headers=headers)
        assert res.status_code == 422
        bad_data = "data:image/png;base64,AAAA"
        res = client.put("/api/settings/theme", json={"branding": {"logo_url": bad_data}}, headers=headers)
        assert res.status_code == 422

    def test_put_theme_accepts_safe_logo_url(self, client):
        headers = auth_headers("test-manager-token")
        for url in ("https://example.com/logo.png", "/static/logo.png"):
            res = client.put("/api/settings/theme", json={"branding": {"logo_url": url}}, headers=headers)
            assert res.status_code == 200, url
            assert res.json()["settings"]["branding"]["logo_url"] == url
