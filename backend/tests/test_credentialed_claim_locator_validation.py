"""Isolated claim-input guard tests; no database, sessions or live saves."""
import pytest

from progression.credentialed_story_claim import claim_story_with_credential
from progression.story_claim import StoryClaimDenied


@pytest.mark.asyncio
@pytest.mark.parametrize('player_id', [
    None, '', 'vc_', 'vc_short', 'vc_' + 'a' * 65,
    'vc_' + 'a' * 8 + '/other', 'vc_' + 'a' * 8 + '\n',
    'vc_' + 'a' * 8 + ' ', 123,
])
async def test_invalid_claim_locator_denied_without_touching_database(player_id):
    # A helper caller must not bypass the HTTP request model's ID constraints.
    with pytest.raises(StoryClaimDenied):
        await claim_story_with_credential(
            None, None, authenticated_user_id='user-one', player_id=player_id,
            expected_anonymous_revision=1, claim_credential='irrelevant', now='now',
        )
