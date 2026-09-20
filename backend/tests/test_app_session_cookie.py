"""Regression coverage for the app-specific authenticated session cookie."""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Response
from starlette.requests import Request


def import_server(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "phase6c_session_cookie_import_only")
    sys.modules.pop("server", None)
    return importlib.import_module("server")


def request_with_cookie(cookie: str) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/auth/me",
        "query_string": b"",
        "headers": [(b"cookie", cookie.encode())],
        "scheme": "https",
        "server": ("testserver", 443),
        "client": ("testclient", 1234),
    })


@pytest.mark.asyncio
async def test_app_cookie_is_preferred_over_legacy_cookie(monkeypatch):
    server = import_server(monkeypatch)
    try:
        session = {
            "user_id": "user-1",
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        }
        find_session = AsyncMock(return_value=session)
        server.sessions = SimpleNamespace(find_one=find_session)
        server.users = SimpleNamespace(find_one=AsyncMock(return_value={
            "user_id": "user-1", "email": "player@example.com",
        }))

        user = await server._current_user(request_with_cookie(
            "__Host-vc_session=app-token; session_token=legacy-token",
        ))

        assert user["email"] == "player@example.com"
        find_session.assert_awaited_once_with(
            {"session_token": "app-token"}, {"_id": 0},
        )
    finally:
        server.client.close()
        sys.modules.pop("server", None)


@pytest.mark.asyncio
async def test_legacy_cookie_remains_valid_during_migration(monkeypatch):
    server = import_server(monkeypatch)
    try:
        session = {
            "user_id": "user-1",
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        }
        find_session = AsyncMock(return_value=session)
        server.sessions = SimpleNamespace(find_one=find_session)
        server.users = SimpleNamespace(find_one=AsyncMock(return_value={
            "user_id": "user-1", "email": "player@example.com",
        }))

        await server._current_user(request_with_cookie("session_token=legacy-token"))

        find_session.assert_awaited_once_with(
            {"session_token": "legacy-token"}, {"_id": 0},
        )
    finally:
        server.client.close()
        sys.modules.pop("server", None)


@pytest.mark.asyncio
async def test_logout_clears_app_and_legacy_cookie_names(monkeypatch):
    server = import_server(monkeypatch)
    try:
        delete_one = AsyncMock()
        server.sessions = SimpleNamespace(delete_one=delete_one)
        response = Response()

        assert await server.auth_logout(
            request_with_cookie("__Host-vc_session=app-token"), response,
        ) == {"ok": True}

        delete_one.assert_awaited_once_with({"session_token": "app-token"})
        cookies = "\n".join(response.headers.getlist("set-cookie"))
        assert "__Host-vc_session=" in cookies
        assert "session_token=" in cookies
    finally:
        server.client.close()
        sys.modules.pop("server", None)
