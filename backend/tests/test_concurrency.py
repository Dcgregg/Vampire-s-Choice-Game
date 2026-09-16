"""Race-condition tests for the hardening pass. These fire GENUINELY simultaneous
requests (threads) so they exercise the competing DB operations, not sequential
calls. Stdlib + pymongo only. Backend must be running on :8001.
Run: python backend/tests/test_concurrency.py
"""
import json, os, uuid, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE = os.environ.get("BACKEND_URL", "http://localhost:8001")
db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "vampires_choice")]


def _req(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def make_user():
    uid = f"user_{uuid.uuid4().hex[:12]}"
    tok = "test_session_" + uuid.uuid4().hex
    db.users.insert_one({"user_id": uid, "email": f"{uid}@example.com", "name": "T", "picture": None, "created_at": datetime.now(timezone.utc)})
    db.user_sessions.insert_one({"user_id": uid, "session_token": tok, "expires_at": datetime.now(timezone.utc) + timedelta(days=7), "created_at": datetime.now(timezone.utc)})
    return uid, tok


def valid_state(**o):
    st = {"player": {"name": "Elena", "genderIdentity": "Woman", "sexualOrientation": "Bisexual", "createdAt": 1},
          "relationships": {}, "flags": {}, "progress": {"currentBookId": "book1", "currentChapter": 1, "currentSceneId": "b1_c1_s1", "completedChapters": [], "completedBooks": [], "sceneHistory": ["b1_c1_s1"]},
          "bloodCoins": 250, "dailyStreak": 3, "lastLoginDate": "2026-01-01", "achievements": {}, "settings": {}, "version": 3}
    st.update(o); return st


def payload(state, base=0):
    return {"saveSchemaVersion": 3, "contentVersions": {"book1": 1}, "playerState": state, "baseRevision": base}


def _parallel(fns):
    with ThreadPoolExecutor(max_workers=len(fns)) as ex:
        return [f.result() for f in [ex.submit(fn) for fn in fns]]


def test_concurrent_anon_update_one_wins():
    pid = "vc_" + uuid.uuid4().hex
    s, _ = _req("PUT", f"/api/saves/{pid}", payload(valid_state()))  # rev1
    assert s == 200
    results = _parallel([
        lambda: _req("PUT", f"/api/saves/{pid}", payload(valid_state(bloodCoins=1), base=1)),
        lambda: _req("PUT", f"/api/saves/{pid}", payload(valid_state(bloodCoins=2), base=1)),
    ])
    codes = sorted(r[0] for r in results)
    assert codes == [200, 409], codes
    winner = next(b for s, b in results if s == 200)
    loser = next(b for s, b in results if s == 409)
    assert winner["revision"] == 2
    assert loser["error"] == "revision_conflict"
    assert loser["currentSave"]["revision"] == 2  # real current, never fabricated
    # DB truly holds exactly one doc at rev2
    docs = list(db.cloud_saves.find({"playerId": pid}))
    assert len(docs) == 1 and docs[0]["revision"] == 2


def test_concurrent_anon_create_one_wins():
    pid = "vc_" + uuid.uuid4().hex
    results = _parallel([
        lambda: _req("PUT", f"/api/saves/{pid}", payload(valid_state(bloodCoins=10))),
        lambda: _req("PUT", f"/api/saves/{pid}", payload(valid_state(bloodCoins=20))),
    ])
    codes = sorted(r[0] for r in results)
    assert codes == [200, 409], (codes, results)
    assert len(list(db.cloud_saves.find({"playerId": pid}))) == 1  # no duplicate doc


def test_concurrent_account_update_one_wins():
    _, tok = make_user()
    _req("PUT", "/api/me/save", payload(valid_state()), token=tok)  # rev1
    results = _parallel([
        lambda: _req("PUT", "/api/me/save", payload(valid_state(bloodCoins=1), base=1), token=tok),
        lambda: _req("PUT", "/api/me/save", payload(valid_state(bloodCoins=2), base=1), token=tok),
    ])
    codes = sorted(r[0] for r in results)
    assert codes == [200, 409], (codes, results)
    loser = next(b for s, b in results if s == 409)
    assert loser["currentSave"]["revision"] == 2


def test_concurrent_claim_two_users_no_double_claim():
    pid = "vc_" + uuid.uuid4().hex
    _req("PUT", f"/api/saves/{pid}", payload(valid_state(bloodCoins=777)))
    _, tokA = make_user()
    _, tokB = make_user()
    results = _parallel([
        lambda: _req("POST", "/api/me/claim", {"playerId": pid}, token=tokA),
        lambda: _req("POST", "/api/me/claim", {"playerId": pid}, token=tokB),
    ])
    codes = sorted(r[0] for r in results)
    assert codes == [200, 403], (codes, results)
    # exactly one owner recorded, and only the winner adopted the progress
    anon = db.cloud_saves.find_one({"playerId": pid})
    owners = {d["userId"] for d in db.account_saves.find({"historicalAnonymousId": pid})}
    assert owners == {anon["claimedBy"]}, owners


def test_concurrent_use_anonymous_resolution_one_wins():
    # Account save + anon save both exist -> two simultaneous use_anonymous resolutions.
    _, tok = make_user()
    _req("PUT", "/api/me/save", payload(valid_state(bloodCoins=5)), token=tok)  # account rev1
    pid = "vc_" + uuid.uuid4().hex
    _req("PUT", f"/api/saves/{pid}", payload(valid_state(bloodCoins=888)))       # anon
    results = _parallel([
        lambda: _req("POST", "/api/me/claim", {"playerId": pid, "strategy": "use_anonymous"}, token=tok),
        lambda: _req("POST", "/api/me/claim", {"playerId": pid, "strategy": "use_anonymous"}, token=tok),
    ])
    codes = sorted(r[0] for r in results)
    # One applies the overwrite (rev2), the other sees the account already moved.
    assert codes == [200, 409], (codes, results)
    uid = db.user_sessions.find_one({"session_token": tok})["user_id"]
    acct = db.account_saves.find_one({"userId": uid})
    assert acct["playerState"]["bloodCoins"] == 888 and acct["revision"] == 2


def test_interrupted_claim_recovers():
    # Simulate a claim that fenced the anon save but crashed before creating the
    # account save. A retry must recover the progress into the account.
    pid = "vc_" + uuid.uuid4().hex
    _req("PUT", f"/api/saves/{pid}", payload(valid_state(bloodCoins=333)))
    uid, tok = make_user()
    db.cloud_saves.update_one({"playerId": pid}, {"$set": {"claimedBy": uid}})  # fenced, no account save
    assert db.account_saves.find_one({"userId": uid}) is None
    s, b = _req("POST", "/api/me/claim", {"playerId": pid}, token=tok)
    assert s == 200 and b["playerState"]["bloodCoins"] == 333, (s, b)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t(); print("PASS", t.__name__)
    print(f"\n{len(tests)}/{len(tests)} concurrency tests passed")
