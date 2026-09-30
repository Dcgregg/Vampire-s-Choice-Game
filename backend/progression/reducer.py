"""Phase 6A — authoritative progression reducer (foundation).

A pure function that mirrors the client Story Engine's ECONOMY + ACHIEVEMENT
semantics (src/engine/effects.ts) so the server can independently derive rewards
from trusted content instead of trusting the browser.

Scope in 6A: given trusted content + an in-memory projection, apply a lifecycle
or choice event and return the awards + navigation. It does NOT persist,
touch a ledger/DB, enforce optimistic concurrency, or dedupe eventIds — those
belong to 6B once the design is approved.

Mirrored effect order (must match effects.ts exactly):
  relationships (+ derived achievement, evaluated only within this block)
  -> flags -> coins (clamped at coinsMin) -> explicit achievement.
Streak/notification are intentionally out of economy/achievement scope.
"""
from typing import Any, Dict, List

from .trusted_content import InvalidChoice, book_entry  # re-exported for callers


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def new_state(registry: Dict[str, Any]) -> Dict[str, Any]:
    """Fresh derived projection: no coins, initial affinities, no unlocks.

    The (6B) server-seeded opening grant is deliberately NOT applied here so the
    reducer's event-derived output can be validated in isolation.
    """
    state = {
        "coins": 0,
        "affinity": dict(registry.get("characters", {})),
        "flags": {},
        "achievements": [],  # ordered list of unlocked ids
    }
    # New authored books can opt into humanity without changing the durable
    # shape of existing trusted books and ledgers.
    humanity_initial = registry.get("rules", {}).get("humanityInitial")
    if type(humanity_initial) is int:
        state["humanity"] = humanity_initial
    return state


def _condition_value(state: Dict[str, Any], target: str) -> Any:
    if target == "bloodCoins":
        return state.get("coins")
    if target == "humanity":
        return state.get("humanity")
    if target.startswith("affinity."):
        return state.get("affinity", {}).get(target.removeprefix("affinity."))
    return None


def _condition_matches(state: Dict[str, Any], condition: Any) -> bool:
    """Evaluate the compact, trusted numeric condition contract safely."""
    if condition is None:
        return True
    conditions = condition if isinstance(condition, list) else [condition]
    for item in conditions:
        if not isinstance(item, dict):
            return False
        target, operator, expected = item.get("target"), item.get("operator"), item.get("value")
        current = _condition_value(state, target) if isinstance(target, str) else None
        if type(current) is not int or type(expected) is not int:
            return False
        if operator == "gte" and current >= expected:
            continue
        if operator == "lte" and current <= expected:
            continue
        if operator == "eq" and current == expected:
            continue
        return False
    return True


def _required_flags_match(state: Dict[str, Any], required_flags: Any) -> bool:
    """Safely evaluate the compact trusted story-flag contract."""
    if required_flags is None:
        return True
    if not isinstance(required_flags, dict):
        return False
    flags = state.get("flags", {})
    return isinstance(flags, dict) and all(type(key) is str and flags.get(key) == expected for key, expected in required_flags.items())


def _unlock(state: Dict[str, Any], achievement_id: str) -> List[str]:
    """Idempotent unlock. Returns [id] if newly unlocked, else []."""
    if achievement_id and achievement_id not in state["achievements"]:
        state["achievements"].append(achievement_id)
        return [achievement_id]
    return []


def apply_lifecycle(registry: Dict[str, Any], state: Dict[str, Any], lifecycle_id: str) -> Dict[str, Any]:
    rule = registry["rules"]["lifecycleEvents"].get(lifecycle_id)
    if rule is None:
        raise InvalidChoice(f"unknown lifecycle event '{lifecycle_id}'")
    awarded = _unlock(state, rule.get("achievementId")) if rule.get("achievementId") else []
    return {"awarded": awarded}


def apply_choice(
    registry: Dict[str, Any],
    state: Dict[str, Any],
    book_id: str,
    version: int,
    from_scene_id: str,
    choice_id: str,
) -> Dict[str, Any]:
    """Apply one choice event's trusted effects to the projection.

    Reachability in 6A is limited to "the choice exists on the named scene".
    The full checkpoint state-machine guard (fromScene == authoritative
    checkpoint) is a 6B ledger concern.
    """
    book = book_entry(registry, book_id, version)  # raises UnknownContentVersion
    scene = book["scenes"].get(from_scene_id)
    if scene is None:
        raise InvalidChoice(f"unreachable scene '{from_scene_id}'")
    choice = scene["choices"].get(choice_id)
    if choice is None:
        raise InvalidChoice(f"unknown choice '{choice_id}' on scene '{from_scene_id}'")
    if not _condition_matches(state, choice.get("condition")) or not _required_flags_match(state, choice.get("requiredFlags")):
        raise InvalidChoice(f"conditions not met for choice '{choice_id}' on scene '{from_scene_id}'")

    effects = choice.get("effects") or {}
    rules = registry["rules"]
    awarded: List[str] = []

    # --- Relationships (+ derived achievement, inside this block like effects.ts) ---
    rc = effects.get("relationshipChanges")
    if rc:
        for cid, delta in rc.items():
            if cid not in state["affinity"]:
                continue  # fail-safe: ignore unknown characters (matches engine)
            state["affinity"][cid] = clamp(
                state["affinity"][cid] + delta, rules["affinityMin"], rules["affinityMax"]
            )
        for d in rules.get("derivedAchievements", []):
            if d["type"] == "affinityThreshold" and any(
                v >= d["threshold"] for v in state["affinity"].values()
            ):
                awarded += _unlock(state, d["id"])

    # --- Flags ---
    if effects.get("setFlags"):
        state["flags"].update(effects["setFlags"])

    # --- Coins (clamped at coinsMin) ---
    coins_change = effects.get("coinsChange")
    if coins_change:
        state["coins"] = max(rules["coinsMin"], state["coins"] + coins_change)

    # Optional only: books that declare humanityInitial own the new trusted
    # dimension. Existing registry versions keep their historical state shape.
    humanity_change = effects.get("humanityChange")
    if humanity_change is not None:
        if type(humanity_change) is not int or type(state.get("humanity")) is not int:
            raise InvalidChoice("humanity effect is not supported by this content version")
        low, high = rules.get("humanityMin", 0), rules.get("humanityMax", 100)
        if type(low) is not int or type(high) is not int or low > high:
            raise InvalidChoice("invalid humanity bounds")
        state["humanity"] = clamp(state["humanity"] + humanity_change, low, high)

    # --- Explicit achievement ---
    if effects.get("achievementId"):
        awarded += _unlock(state, effects["achievementId"])

    return {
        "awarded": awarded,
        "nextSceneId": choice["nextSceneId"],
        "endsBook": bool(choice.get("endsBook", False)),
    }
