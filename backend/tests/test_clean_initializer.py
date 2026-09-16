"""Isolated initializer tests; no production DB or API."""
import asyncio
from copy import deepcopy

import pytest
from pymongo.errors import DuplicateKeyError

from progression.clean_initializer import clean_seed, initialize_clean_account_ledger
from progression.clean_ledger import InvalidCleanLedger


def registry():
    return {"characters": {"friend": 0}, "books": {"book1": {"version": 1,
            "scenes": {"start": {"choices": {}}}}}}


class UniqueFakeCollection:
    def __init__(self):
        self.docs = {}
        self.lock = asyncio.Lock()
        self.inserts = 0

    async def find_one(self, query):
        await asyncio.sleep(0)
        doc = self.docs.get((query["ownerType"], query["ownerId"]))
        return deepcopy(doc) if doc is not None else None

    async def insert_one(self, doc):
        async with self.lock:
            key = (doc["ownerType"], doc["ownerId"])
            if key in self.docs:
                raise DuplicateKeyError("unique account owner")
            self.docs[key] = deepcopy(doc)
            self.inserts += 1


def kwargs():
    return {"owner_id": "authenticated-account", "book_id": "book1",
            "content_version": 1, "scene_id": "start"}


def test_seed_is_unawarded_and_not_mutated():
    source = registry()
    before = deepcopy(source)
    seed = clean_seed(source, **kwargs())
    assert source == before
    assert seed["ownerType"] == "account" and seed["progressionRevision"] == 0
    assert seed["coins"] == {"confirmed": 0} and seed["achievements"] == {}
    assert seed["openingGranted"] is False and seed["lifecycleApplied"] == []
    assert seed["checkpoint"] == {"bookId": "book1", "contentVersion": 1,
                                   "currentSceneId": "start", "terminal": False}


@pytest.mark.parametrize("changes", [
    {"owner_id": ""}, {"owner_id": "   "}, {"book_id": "unknown"},
    {"content_version": 2}, {"content_version": True},
    {"scene_id": "missing"},
])
def test_invalid_seed_rejected_before_io(changes):
    args = kwargs()
    args.update(changes)
    with pytest.raises(InvalidCleanLedger):
        clean_seed(registry(), **args)


@pytest.mark.asyncio
async def test_concurrent_initializers_insert_exactly_once():
    collection = UniqueFakeCollection()
    results = await asyncio.gather(*(initialize_clean_account_ledger(
        collection, registry(), **kwargs()) for _ in range(24)))
    assert collection.inserts == 1
    assert len({result["_id"] for result in results}) == 1
    assert all(result["coins"]["confirmed"] == 0 for result in results)
    results[0]["coins"]["confirmed"] = 999
    assert collection.docs[("account", "authenticated-account")]["coins"]["confirmed"] == 0


@pytest.mark.asyncio
async def test_existing_progressed_ledger_is_not_reset_or_reawarded():
    collection = UniqueFakeCollection()
    first = await initialize_clean_account_ledger(collection, registry(), **kwargs())
    collection.docs[("account", "authenticated-account")]["progressionRevision"] = 4
    collection.docs[("account", "authenticated-account")]["coins"]["confirmed"] = 19
    again = await initialize_clean_account_ledger(collection, registry(), **kwargs())
    assert again["_id"] == first["_id"] and again["progressionRevision"] == 4
    assert again["coins"]["confirmed"] == 19 and collection.inserts == 1


@pytest.mark.asyncio
async def test_existing_ledger_is_found_when_original_opening_content_is_retired():
    collection = UniqueFakeCollection()
    first = await initialize_clean_account_ledger(collection, registry(), **kwargs())
    collection.docs[("account", "authenticated-account")]["progressionRevision"] = 3
    # No new ledger can be seeded from this unavailable version, but an
    # existing account's ledger must remain discoverable without rewriting it.
    again = await initialize_clean_account_ledger(collection, {"books": {}}, **kwargs())
    assert again["_id"] == first["_id"]
    assert again["progressionRevision"] == 3
    assert again["checkpoint"] == first["checkpoint"]
    assert collection.inserts == 1
    again["coins"]["confirmed"] = 999
    assert collection.docs[("account", "authenticated-account")]["coins"]["confirmed"] == 0


@pytest.mark.asyncio
async def test_invalid_owner_is_rejected_before_lookup():
    collection = UniqueFakeCollection()
    with pytest.raises(InvalidCleanLedger, match="authenticated account owner"):
        await initialize_clean_account_ledger(collection, registry(),
                                              **{**kwargs(), "owner_id": "   "})
    assert collection.inserts == 0


@pytest.mark.asyncio
async def test_invalid_content_never_inserts():
    collection = UniqueFakeCollection()
    with pytest.raises(InvalidCleanLedger):
        await initialize_clean_account_ledger(collection, registry(),
                                              **{**kwargs(), "scene_id": "not-a-scene"})
    assert collection.inserts == 0
