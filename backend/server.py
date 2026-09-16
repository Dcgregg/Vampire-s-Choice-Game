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
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
import uuid

load_dotenv()

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
EMERGENT_SESSION_URL = os.environ.get(
    "EMERGENT_SESSION_URL",
    "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
)
SESSION_TTL_DAYS = 7

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
        if payload.baseRevision not in (0,):
            raise HTTPException(
                status_code=409,
                detail={"error": "revision_conflict", "reason": "no_server_save", "currentSave": None},
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
        await saves.insert_one(doc)
        return _public(doc)

    # Optimistic concurrency: only accept if the client is up to date.
    if payload.baseRevision != existing["revision"]:
        return JSONResponse(
            status_code=409,
            content={"error": "revision_conflict", "reason": "stale_revision", "currentSave": _public(existing)},
        )

    new_rev = existing["revision"] + 1
    await saves.update_one(
        {"playerId": player_id, "revision": existing["revision"]},
        {"$set": {
            "saveSchemaVersion": payload.saveSchemaVersion,
            "contentVersions": payload.contentVersions,
            "playerState": state_dict,
            "revision": new_rev,
            "updatedAt": now,
        }},
    )
    existing.update({
        "saveSchemaVersion": payload.saveSchemaVersion,
        "contentVersions": payload.contentVersions,
        "playerState": state_dict,
        "revision": new_rev,
        "updatedAt": now,
    })
    return _public(existing)


# ===================== Authentication (Emergent Google) =====================
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


class SessionRequest(BaseModel):
    session_id: str


@api.post("/auth/session")
async def auth_session(body: SessionRequest, response: Response):
    # Exchange the one-time session_id with Emergent (server-side only).
    req = urllib.request.Request(EMERGENT_SESSION_URL, headers={"X-Session-ID": body.session_id})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = _json.loads(r.read().decode())
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "invalid_session_id"})

    email = data.get("email")
    if not email:
        raise HTTPException(status_code=401, detail={"error": "invalid_session_data"})

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

    session_token = data.get("session_token") or uuid.uuid4().hex
    await sessions.insert_one({
        "user_id": user_id, "session_token": session_token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS),
        "created_at": _now(),
    })
    response.set_cookie(
        key="session_token", value=session_token, httponly=True, secure=True,
        samesite="none", path="/", max_age=SESSION_TTL_DAYS * 24 * 3600,
    )
    return {"email": email, "name": data.get("name"), "picture": data.get("picture")}


@api.get("/auth/me")
async def auth_me(request: Request):
    user = await _current_user(request)
    return {"email": user["email"], "name": user.get("name"), "picture": user.get("picture")}


@api.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = request.cookies.get("session_token") or ""
    if token:
        await sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/", samesite="none", secure=True)
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
        if payload.baseRevision not in (0,):
            return JSONResponse(status_code=409, content={"error": "revision_conflict", "reason": "no_server_save", "currentSave": None})
        doc = {"userId": uid, "saveSchemaVersion": payload.saveSchemaVersion,
               "contentVersions": payload.contentVersions, "playerState": state_dict,
               "revision": 1, "createdAt": now, "updatedAt": now}
        await account_saves.insert_one(doc)
        return _public_account(doc)
    if payload.baseRevision != existing["revision"]:
        return JSONResponse(status_code=409, content={"error": "revision_conflict", "reason": "stale_revision", "currentSave": _public_account(existing)})
    new_rev = existing["revision"] + 1
    await account_saves.update_one({"userId": uid, "revision": existing["revision"]},
        {"$set": {"saveSchemaVersion": payload.saveSchemaVersion, "contentVersions": payload.contentVersions,
                  "playerState": state_dict, "revision": new_rev, "updatedAt": now}})
    existing.update({"saveSchemaVersion": payload.saveSchemaVersion, "contentVersions": payload.contentVersions,
                     "playerState": state_dict, "revision": new_rev, "updatedAt": now})
    return _public_account(existing)


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

    anon = await saves.find_one({"playerId": body.playerId})
    account = await account_saves.find_one({"userId": uid})
    now = _now()

    # An anonymous save already claimed by someone else cannot be hijacked.
    if anon and anon.get("claimedBy") and anon["claimedBy"] != uid:
        raise HTTPException(status_code=403, detail={"error": "already_claimed"})

    # Nothing to claim and no account save.
    if not anon and not account:
        raise HTTPException(status_code=404, detail={"error": "nothing_to_claim"})

    # Account already has a save AND a meaningful anonymous save exists -> need a choice.
    if anon and account and not anon.get("claimedBy") and not body.strategy:
        return JSONResponse(status_code=409, content={
            "error": "claim_conflict",
            "accountSave": _public_account(account),
            "anonymousSave": {"revision": anon["revision"], "playerState": anon["playerState"],
                              "contentVersions": anon.get("contentVersions", {}),
                              "saveSchemaVersion": anon["saveSchemaVersion"]},
        })

    def account_from_anon(a):
        return {"userId": uid, "historicalAnonymousId": a["playerId"],
                "saveSchemaVersion": a["saveSchemaVersion"], "contentVersions": a.get("contentVersions", {}),
                "playerState": a["playerState"], "revision": 1, "createdAt": now, "updatedAt": now}

    if anon and not account:
        # Atomic-ish create from anonymous; mark anonymous claimed so old id can't reuse it.
        doc = account_from_anon(anon)
        await account_saves.update_one({"userId": uid}, {"$setOnInsert": doc}, upsert=True)
        await saves.update_one({"playerId": body.playerId}, {"$set": {"claimedBy": uid, "updatedAt": now}})
        result = await account_saves.find_one({"userId": uid})
        return _public_account(result)

    if anon and account and body.strategy == "use_anonymous":
        new_rev = account["revision"] + 1
        await account_saves.update_one({"userId": uid}, {"$set": {
            "saveSchemaVersion": anon["saveSchemaVersion"], "contentVersions": anon.get("contentVersions", {}),
            "playerState": anon["playerState"], "historicalAnonymousId": anon["playerId"],
            "revision": new_rev, "updatedAt": now}})
        await saves.update_one({"playerId": body.playerId}, {"$set": {"claimedBy": uid, "updatedAt": now}})
        result = await account_saves.find_one({"userId": uid})
        return _public_account(result)

    # use_account (explicit) OR anon already claimed by this user (idempotent) OR account-only.
    if anon and not anon.get("claimedBy"):
        await saves.update_one({"playerId": body.playerId}, {"$set": {"claimedBy": uid, "updatedAt": now}})
    if account:
        return _public_account(account)
    result = await account_saves.find_one({"userId": uid})
    return _public_account(result)


app.include_router(api)
