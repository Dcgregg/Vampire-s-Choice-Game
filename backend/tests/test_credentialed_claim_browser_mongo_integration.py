"""Real Chromium -> test-only FastAPI -> disposable MongoDB; never mounts live routes.

Run only with TEST_MONGO_URI pointing to a disposable transaction-capable replica set.
The test-only authenticated identity is not a production login implementation.
"""
import asyncio
import json
import socket

import pytest
from fastapi import FastAPI
from playwright.async_api import async_playwright
import uvicorn

from progression.anonymous_credential_routes import make_anonymous_credential_router
from progression.credentialed_story_claim_routes import make_credentialed_story_claim_router
from test_story_claim_transaction_integration import collections  # noqa: F401
from test_story_claim_mongo_integration import anonymous_doc


@pytest.mark.asyncio
async def test_chromium_issuance_to_claim_uses_disposable_mongo(collections):
    anonymous_saves, account_saves = collections
    seed = anonymous_doc()
    initial = {key: seed[key] for key in ('saveSchemaVersion', 'contentVersions', 'playerState')}
    initial['playerState']['bloodCoins'] = 0
    initial['playerState']['achievements'] = {}
    initial['playerState']['dailyStreak'] = 0
    initial['playerState']['lastLoginDate'] = ''
    identity = {'user_id': 'browser-test-account'}

    async def test_identity():
        return identity.copy()

    app = FastAPI()
    app.include_router(make_anonymous_credential_router(
        anonymous_saves, initial_save=lambda: initial, now=lambda: 'issued'))
    app.include_router(make_credentialed_story_claim_router(
        anonymous_saves, account_saves, current_user=test_identity, now=lambda: 'claimed'))

    @app.get('/test-only-browser-page')
    async def page():
        from fastapi.responses import HTMLResponse
        return HTMLResponse('<!doctype html><html><body>Isolated credential flow test</body></html>')

    # Bind localhost only; no live server, account, or production credentials.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
                                          log_level='error', access_log=False))
    server_task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            if server_task.done():
                await server_task
            await asyncio.sleep(0.05)
        assert server.started, 'test-only FastAPI server did not start'
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(f'http://127.0.0.1:{port}/test-only-browser-page')
                result = await page.evaluate('''async () => {
                    const issued = await fetch('/api/anonymous/credentialed-save', {method: 'POST'});
                    const creation = await issued.json();
                    const {save, claimCredential} = creation;
                    const payload = JSON.stringify({playerId: save.playerId,
                        expectedAnonymousRevision: save.revision});
                    const wrong = await fetch('/api/me/claim-story-with-credential', {
                        method: 'POST', headers: {'Content-Type': 'application/json',
                            'X-Anonymous-Claim-Credential': 'A'.repeat(43)}, body: payload});
                    const claimed = await fetch('/api/me/claim-story-with-credential', {
                        method: 'POST', headers: {'Content-Type': 'application/json',
                            'X-Anonymous-Claim-Credential': claimCredential}, body: payload});
                    const claimedText = await claimed.text();
                    const repeated = await fetch('/api/me/claim-story-with-credential', {
                        method: 'POST', headers: {'Content-Type': 'application/json',
                            'X-Anonymous-Claim-Credential': claimCredential}, body: payload});
                    return {issuedStatus: issued.status, issuedCache: issued.headers.get('cache-control'),
                        wrongStatus: wrong.status, claimStatus: claimed.status,
                        claimCache: claimed.headers.get('cache-control'), save,
                        credential: claimCredential, claimedText,
                        repeatedStatus: repeated.status, repeatedText: await repeated.text()};
                }''')
                assert result['issuedStatus'] == 201
                assert result['issuedCache'] == 'no-store'
                assert result['wrongStatus'] == 403
                assert result['claimStatus'] == 200
                assert result['claimCache'] == 'no-store'
                assert result['save']['playerId'].startswith('vc_')
                assert result['credential'] not in result['claimedText']
                claimed = json.loads(result['claimedText'])
                assert claimed['playerState']['progress'] == result['save']['playerState']['progress']
                assert claimed['playerState']['bloodCoins'] == 0
                assert claimed['playerState']['achievements'] == {}
                assert 'claimCredentialDigest' not in result['claimedText']
                assert result['repeatedStatus'] == 200
                assert json.loads(result['repeatedText']) == claimed
                assert await account_saves.count_documents({'userId': 'browser-test-account'}) == 1
                stored = await anonymous_saves.find_one({'playerId': result['save']['playerId']})
                assert stored['claimedBy'] == 'browser-test-account'
                assert stored['claimCredentialDigest'] != result['credential']

                # Switch only the injected test identity; the browser still has the real
                # credential. The claimed story must not transfer to a second account.
                identity['user_id'] = 'browser-second-account'
                denied = await page.evaluate('''async ({playerId, revision, credential}) => {
                    const response = await fetch('/api/me/claim-story-with-credential', {
                        method: 'POST', headers: {'Content-Type': 'application/json',
                            'X-Anonymous-Claim-Credential': credential},
                        body: JSON.stringify({playerId, expectedAnonymousRevision: revision})});
                    return {status: response.status, cache: response.headers.get('cache-control'),
                        text: await response.text()};
                }''', {'playerId': result['save']['playerId'],
                       'revision': result['save']['revision'],
                       'credential': result['credential']})
                assert denied['status'] == 403
                assert denied['cache'] == 'no-store'
                assert result['credential'] not in denied['text']
                assert await account_saves.count_documents({'userId': 'browser-second-account'}) == 0
                assert await account_saves.count_documents({'userId': 'browser-test-account'}) == 1
                assert (await anonymous_saves.find_one(
                    {'playerId': result['save']['playerId']}))['claimedBy'] == 'browser-test-account'
            finally:
                await browser.close()
    finally:
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=10)
