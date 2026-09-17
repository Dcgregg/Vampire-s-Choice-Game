"""Inert regression for local attribution continuity; no database or live routes."""
from copy import deepcopy

import pytest

from progression.choice_checkpoint_guard import CheckpointConflict
from progression.validated_choice_replay import replay_nonterminal_choices
from test_choice_checkpoint_guard import event, ledger, registry

PRIOR_ID = '550e8400-e29b-41d4-a716-446655440002'


@pytest.mark.parametrize('retained', [{}, {'2': PRIOR_ID}, {'0': PRIOR_ID}])
def test_replay_rejects_missing_latest_revision_marker(retained):
    source = ledger()
    source['appliedEventIds'] = retained
    before = deepcopy(source)
    with pytest.raises(CheckpointConflict, match='latest revision'):
        replay_nonterminal_choices(registry(), source, [event()])
    assert source == before


def test_replay_accepts_current_revision_marker_without_rewriting_it():
    source = ledger()
    source['appliedEventIds'] = {'3': PRIOR_ID}
    proposed = replay_nonterminal_choices(registry(), source, [event()])
    assert proposed['appliedEventIds'] == {'3': PRIOR_ID, '4': event().eventId}
    assert source['appliedEventIds'] == {'3': PRIOR_ID}
