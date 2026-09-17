"""No real player credentials, saves or production services are involved."""
import pytest

from progression.anonymous_claim_proof import (
    InvalidClaimProof, credential_digest, issue_claim_credential, verify_claim_credential,
)


def test_new_credential_is_distinct_and_only_its_digest_is_stored():
    first, digest = issue_claim_credential()
    second, other_digest = issue_claim_credential()
    assert len(first) == 43 and first != second
    assert len(digest) == 64 and digest != other_digest
    assert first not in digest
    assert verify_claim_credential({'claimCredentialDigest': digest}, first)
    assert not verify_claim_credential({'claimCredentialDigest': digest}, second)


def test_legacy_save_and_bad_digest_fail_closed():
    credential, digest = issue_claim_credential()
    for save in ({}, {'claimCredentialDigest': None}, {'claimCredentialDigest': credential},
                 {'claimCredentialDigest': digest.upper()}, {'claimCredentialDigest': 'x' * 64}):
        assert not verify_claim_credential(save, credential)


def test_malformed_credentials_are_not_accepted_or_logged():
    credential, digest = issue_claim_credential()
    for bad in ('', 'vc_abcdefgh', credential + '=', credential[:-1], None, 123, credential[:4] + '!' + credential[5:]):
        assert not verify_claim_credential({'claimCredentialDigest': digest}, bad)
        with pytest.raises(InvalidClaimProof, match='invalid claim proof'):
            credential_digest(bad)
