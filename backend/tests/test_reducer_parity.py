"""Phase 6A — TS engine <-> Python reducer parity + reducer unit tests.

The parity test replays the golden fixtures (generated FROM the real TS Story
Engine by `yarn content:export`) through the Python reducer and asserts identical
coins + achievements at EVERY step. Any silent divergence between the client
engine and the server reducer fails here.

Run: python backend/tests/test_reducer_parity.py   (or via pytest)
"""
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from progression.reducer import (  # noqa: E402
    apply_choice,
    apply_lifecycle,
    new_state,
)
from progression.trusted_content import (  # noqa: E402
    InvalidChoice,
    UnknownContentVersion,
    load_fixtures,
    load_registry,
)


def test_parity_engine_vs_reducer_every_step():
    registry = load_registry()
    fixtures = load_fixtures()
    assert fixtures, "no parity fixtures generated"
    for fx in fixtures:
        state = new_state(registry)
        steps = fx["steps"]
        first = steps[0]
        assert first["event"] == "character_created", "fixture must start with lifecycle"
        apply_lifecycle(registry, state, "character_created")
        assert state["coins"] == first["coins"]
        assert sorted(state["achievements"]) == first["achievements"]
        for step in steps[1:]:
            apply_choice(registry, state, fx["book"], fx["version"], step["fromScene"], step["event"])
            assert state["coins"] == step["coins"], (step["event"], state["coins"], step["coins"])
            assert sorted(state["achievements"]) == step["achievements"], (
                step["event"], sorted(state["achievements"]), step["achievements"],
            )


def test_registry_known_achievements_cover_awarded():
    """Every achievement the reducer can award must be a known, trusted id
    (so legacy import in 6D can be restricted to known ids)."""
    registry = load_registry()
    known = set(registry["knownAchievements"])
    # derived + lifecycle
    for d in registry["rules"]["derivedAchievements"]:
        assert d["id"] in known
    for rule in registry["rules"]["lifecycleEvents"].values():
        assert rule["achievementId"] in known
    # explicit choice achievements
    for book in registry["books"].values():
        for scene in book["scenes"].values():
            for choice in scene["choices"].values():
                aid = (choice.get("effects") or {}).get("achievementId")
                if aid:
                    assert aid in known, aid


# ---- Negative / rule unit tests (small synthetic registries) ----

def _mini_registry():
    return {
        "contentSchemaVersion": 1,
        "rules": {
            "affinityMin": 0, "affinityMax": 100, "coinsMin": 0,
            "derivedAchievements": [{"id": "DL", "type": "affinityThreshold", "threshold": 70, "scope": "any"}],
            "lifecycleEvents": {"character_created": {"achievementId": "START"}},
        },
        "knownAchievements": ["START", "DL", "A1"],
        "characters": {"x": 65},
        "books": {"bookX": {"version": 1, "startingSceneId": "s1", "scenes": {
            "s1": {"chapterNumber": 1, "choices": {
                "give": {"nextSceneId": "s2", "endsBook": False, "effects": {"coinsChange": 40, "achievementId": "A1"}, "condition": None},
                "take": {"nextSceneId": "s3", "endsBook": False, "effects": {"coinsChange": -100}, "condition": None},
                "bond": {"nextSceneId": "s4", "endsBook": False, "effects": {"relationshipChanges": {"x": 10}}, "condition": None},
            }},
        }}},
    }


def test_invalid_choice_rejected():
    reg = _mini_registry(); st = new_state(reg)
    try:
        apply_choice(reg, st, "bookX", 1, "s1", "nope")
        assert False, "expected InvalidChoice"
    except InvalidChoice:
        pass


def test_unreachable_scene_rejected():
    reg = _mini_registry(); st = new_state(reg)
    try:
        apply_choice(reg, st, "bookX", 1, "sZ", "give")
        assert False, "expected InvalidChoice"
    except InvalidChoice:
        pass


def test_unknown_content_version_rejected():
    reg = _mini_registry(); st = new_state(reg)
    try:
        apply_choice(reg, st, "bookX", 2, "s1", "give")
        assert False, "expected UnknownContentVersion"
    except UnknownContentVersion:
        pass


def test_coins_clamped_at_zero():
    reg = _mini_registry(); st = new_state(reg)
    apply_choice(reg, st, "bookX", 1, "s1", "take")  # -100 from 0
    assert st["coins"] == 0


def test_derived_threshold_and_idempotent_unlock():
    reg = _mini_registry(); st = new_state(reg)
    # x starts at 65; +10 -> 75 crosses 70 -> DL unlocked once
    r1 = apply_choice(reg, st, "bookX", 1, "s1", "bond")
    assert "DL" in r1["awarded"] and st["achievements"].count("DL") == 1
    # applying again does not double-unlock
    r2 = apply_choice(reg, st, "bookX", 1, "s1", "bond")
    assert "DL" not in r2["awarded"] and st["achievements"].count("DL") == 1


def test_explicit_achievement_and_coins():
    reg = _mini_registry(); st = new_state(reg)
    r = apply_choice(reg, st, "bookX", 1, "s1", "give")
    assert st["coins"] == 40 and "A1" in r["awarded"] and r["nextSceneId"] == "s2"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t(); print("PASS", t.__name__)
    print(f"\n{len(tests)}/{len(tests)} reducer/parity tests passed")
