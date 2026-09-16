"""Auth + account-save + claim tests. Seeds sessions directly in Mongo (per the
Emergent auth testing playbook), then exercises the API. Stdlib + pymongo only.
Run: python backend/tests/test_auth.py  (backend must be running on :8001)."""
import json, os, uuid, urllib.request, urllib.error
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


def test_me_requires_valid_token():
    assert _req("GET", "/api/auth/me")[0] == 401
    assert _req("GET", "/api/auth/me", token="bogus")[0] == 401
    _, tok = make_user()
    s, b = _req("GET", "/api/auth/me", token=tok)
    assert s == 200 and "@example.com" in b["email"]


def test_account_save_requires_owner_and_roundtrips():
    _, tok = make_user()
    assert _req("GET", "/api/me/save", token=tok)[0] == 404
    s, b = _req("PUT", "/api/me/save", payload(valid_state()), token=tok)
    assert s == 200 and b["revision"] == 1
    s, b = _req("PUT", "/api/me/save", payload(valid_state(bloodCoins=300), base=1), token=tok)
    assert s == 200 and b["revision"] == 2 and b["playerState"]["bloodCoins"] == 300
    # unauthenticated cannot access
    assert _req("GET", "/api/me/save")[0] == 401


def test_users_are_isolated():
    _, tokA = make_user(); _, tokB = make_user()
    _req("PUT", "/api/me/save", payload(valid_state(bloodCoins=111)), token=tokA)
    # B has no save; B cannot see A's
    assert _req("GET", "/api/me/save", token=tokB)[0] == 404


def test_claim_flow_idempotent_and_no_hijack():
    pid = "vc_" + uuid.uuid4().hex
    # create an anonymous save
    _req("PUT", f"/api/saves/{pid}", payload(valid_state(bloodCoins=570, flags={"completedBook1": True})))
    _, tokA = make_user()
    s, b = _req("POST", "/api/me/claim", {"playerId": pid}, token=tokA)
    assert s == 200 and b["playerState"]["bloodCoins"] == 570
    assert b["playerState"]["flags"]["completedBook1"] is True
    # repeated claim is safe/idempotent
    s2, _ = _req("POST", "/api/me/claim", {"playerId": pid}, token=tokA)
    assert s2 == 200
    # anonymous writes to a claimed save are blocked
    s3, _ = _req("PUT", f"/api/saves/{pid}", payload(valid_state(bloodCoins=1), base=1))
    assert s3 == 409
    # a different user cannot hijack the claimed anon save
    _, tokB = make_user()
    s4, _ = _req("POST", "/api/me/claim", {"playerId": pid}, token=tokB)
    assert s4 == 403


def test_claim_conflict_requires_choice():
    _, tok = make_user()
    _req("PUT", "/api/me/save", payload(valid_state(bloodCoins=10)), token=tok)  # account has save
    pid = "vc_" + uuid.uuid4().hex
    _req("PUT", f"/api/saves/{pid}", payload(valid_state(bloodCoins=999)))       # meaningful anon save
    s, b = _req("POST", "/api/me/claim", {"playerId": pid}, token=tok)
    assert s == 409 and b["error"] == "claim_conflict"
    # resolve by keeping anonymous
    s2, b2 = _req("POST", "/api/me/claim", {"playerId": pid, "strategy": "use_anonymous"}, token=tok)
    assert s2 == 200 and b2["playerState"]["bloodCoins"] == 999


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t(); print("PASS", t.__name__)
    print(f"\n{len(tests)}/{len(tests)} auth tests passed")
