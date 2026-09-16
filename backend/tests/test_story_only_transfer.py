"""Pure tests for the inert story-only account transfer boundary."""
from copy import deepcopy

import pytest

from progression.story_only_transfer import InvalidStoryTransfer, story_only_player_state


def sample():
    return {
        "player": {"name": "Mara", "identity": "custom"},
        "relationships": {"friend": 7}, "flags": {"saved_friend": True},
        "progress": {"currentBookId": "book1", "currentChapter": 3,
                     "currentSceneId": "forest", "completedChapters": [1, 2],
                     "completedBooks": [], "sceneHistory": ["start", "forest"]},
        "settings": {"textSize": "large"}, "version": 3,
        "bloodCoins": 999999, "achievements": {"FIRST_CHOICE": True},
        "dailyStreak": 999, "lastLoginDate": "2026-09-16",
        "premiumEntitlements": {"all": True}, "coinBalance": 100000,
    }


def test_story_is_preserved_without_promoting_rewards_or_unknown_fields():
    source = sample()
    before = deepcopy(source)
    result = story_only_player_state(source)
    for field in ("player", "relationships", "flags", "progress", "settings", "version"):
        assert result[field] == source[field]
    assert result["bloodCoins"] == 0
    assert result["achievements"] == {}
    assert result["dailyStreak"] == 0
    assert result["lastLoginDate"] == ""
    assert "premiumEntitlements" not in result and "coinBalance" not in result
    assert source == before
    result["progress"]["sceneHistory"].append("tamper")
    assert source["progress"]["sceneHistory"] == ["start", "forest"]


@pytest.mark.parametrize("bad", [None, [], "save", {}, {"progress": []},
    {"progress": {}, "relationships": {}, "flags": {}, "settings": {}, "version": True},
    {"progress": {}, "relationships": [], "flags": {}, "settings": {}, "version": 3}])
def test_missing_or_invalid_story_structure_is_rejected(bad):
    with pytest.raises(InvalidStoryTransfer):
        story_only_player_state(bad)
