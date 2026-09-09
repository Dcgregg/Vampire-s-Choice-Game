"""
Backend tests for the cloud save API. Stdlib-only (urllib) so they run without
extra deps: `python backend/tests/test_saves.py` or via pytest.
Assumes the backend is running on http://localhost:8001.
"""
import json
import os
import uuid
import urllib.request
import urllib.error

BASE = os.environ.get("BACKEND_URL", "http://localhost:8001")


def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def valid_state(**over):
    st = {
        "player": {"name": "Elena", "genderIdentity": "Woman", "sexualOrientation": "Bisexual", "createdAt": 1},
        "relationships": {},
        "flags": {"completedBook1": True},
        "progress": {
            "currentBookId": "book1", "currentChapter": 3, "currentSceneId": "b1_c3_s3",
            "completedChapters": [1, 2], "completedBooks": ["book1"],
            "sceneHistory": ["b1_c1_s1", "b1_c3_s3"],
        },
        "bloodCoins": 570, "dailyStreak": 4, "lastLoginDate": "2026-01-01",
        "achievements": {"FIRST_CHOICE": {"id": "FIRST_CHOICE", "unlockedAt": 1}},
        "settings": {"fontSize": "normal", "ambientAudio": False, "reducedMotion": False, "highContrast": False},
        "version": 3,
    }
    st.update(over)
    return st


def payload(state, base_rev=0, schema=3, cvs=None):
    return {"saveSchemaVersion": schema, "contentVersions": cvs or {"book1": 1},
            "playerState": state, "baseRevision": base_rev}


def new_id():
    return "vc_" + uuid.uuid4().hex


def test_health():
    s, b = _req("GET", "/api/health")
    assert s == 200 and b["status"] == "ok"


def test_create_read_update():
    pid = new_id()
    s, b = _req("PUT", f"/api/saves/{pid}", payload(valid_state()))
    assert s == 200 and b["revision"] == 1, (s, b)
    assert "_id" not in b  # internal id never leaked

    s, b = _req("GET", f"/api/saves/{pid}")
    assert s == 200 and b["revision"] == 1
    assert b["playerState"]["progress"]["completedBooks"] == ["book1"]
    assert b["contentVersions"] == {"book1": 1}

    s2 = valid_state(bloodCoins=999)
    s, b = _req("PUT", f"/api/saves/{pid}", payload(s2, base_rev=1))
    assert s == 200 and b["revision"] == 2 and b["playerState"]["bloodCoins"] == 999


def test_missing_returns_404():
    s, _ = _req("GET", f"/api/saves/{new_id()}")
    assert s == 404


def test_stale_revision_conflict():
    pid = new_id()
    _req("PUT", f"/api/saves/{pid}", payload(valid_state()))              # rev1
    _req("PUT", f"/api/saves/{pid}", payload(valid_state(bloodCoins=1), base_rev=1))  # rev2
    s, b = _req("PUT", f"/api/saves/{pid}", payload(valid_state(bloodCoins=2), base_rev=1))  # stale
    assert s == 409 and b["error"] == "revision_conflict"
    assert b["currentSave"]["revision"] == 2


def test_create_with_nonzero_base_conflicts():
    s, b = _req("PUT", f"/api/saves/{new_id()}", payload(valid_state(), base_rev=5))
    assert s == 409


def test_malformed_rejected():
    bad = valid_state()
    del bad["progress"]  # required
    s, _ = _req("PUT", f"/api/saves/{new_id()}", payload(bad))
    assert s == 422


def test_negative_coins_rejected():
    s, _ = _req("PUT", f"/api/saves/{new_id()}", payload(valid_state(bloodCoins=-5)))
    assert s == 422


def test_unsupported_schema_rejected():
    s, b = _req("PUT", f"/api/saves/{new_id()}", payload(valid_state(), schema=99))
    assert s == 422 and b["detail"]["error"] == "unsupported_save_schema"


def test_invalid_player_id_rejected():
    s, _ = _req("PUT", "/api/saves/bad!!id", payload(valid_state()))
    assert s == 400


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} backend tests passed")
