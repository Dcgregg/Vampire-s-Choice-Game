"""Regression guard: foundation-only PR must not activate experimental APIs.

This is a source-level tripwire, not a replacement for integration/security review.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_live_server_does_not_register_experimental_routers():
    source = (ROOT / 'backend/server.py').read_text(encoding='utf-8')
    for marker in (
        'make_story_claim_router',
        'make_credentialed_story_claim_router',
        'make_anonymous_credential_router',
        'write_credentialed_anonymous_save',
        'read_credentialed_anonymous_save',
        '/me/claim-story-only',
        '/me/claim-story-with-credential',
        '/anonymous/credentialed-save',
    ):
        assert marker not in source, f'Phase 6B activation needs explicit cutover review: {marker}'


def test_live_auth_does_not_adopt_experimental_claim_clients():
    source = (ROOT / 'src/auth/AuthContext.tsx').read_text(encoding='utf-8')
    for marker in ('storyOnlyLink', 'credentialedStoryLink',
                   'claimStoryOnly', 'claimStoryWithCredential',
                   'linkFreshCredentialedStory'):
        assert marker not in source, f'Phase 6B auth cutover needs explicit review: {marker}'
