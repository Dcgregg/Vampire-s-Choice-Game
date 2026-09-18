"""Chromium cookie session -> trusted API -> disposable MongoDB smoke test."""
import asyncio
import socket
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request
from playwright.async_api import async_playwright
import uvicorn

from progression.attributed_mongo_reservations import AttributedMongoReservationStore
from progression.feature_gated_routes import register_trusted_progression_routes
from progression.trusted_content import load_registry
from test_story_claim_transaction_integration import collections  # noqa: F401


@pytest.mark.asyncio
async def test_chromium_cookie_session_confirms_lifecycle_and_first_choice(collections):
    anonymous_saves, _ = collections
    database = anonymous_saves.database
    ledgers, events, sessions = database.ledgers, database.events, database.sessions
    await AttributedMongoReservationStore(ledgers, events).ensure_indexes()
    token = f"browser-session-{uuid4().hex}"
    account_id = f"browser-account-{uuid4().hex}"
    await sessions.insert_one({"session_token": token, "user_id": account_id})

    async def current_user(request: Request):
        session = await sessions.find_one({
            "session_token": request.cookies.get("session_token"),
        })
        if session is None:
            raise HTTPException(status_code=401, detail={"error": "not_authenticated"})
        return {"user_id": session["user_id"]}

    app = FastAPI()
    register_trusted_progression_routes(
        app, activation_value="enabled", current_user=current_user,
        ledgers=ledgers, events=events, registry=load_registry(),
    )

    @app.get("/test-only-browser-page")
    async def page():
        from fastapi.responses import HTMLResponse
        return HTMLResponse("<!doctype html><html><body>Trusted progression test</body></html>")

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="error", access_log=False,
    ))
    server_task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            if server_task.done():
                await server_task
            await asyncio.sleep(0.05)
        assert server.started
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                await context.add_cookies([{
                    "name": "session_token", "value": token,
                    "url": origin, "httpOnly": True, "sameSite": "Lax",
                }])
                page = await context.new_page()
                await page.goto(f"{origin}/test-only-browser-page")
                result = await page.evaluate("""async () => {
                    const withoutCsrf = await fetch('/api/me/progression/bootstrap', {method: 'POST'});
                    const headers = {'Content-Type': 'application/json', 'X-VC-Progression': '1'};
                    const bootstrap = await fetch('/api/me/progression/bootstrap', {method: 'POST', headers});
                    const initial = (await bootstrap.json()).ledger;
                    const lifecycle = {kind: 'lifecycle', eventId: crypto.randomUUID(),
                        bookId: 'book1', contentVersion: 1,
                        baseProgressionRevision: initial.progressionRevision,
                        lifecycleId: 'character_created'};
                    const created = await fetch('/api/me/progression/lifecycle', {
                        method: 'POST', headers, body: JSON.stringify(lifecycle)});
                    const afterCreated = (await created.json()).ledger;
                    const choice = {kind: 'choice', eventId: crypto.randomUUID(),
                        bookId: 'book1', contentVersion: 1,
                        baseProgressionRevision: afterCreated.progressionRevision,
                        fromSceneId: 'b1_c1_s1', choiceId: 'c1_call_out'};
                    const chosen = await fetch('/api/me/progression/choices', {
                        method: 'POST', headers, body: JSON.stringify(choice)});
                    return {withoutCsrf: withoutCsrf.status, bootstrap: bootstrap.status,
                        created: created.status, chosen: chosen.status,
                        afterCreated, chosenBody: await chosen.json()};
                }""")
                assert result["withoutCsrf"] == 403
                assert result["bootstrap"] == result["created"] == result["chosen"] == 200, result
                result["ledger"] = result["chosenBody"]["ledger"]
                assert result["ledger"]["coins"] == {"confirmed": 50}
                assert set(result["ledger"]["achievements"]) == {
                    "THE_STORY_BEGINS", "FIRST_CHOICE",
                }
                assert result["ledger"]["progressionRevision"] == 2
                assert result["ledger"]["checkpoint"]["currentSceneId"] == "b1_c1_s2c"
            finally:
                await browser.close()
    finally:
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=10)

    stored = await ledgers.find_one({"ownerId": account_id})
    assert stored["coins"] == {"confirmed": 50}
    assert stored["appliedEventIds"].keys() == {"1", "2"}
