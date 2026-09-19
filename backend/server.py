"""
Vampire's Choice — cloud save backend (Phase 4).

Minimal, production-shaped persistence service for ANONYMOUS cloud saves.
It stores one save document per anonymous player id and uses optimistic
concurrency (a monotonic `revision`) so a stale client cannot silently
overwrite newer cloud progress.

Explicitly NOT in this phase: accounts/auth, payments, server-authoritative
currency/achievements. Blood Coins and achievements are still client-derived
and are NOT tamper-proof yet (documented, not marketed as authoritative).
"""
import os
import re
import json as _json
import base64
import hashlib
import secrets
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
from pydantic import BaseModel, ConfigDict, Field
import uuid

from progression.feature_gated_routes import (
    ensure_trusted_progression_indexes,
    register_trusted_progression_routes,
    trusted_progression_routes_enabled,
)
from progression.trusted_content import load_registry

load_dotenv()

MONGO_URL = os.environ.get("MONGO_URL") or os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("DB_NAME", "vampires_choice_phase6c_staging")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")
GOOGLE_OAUTH_SUCCESS_URL = os.environ.get("GOOGLE_OAUTH_SUCCESS_URL", "/")
SESSION_TTL_DAYS = 7
TRUSTED_PROGRESSION_ACTIVATION = os.environ.get("TRUSTED_PROGRESSION_ROUTES")
TRUSTED_PROGRESSION_ENABLED = trusted_progression_routes_enabled(
    TRUSTED_PROGRESSION_ACTIVATION,
)

# Highest player-SAVE schema version this server understands (see frontend storage.ts).
SUPPORTED_SAVE_SCHEMA_VERSIONS = {1, 2, 3}
MAX_BODY_BYTES = 512 * 1024  # constrain request size
PLAYER_ID_RE = re.compile(r"^vc_[A-Za-z0-9_-]{8,64}$")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
saves = db["cloud_saves"]        # anonymous saves (weaker trust model)
account_saves = db["account_saves"]  # account-owned saves (authenticated)
users = db["users"]
sessions = db["user_sessions"]
progression_ledgers = db["progression_ledgers"]
progression_events = db["progression_events"]

app = FastAPI(title="Vampire's Choice Cloud Save API")


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > MAX_BODY_BYTES:
                return JSONResponse(status_code=413, content={"error": "payload_too_large"})
        except ValueError:
            pass
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS.split(",")] if CORS_ORIGINS != "*" else ["*"],
    allow_credentials=False,
    allow_methods=["GET", "PUT", "POST", "OPTIONS"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")


@app.on_event("startup")
async def _ensure_indexes():
    # Unique keys turn concurrent "create" races into duplicate-key errors we can
    # translate into a clean 409 instead of silently storing two rival documents.
    await saves.create_index("playerId", unique=True)
    await account_saves.create_index("userId", unique=True)
    await sessions.create_index("session_token", unique=True)
    await users.create_index("email", unique=True)
    await ensure_trusted_progression_indexes(
        activation_value=TRUSTED_PROGRESSION_ACTIVATION,
        ledgers=progression_ledgers,
        events=progression_events,
    )


# ---- Validation models (structure-only; nested detail stays flexible) ----
class Progress(BaseModel):
    model_config = ConfigDict(extra="allow")
    currentBookId: str
    currentChapter: int
    currentSceneId: str
    completedChapters: List[int]
    completedBooks: List[str]
    sceneHistory: List[str]


class PlayerStateModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    player: Optional[Dict[str, Any]]
    relationships: Dict[str, Any]
    flags: Dict[str, Any]
    progress: Progress
    bloodCoins: int = Field(ge=0)
    dailyStreak: int = Field(ge=0)
    lastLoginDate: str
    achievements: Dict[str, Any]
    settings: Dict[str, Any]
    version: int


class SavePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    saveSchemaVersion: int
    contentVersions: Dict[str, int] = {}
    playerState: PlayerStateModel
    baseRevision: int = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a stored document for the client; never leak the internal _id."""
    return {
        "playerId": doc["playerId"],
        "saveSchemaVersion": doc["saveSchemaVersion"],
        "contentVersions": doc.get("contentVersions", {}),
        "playerState": doc["playerState"],
        "revision": doc["revision"],
        "createdAt": doc["createdAt"],
        "updatedAt": doc["updatedAt"],
    }


def _validate_player_id(player_id: str) -> None:
    if not PLAYER_ID_RE.match(player_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_player_id"})


@api.get("/health")
async def health():
    try:
        await db.command("ping")
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok", "db": db_ok, "time": _now()}


@api.get("/saves/{player_id}")
async def get_save(player_id: str):
    _validate_player_id(player_id)
    doc = await saves.find_one({"playerId": player_id})
    if not doc:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return _public(doc)


@api.put("/saves/{player_id}")
async def put_save(player_id: str, payload: SavePayload):
    _validate_player_id(player_id)

    if payload.saveSchemaVersion not in SUPPORTED_SAVE_SCHEMA_VERSIONS:
        raise HTTPException(
            status_code=422,
            detail={"error": "unsupported_save_schema", "supported": sorted(SUPPORTED_SAVE_SCHEMA_VERSIONS)},
        )

    existing = await saves.find_one({"playerId": player_id})
    if existing and existing.get("claimedBy"):
        # This anonymous save has been linked to an account; block further anon writes.
        return JSONResponse(status_code=409, content={"error": "claimed", "reason": "use_account_endpoints"})
    state_dict = payload.playerState.model_dump()
    now = _now()

    if existing is None:
        # Creating: client must not claim a base revision that never existed.
        if payload.baseRevision != 0:
            return JSONResponse(
                status_code=409,
                content={"error": "revision_conflict", "reason": "no_server_save", "currentSave": None},
            )
        doc = {
            "playerId": player_id,
            "saveSchemaVersion": payload.saveSchemaVersion,
            "contentVersions": payload.contentVersions,
            "playerState": state_dict,
            "revision": 1,
            "createdAt": now,
            "updatedAt": now,
        }
        try:
            await saves.insert_one(doc)
        except DuplicateKeyError:
            # A concurrent create won the race — surface the real current save.
            return await _anon_conflict(player_id)
        return _public(doc)

    # Optimistic concurrency: only accept if the client is up to date.
    if payload.baseRevision != existing["revision"]:
        return JSONResponse(
            status_code=409,
            content={"error": "revision_conflict", "reason": "stale_revision", "currentSave": _public(existing)},
        )

    new_rev = existing["revision"] + 1
    result = await saves.update_one(
        {"playerId": player_id, "revision": existing["revision"], "claimedBy": {"$exists": False}},
        {"$set": {
            "saveSchemaVersion": payload.saveSchemaVersion,
            "contentVersions": payload.contentVersions,
            "playerState": state_dict,
            "revision": new_rev,
            "updatedAt": now,
        }},
    )
    if result.matched_count == 0:
        # The revision moved (or the save was claimed) between our read and write.
        return await _anon_conflict(player_id)
    updated = {**existing,
               "saveSchemaVersion": payload.saveSchemaVersion,
               "contentVersions": payload.contentVersions,
               "playerState": state_dict,
               "revision": new_rev,
               "updatedAt": now}
    return _public(updated)


async def _anon_conflict(player_id: str) -> JSONResponse:
    """Build the truthful 409 for a lost anonymous write (never a fake revision)."""
    latest = await saves.find_one({"playerId": player_id})
    if latest and latest.get("claimedBy"):
        return JSONResponse(status_code=409, content={"error": "claimed", "reason": "use_account_endpoints"})
    return JSONResponse(status_code=409, content={
        "error": "revision_conflict", "reason": "stale_revision",
        "currentSave": _public(latest) if latest else None,
    })


# ===================== Authentication (direct Google OAuth) =====================
class PublicUser(BaseModel):
    email: str
    name: str
    picture: Optional[str] = None


async def _current_user(request: Request) -> Dict[str, Any]:
    """Resolve the authenticated user from the session_token cookie or Bearer header.
    A client-supplied anonymous player id is NEVER accepted here."""
    token = request.cookies.get("session_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated"})

    sess = await sessions.find_one({"session_token": token}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=401, detail={"error": "invalid_session"})
    exp = sess["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        await sessions.delete_one({"session_token": token})
        raise HTTPException(status_code=401, detail={"error": "session_expired"})

    user = await users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail={"error": "user_not_found"})
    return user


def _require_google_oauth_config() -> None:
    if not all((GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI)):
        raise HTTPException(status_code=503, detail={"error": "google_oauth_not_configured"})


@api.get("/auth/google/start")
async def google_auth_start():
    _require_google_oauth_config()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = urllib.parse.urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    })
    response = RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}", status_code=302)
    response.set_cookie("oauth_state", state, max_age=600, httponly=True, secure=True, samesite="lax", path="/api/auth/google")
    response.set_cookie("oauth_code_verifier", verifier, max_age=600, httponly=True, secure=True, samesite="lax", path="/api/auth/google")
    return response


@api.get("/auth/google/callback")
async def google_auth_callback(request: Request, code: str, state: str):
    _require_google_oauth_config()
    expected_state = request.cookies.get("oauth_state") or ""
    verifier = request.cookies.get("oauth_code_verifier") or ""
    if not expected_state or not verifier or not secrets.compare_digest(state, expected_state):
        raise HTTPException(status_code=400, detail={"error": "invalid_oauth_state"})

    body = urllib.parse.urlencode({
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }).encode()
    token_request = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(token_request, timeout=10) as token_response:
            token_data = _json.loads(token_response.read().decode())
        userinfo_request = urllib.request.Request(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        with urllib.request.urlopen(userinfo_request, timeout=10) as userinfo_response:
            data = _json.loads(userinfo_response.read().decode())
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "google_oauth_failed"})

    email = data.get("email")
    if not email or data.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail={"error": "unverified_google_email"})

    existing = await users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await users.update_one({"user_id": user_id}, {"$set": {"name": data.get("name"), "picture": data.get("picture")}})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await users.insert_one({
            "user_id": user_id, "email": email, "name": data.get("name"),
            "picture": data.get("picture"), "created_at": _now(),
        })

    session_token = secrets.token_urlsafe(48)
    await sessions.insert_one({
        "user_id": user_id, "session_token": session_token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS),
        "created_at": _now(),
    })
    response = RedirectResponse(GOOGLE_OAUTH_SUCCESS_URL, status_code=303)
    response.set_cookie(
        key="session_token", value=session_token, httponly=True, secure=True,
        samesite="lax", path="/", max_age=SESSION_TTL_DAYS * 24 * 3600,
    )
    response.delete_cookie("oauth_state", path="/api/auth/google")
    response.delete_cookie("oauth_code_verifier", path="/api/auth/google")
    return response


@api.get("/auth/me")
async def auth_me(request: Request):
    user = await _current_user(request)
    return {"email": user["email"], "name": user.get("name"), "picture": user.get("picture")}


@api.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = request.cookies.get("session_token") or ""
    if token:
        await sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/", samesite="lax", secure=True)
    return {"ok": True}


# ===================== Account-owned saves (authenticated) =====================
def _public_account(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "saveSchemaVersion": doc["saveSchemaVersion"],
        "contentVersions": doc.get("contentVersions", {}),
        "playerState": doc["playerState"],
        "revision": doc["revision"],
        "createdAt": doc["createdAt"],
        "updatedAt": doc["updatedAt"],
    }


@api.get("/me/save")
async def get_my_save(request: Request):
    user = await _current_user(request)
    doc = await account_saves.find_one({"userId": user["user_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return _public_account(doc)


@api.put("/me/save")
async def put_my_save(request: Request, payload: SavePayload):
    user = await _current_user(request)
    if payload.saveSchemaVersion not in SUPPORTED_SAVE_SCHEMA_VERSIONS:
        raise HTTPException(status_code=422, detail={"error": "unsupported_save_schema"})
    uid = user["user_id"]
    existing = await account_saves.find_one({"userId": uid})
    state_dict = payload.playerState.model_dump()
    now = _now()
    if existing is None:
        if payload.baseRevision != 0:
            return JSONResponse(status_code=409, content={"error": "revision_conflict", "reason": "no_server_save", "currentSave": None})
        doc = {"userId": uid, "saveSchemaVersion": payload.saveSchemaVersion,
               "contentVersions": payload.contentVersions, "playerState": state_dict,
               "revision": 1, "createdAt": now, "updatedAt": now}
        try:
            await account_saves.insert_one(doc)
        except DuplicateKeyError:
            return await _account_conflict(uid)
        return _public_account(doc)
    if payload.baseRevision != existing["revision"]:
        return JSONResponse(status_code=409, content={"error": "revision_conflict", "reason": "stale_revision", "currentSave": _public_account(existing)})
    new_rev = existing["revision"] + 1
    result = await account_saves.update_one({"userId": uid, "revision": existing["revision"]},
        {"$set": {"saveSchemaVersion": payload.saveSchemaVersion, "contentVersions": payload.contentVersions,
                  "playerState": state_dict, "revision": new_rev, "updatedAt": now}})
    if result.matched_count == 0:
        return await _account_conflict(uid)
    updated = {**existing, "saveSchemaVersion": payload.saveSchemaVersion, "contentVersions": payload.contentVersions,
               "playerState": state_dict, "revision": new_rev, "updatedAt": now}
    return _public_account(updated)


async def _account_conflict(uid: str) -> JSONResponse:
    latest = await account_saves.find_one({"userId": uid})
    return JSONResponse(status_code=409, content={
        "error": "revision_conflict", "reason": "stale_revision",
        "currentSave": _public_account(latest) if latest else None,
    })


# ===================== Claim / link anonymous progress =====================
class ClaimRequest(BaseModel):
    playerId: str
    strategy: Optional[str] = None  # 'use_account' | 'use_anonymous' when both exist


@api.post("/me/claim")
async def claim_save(request: Request, body: ClaimRequest):
    user = await _current_user(request)
    uid = user["user_id"]
    if not PLAYER_ID_RE.match(body.playerId):
        raise HTTPException(status_code=400, detail={"error": "invalid_player_id"})

    now = _now()
    anon = await saves.find_one({"playerId": body.playerId})
    account = await account_saves.find_one({"userId": uid})

    # An anonymous save already claimed by someone else cannot be hijacked.
    if anon and anon.get("claimedBy") and anon["claimedBy"] != uid:
        raise HTTPException(status_code=403, detail={"error": "already_claimed"})

    if not anon and not account:
        raise HTTPException(status_code=404, detail={"error": "nothing_to_claim"})

    unclaimed_anon = bool(anon and not anon.get("claimedBy"))

    # A fresh anonymous save AND an existing account save both exist -> user must choose.
    if unclaimed_anon and account and not body.strategy:
        return JSONResponse(status_code=409, content={
            "error": "claim_conflict",
            "accountSave": _public_account(account),
            "anonymousSave": {"revision": anon["revision"], "playerState": anon["playerState"],
                              "contentVersions": anon.get("contentVersions", {}),
                              "saveSchemaVersion": anon["saveSchemaVersion"]},
        })

    async def _guard_anon() -> bool:
        """Atomically stamp the anon save as ours iff it's unclaimed or already ours.
        Returns False only when another user owns it (=> 403)."""
        if not anon:
            return True
        res = await saves.update_one(
            {"playerId": body.playerId, "$or": [{"claimedBy": {"$exists": False}}, {"claimedBy": uid}]},
            {"$set": {"claimedBy": uid, "updatedAt": now}},
        )
        if res.matched_count == 1:
            return True
        latest = await saves.find_one({"playerId": body.playerId})
        return bool(latest and latest.get("claimedBy") == uid)

    def account_from_anon(a):
        return {"userId": uid, "historicalAnonymousId": a["playerId"],
                "saveSchemaVersion": a["saveSchemaVersion"], "contentVersions": a.get("contentVersions", {}),
                "playerState": a["playerState"], "revision": 1, "createdAt": now, "updatedAt": now}

    # --- Adopt anon into a NEW account save (also the recovery path for an
    #     interrupted claim where anon is already ours but no account exists). ---
    if anon and not account:
        if not await _guard_anon():
            raise HTTPException(status_code=403, detail={"error": "already_claimed"})
        # $setOnInsert makes this a no-op if a concurrent request already created it.
        await account_saves.update_one({"userId": uid}, {"$setOnInsert": account_from_anon(anon)}, upsert=True)
        result = await account_saves.find_one({"userId": uid})
        return _public_account(result)

    # --- Explicit "keep this device's progress": overwrite account with anon,
    #     but never clobber a concurrently-updated account save. ---
    if anon and account and body.strategy == "use_anonymous":
        if not await _guard_anon():
            raise HTTPException(status_code=403, detail={"error": "already_claimed"})
        new_rev = account["revision"] + 1
        res = await account_saves.update_one(
            {"userId": uid, "revision": account["revision"]},
            {"$set": {"saveSchemaVersion": anon["saveSchemaVersion"], "contentVersions": anon.get("contentVersions", {}),
                      "playerState": anon["playerState"], "historicalAnonymousId": anon["playerId"],
                      "revision": new_rev, "updatedAt": now}},
        )
        if res.matched_count == 0:
            latest = await account_saves.find_one({"userId": uid})
            return JSONResponse(status_code=409, content={
                "error": "revision_conflict", "reason": "account_changed",
                "currentSave": _public_account(latest) if latest else None,
            })
        result = await account_saves.find_one({"userId": uid})
        return _public_account(result)

    # --- use_account, idempotent re-claim, or account-only: just fence the anon
    #     save (so the old device can't keep writing) and return the account save. ---
    if not await _guard_anon():
        raise HTTPException(status_code=403, detail={"error": "already_claimed"})
    result = await account_saves.find_one({"userId": uid})
    if not result:
        raise HTTPException(status_code=404, detail={"error": "nothing_to_claim"})
    return _public_account(result)


app.include_router(api)

# Exact-token feature gate: the default and every unrecognised value leave
# these routes absent. Registry loading also stays behind the gate so a normal
# deployment retains the pre-Phase-6C startup surface.
_trusted_registry = load_registry() if TRUSTED_PROGRESSION_ENABLED else None
TRUSTED_PROGRESSION_ROUTES_REGISTERED = register_trusted_progression_routes(
    app,
    activation_value=TRUSTED_PROGRESSION_ACTIVATION,
    current_user=_current_user,
    ledgers=progression_ledgers,
    events=progression_events,
    registry=_trusted_registry,
)
