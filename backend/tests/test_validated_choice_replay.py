"""Pure tests only: no HTTP, durable event store, login or real player data."""
from copy import deepcopy

import pytest

from progression.choice_checkpoint_guard import CheckpointConflict
from progression.strict_event_input import StrictChoiceEvent
from progression.trusted_content import InvalidChoice
from progression.validated_choice_replay import replay_nonterminal_choices
from test_choice_checkpoint_guard import event, ledger, registry

SECOND_ID = '550e8400-e29b-41d4-a716-446655440001'
PRIOR_ID = '550e8400-e29b-41d4-a716-446655440002'


def trusted_ledger():
    source = ledger()
    source['appliedEventIds'] = {'3': PRIOR_ID}
    return source


def test_replays_only_reachable_choices_from_trusted_checkpoint():
    source = trusted_ledger()
    original = deepcopy(source)
    choices = [event(), event(eventId=SECOND_ID, baseProgressionRevision=4,
                              fromSceneId='next', choiceId='noncurrent')]
    result = replay_nonterminal_choices(registry(), source, choices)
    assert source == original
    assert result['progressionRevision'] == 5
    assert result['checkpoint']['currentSceneId'] == 'end'
    assert result['coins']['confirmed'] == 530
    assert result['derived']['coins'] == 530
    assert result['appliedEventIds'] == {'3': PRIOR_ID}


@pytest.mark.parametrize('choices', [
    [event(fromSceneId='next', choiceId='noncurrent')],
    [event(choiceId='unknown')],
    [event(), event(eventId=SECOND_ID, baseProgressionRevision=3,
                    fromSceneId='next', choiceId='noncurrent')],
    [event(), event(eventId=SECOND_ID, baseProgressionRevision=4,
                    fromSceneId='start', choiceId='ordinary')],
    [event(), event(baseProgressionRevision=4, fromSceneId='next',
                    choiceId='noncurrent')],
    [event(contentVersion=2)],
    [event(choiceId='terminal')],
    [event(choiceId='award')],
    [event(eventId=PRIOR_ID)],
])
def test_fails_closed_on_forged_or_unsupported_history(choices):
    source = trusted_ledger()
    original = deepcopy(source)
    with pytest.raises((CheckpointConflict, InvalidChoice)):
        replay_nonterminal_choices(registry(), source, choices)
    assert source == original


@pytest.mark.parametrize('retained', [
    None, [], {'3': ''}, {'3': 3}, {'2': PRIOR_ID, '3': PRIOR_ID},
])
def test_rejects_missing_or_corrupt_trusted_attribution(retained):
    source = trusted_ledger()
    if retained is None:
        del source['appliedEventIds']
    else:
        source['appliedEventIds'] = retained
    original = deepcopy(source)
    with pytest.raises(CheckpointConflict):
        replay_nonterminal_choices(registry(), source, [event()])
    assert source == original


def test_requires_strict_bounded_event_sequence():
    source = trusted_ledger()
    for choices in ([], [event()] * 101, 'not-events', [{'kind': 'choice'}]):
        with pytest.raises(CheckpointConflict):
            replay_nonterminal_choices(registry(), source, choices)
    assert source == trusted_ledger()


def test_never_trusts_a_client_supplied_snapshot_as_an_event():
    forged = {'progress': {'currentSceneId': 'end'}, 'bloodCoins': 99999}
    with pytest.raises(CheckpointConflict):
        replay_nonterminal_choices(registry(), trusted_ledger(), [forged])
