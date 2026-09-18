"""Malformed locators must fail before querying the anonymous collection."""
import pytest

from progression.credentialed_anonymous_read import (
    AnonymousReadDenied, read_credentialed_anonymous_save,
)
from progression.credentialed_anonymous_write import (
    AnonymousWriteDenied, write_credentialed_anonymous_save,
)


class NoDatabaseAccess:
    async def find_one(self, query):
        raise AssertionError('invalid locator reached database')


@pytest.mark.asyncio
@pytest.mark.parametrize('player_id', [
    'vc_', 'vc_short', 'vc_abcdefgh!', 'vc_abcdefgh\n',
    'vc_abcdefgh/other', 'vc_' + 'a' * 65, None, 123,
])
async def test_invalid_locator_denied_before_database_read_or_write(player_id):
    collection = NoDatabaseAccess()
    with pytest.raises(AnonymousReadDenied):
        await read_credentialed_anonymous_save(
            collection, player_id=player_id, claim_credential='not-a-credential',
        )
    with pytest.raises(AnonymousWriteDenied):
        await write_credentialed_anonymous_save(
            collection, player_id=player_id, claim_credential='not-a-credential',
            expected_revision=1, player_state={'progress': {}}, now='now',
        )
