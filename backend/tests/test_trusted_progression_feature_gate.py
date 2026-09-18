"""Regression tests for the disabled-by-default trusted route cutover gate."""
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from progression import feature_gated_routes as gate


PROGRESSION_PATHS = {
    "/api/me/progression/bootstrap",
    "/api/me/progression/choices",
    "/api/me/progression/lifecycle",
}


async def authenticated():
    return {"user_id": "account-from-session"}


def paths(app):
    return {route.path for route in app.routes}


@pytest.mark.parametrize("value", [
    None, "", "true", "TRUE", "1", "yes", "on", "enabled ", " disabled",
])
def test_only_exact_activation_token_enables(value):
    assert gate.trusted_progression_routes_enabled(value) is False


def test_exact_activation_token_enables():
    assert gate.trusted_progression_routes_enabled("enabled") is True


def test_disabled_registration_leaves_route_table_unchanged():
    app = FastAPI()
    before = paths(app)
    registered = gate.register_trusted_progression_routes(
        app,
        activation_value=None,
        current_user=authenticated,
        ledgers=object(),
        events=object(),
        registry=None,
    )
    assert registered is False
    assert paths(app) == before
    assert paths(app).isdisjoint(PROGRESSION_PATHS)


def test_enabled_registration_adds_only_the_three_reviewed_routes():
    app = FastAPI()
    before = paths(app)
    registered = gate.register_trusted_progression_routes(
        app,
        activation_value="enabled",
        current_user=authenticated,
        ledgers=object(),
        events=object(),
        registry={"books": {}},
    )
    assert registered is True
    assert paths(app) - before == PROGRESSION_PATHS


def test_enabled_registration_requires_trusted_registry():
    with pytest.raises(RuntimeError, match="registry required"):
        gate.register_trusted_progression_routes(
            FastAPI(),
            activation_value="enabled",
            current_user=authenticated,
            ledgers=object(),
            events=object(),
            registry=None,
        )


def test_enabled_routes_bind_server_owned_collections_registry_and_opening_pin(monkeypatch):
    bootstrap = AsyncMock(return_value={"progressionRevision": 0})
    process_choice = AsyncMock(return_value={"status": "confirmed"})
    monkeypatch.setattr(gate, "bootstrap_account_progression", bootstrap)
    monkeypatch.setattr(gate, "process_account_choice", process_choice)
    app = FastAPI()
    ledgers, events, registry = object(), object(), {"books": {}}
    gate.register_trusted_progression_routes(
        app,
        activation_value="enabled",
        current_user=authenticated,
        ledgers=ledgers,
        events=events,
        registry=registry,
    )
    http = TestClient(app)

    headers = {"X-VC-Progression": "1"}
    assert http.post("/api/me/progression/bootstrap", headers=headers).status_code == 200
    event = {
        "kind": "choice",
        "eventId": "550e8400-e29b-41d4-a716-446655440000",
        "bookId": "book1",
        "contentVersion": 1,
        "baseProgressionRevision": 0,
        "fromSceneId": "b1_c1_s1",
        "choiceId": "c1_call_out",
    }
    assert http.post("/api/me/progression/choices", headers=headers, json=event).status_code == 200
    bootstrap.assert_awaited_once_with(
        ledgers,
        registry,
        authenticated_user_id="account-from-session",
        book_id=gate.OPENING_BOOK_ID,
        content_version=gate.OPENING_CONTENT_VERSION,
        scene_id=gate.OPENING_SCENE_ID,
    )
    assert process_choice.await_args.args == (ledgers, events, registry)
    assert process_choice.await_args.kwargs["authenticated_user_id"] == "account-from-session"
    assert process_choice.await_args.kwargs["event"].eventId == event["eventId"]


@pytest.mark.asyncio
async def test_disabled_startup_performs_no_progression_index_writes(monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(gate, "AttributedMongoReservationStore", constructor)
    assert await gate.ensure_trusted_progression_indexes(
        activation_value=None,
        ledgers=object(),
        events=object(),
    ) is False
    constructor.assert_not_called()


@pytest.mark.asyncio
async def test_enabled_startup_ensures_required_progression_indexes(monkeypatch):
    ensure_indexes = AsyncMock()
    store = SimpleNamespace(ensure_indexes=ensure_indexes)
    constructor = Mock(return_value=store)
    monkeypatch.setattr(gate, "AttributedMongoReservationStore", constructor)
    ledgers, events = object(), object()
    assert await gate.ensure_trusted_progression_indexes(
        activation_value="enabled",
        ledgers=ledgers,
        events=events,
    ) is True
    constructor.assert_called_once_with(ledgers, events)
    ensure_indexes.assert_awaited_once_with()


def import_server(monkeypatch, activation_value):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "phase6c_feature_gate_import_only")
    if activation_value is None:
        monkeypatch.delenv("TRUSTED_PROGRESSION_ROUTES", raising=False)
    else:
        monkeypatch.setenv("TRUSTED_PROGRESSION_ROUTES", activation_value)
    sys.modules.pop("server", None)
    return importlib.import_module("server")


@pytest.mark.parametrize("activation_value", [None, "true", "enabled "])
def test_server_route_table_is_off_by_default_and_for_unrecognised_values(
    monkeypatch, activation_value,
):
    server = import_server(monkeypatch, activation_value)
    try:
        assert server.TRUSTED_PROGRESSION_ENABLED is False
        assert server.TRUSTED_PROGRESSION_ROUTES_REGISTERED is False
        assert paths(server.app).isdisjoint(PROGRESSION_PATHS)
    finally:
        server.client.close()
        sys.modules.pop("server", None)


def test_server_route_table_requires_exact_explicit_activation(monkeypatch):
    server = import_server(monkeypatch, "enabled")
    try:
        assert server.TRUSTED_PROGRESSION_ENABLED is True
        assert server.TRUSTED_PROGRESSION_ROUTES_REGISTERED is True
        assert PROGRESSION_PATHS.issubset(paths(server.app))
    finally:
        server.client.close()
        sys.modules.pop("server", None)
