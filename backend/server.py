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
import logging
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
from admin_access import configured_admin_emails, is_admin_email

load_dotenv()

MONGO_URL = os.environ.get("MONGO_URL") or os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("DB_NAME", "vampires_choice_phase6c_staging")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")
GOOGLE_OAUTH_SUCCESS_URL = os.environ.get("GOOGLE_OAUTH_SUCCESS_URL", "/")
ADMIN_EMAILS = configured_admin_emails(os.environ.get("ADMIN_EMAILS"))
SESSION_TTL_DAYS = 7
SESSION_COOKIE_NAME = "__Host-vc_session"
LEGACY_SESSION_COOKIE_NAME = "session_token"
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
admin_drafts = db["admin_drafts"]

app = FastAPI(title="Vampire's Choice Cloud Save API")
auth_logger = logging.getLogger("vampires_choice.auth")


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
    await admin_drafts.create_index("draftId", unique=True)
    await admin_drafts.create_index([("bookId", 1), ("updatedAt", -1)])
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
    """Resolve the authenticated user from the app cookie or Bearer header.
    A client-supplied anonymous player id is NEVER accepted here."""
    token = (
        request.cookies.get(SESSION_COOKIE_NAME)
        or request.cookies.get(LEGACY_SESSION_COOKIE_NAME)
    )
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        auth_logger.warning(
            "authentication_rejected",
            extra={"auth_reason": "missing_token", "auth_path": request.url.path},
        )
        raise HTTPException(status_code=401, detail={"error": "not_authenticated"})

    sess = await sessions.find_one({"session_token": token}, {"_id": 0})
    if not sess:
        auth_logger.warning(
            "authentication_rejected",
            extra={"auth_reason": "invalid_session", "auth_path": request.url.path},
        )
        raise HTTPException(status_code=401, detail={"error": "invalid_session"})
    exp = sess["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        await sessions.delete_one({"session_token": token})
        auth_logger.warning(
            "authentication_rejected",
            extra={"auth_reason": "session_expired", "auth_path": request.url.path},
        )
        raise HTTPException(status_code=401, detail={"error": "session_expired"})

    user = await users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    if not user:
        auth_logger.warning(
            "authentication_rejected",
            extra={"auth_reason": "user_not_found", "auth_path": request.url.path},
        )
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
        key=SESSION_COOKIE_NAME, value=session_token, httponly=True, secure=True,
        samesite="lax", path="/", max_age=SESSION_TTL_DAYS * 24 * 3600,
    )
    # Remove the former generic cookie name so hosting/auth middleware cannot
    # collide with the application session during a preview deployment.
    response.delete_cookie(
        LEGACY_SESSION_COOKIE_NAME, path="/", samesite="lax", secure=True,
    )
    response.delete_cookie("oauth_state", path="/api/auth/google")
    response.delete_cookie("oauth_code_verifier", path="/api/auth/google")
    return response


@api.get("/auth/me")
async def auth_me(request: Request):
    user = await _current_user(request)
    return {"email": user["email"], "name": user.get("name"), "picture": user.get("picture")}


# ===================== Phase 7/8 admin workspace =====================
def _require_admin(user: Dict[str, Any]) -> None:
    if not is_admin_email(user.get("email"), ADMIN_EMAILS):
        raise HTTPException(status_code=403, detail={"error": "admin_required"})


@api.get("/admin/me")
async def admin_me(request: Request):
    user = await _current_user(request)
    return {"isAdmin": is_admin_email(user.get("email"), ADMIN_EMAILS)}


@api.get("/admin/content-catalog")
async def admin_content_catalog(request: Request):
    user = await _current_user(request)
    _require_admin(user)
    registry = load_registry()
    books = registry.get("books", {})
    return {
        "series": registry.get("series", {}).get("books", []),
        "books": [
            {
                "id": book_id,
                "version": book.get("version"),
                "startingSceneId": book.get("startingSceneId"),
                "sceneCount": len(book.get("scenes", {})),
            }
            for book_id, book in books.items()
            if isinstance(book, dict)
        ],
    }


class AdminDraftInput(BaseModel):
    """A deliberately small authoring format.

    Drafts are not player-facing content and are never loaded by the trusted
    progression reducer. Publishing remains a separate, reviewable step.
    """

    model_config = ConfigDict(extra="forbid")
    bookId: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    synopsis: str = Field(max_length=8000)
    branchNotes: str = Field(max_length=12000)


class AdminDraftUpdate(AdminDraftInput):
    baseRevision: int = Field(ge=1)


class AdminChoiceInput(BaseModel):
    """One manually-authored route out of a draft scene."""

    model_config = ConfigDict(extra="forbid")
    choiceId: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=300)
    nextSceneId: Optional[str] = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    effectsNotes: str = Field(default="", max_length=1000)


class AdminSceneInput(BaseModel):
    """A bounded manual scene format, separate from published story content."""

    model_config = ConfigDict(extra="forbid")
    sceneId: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    chapterNumber: int = Field(ge=1, le=200)
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=12000)
    choices: List[AdminChoiceInput] = Field(default_factory=list, max_length=8)


class AdminDraftScenesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseRevision: int = Field(ge=1)
    scenes: List[AdminSceneInput] = Field(default_factory=list, max_length=200)


def _validate_manual_scenes(scenes: List[AdminSceneInput]) -> None:
    scene_ids = [scene.sceneId for scene in scenes]
    if len(scene_ids) != len(set(scene_ids)):
        raise HTTPException(status_code=422, detail={"error": "duplicate_scene_id"})
    for scene in scenes:
        choice_ids = [choice.choiceId for choice in scene.choices]
        if len(choice_ids) != len(set(choice_ids)):
            raise HTTPException(status_code=422, detail={"error": "duplicate_choice_id", "sceneId": scene.sceneId})


def _public_admin_draft(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "draftId": doc["draftId"],
        "bookId": doc["bookId"],
        "title": doc["title"],
        "synopsis": doc["synopsis"],
        "branchNotes": doc["branchNotes"],
        "scenes": doc.get("scenes", []),
        "status": doc.get("status", "draft"),
        "revision": doc["revision"],
        "createdAt": doc["createdAt"],
        "updatedAt": doc["updatedAt"],
        "updatedBy": doc["updatedBy"],
    }


@api.get("/admin/drafts")
async def list_admin_drafts(request: Request):
    user = await _current_user(request)
    _require_admin(user)
    docs = await admin_drafts.find({}, {"_id": 0}).sort("updatedAt", -1).to_list(length=100)
    return {"drafts": [_public_admin_draft(doc) for doc in docs]}


@api.post("/admin/drafts", status_code=201)
async def create_admin_draft(request: Request, payload: AdminDraftInput):
    user = await _current_user(request)
    _require_admin(user)
    now = _now()
    doc = {
        "draftId": f"draft_{uuid.uuid4().hex}",
        **payload.model_dump(),
        "revision": 1,
        "status": "draft",
        "scenes": [],
        "createdAt": now,
        "updatedAt": now,
        "updatedBy": user["email"],
    }
    await admin_drafts.insert_one(doc)
    return _public_admin_draft(doc)


@api.put("/admin/drafts/{draft_id}")
async def update_admin_draft(draft_id: str, request: Request, payload: AdminDraftUpdate):
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"draft_[0-9a-f]{32}", draft_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_draft_id"})
    now = _now()
    changes = payload.model_dump(exclude={"baseRevision"})
    updated = await admin_drafts.find_one_and_update(
        {"draftId": draft_id, "revision": payload.baseRevision},
        {"$set": {**changes, "updatedAt": now, "updatedBy": user["email"]}, "$inc": {"revision": 1}},
        return_document=True,
    )
    if updated is None:
        current = await admin_drafts.find_one({"draftId": draft_id}, {"_id": 0})
        if current is None:
            raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
        return JSONResponse(status_code=409, content={"error": "revision_conflict", "currentDraft": _public_admin_draft(current)})
    return _public_admin_draft(updated)


@api.put("/admin/drafts/{draft_id}/scenes")
async def update_admin_draft_scenes(draft_id: str, request: Request, payload: AdminDraftScenesUpdate):
    """Replace a draft's manual scene list; this does not publish content."""
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"draft_[0-9a-f]{32}", draft_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_draft_id"})
    _validate_manual_scenes(payload.scenes)
    now = _now()
    updated = await admin_drafts.find_one_and_update(
        {"draftId": draft_id, "revision": payload.baseRevision},
        {"$set": {"scenes": [scene.model_dump() for scene in payload.scenes], "updatedAt": now, "updatedBy": user["email"]}, "$inc": {"revision": 1}},
        return_document=True,
    )
    if updated is None:
        current = await admin_drafts.find_one({"draftId": draft_id}, {"_id": 0})
        if current is None:
            raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
        return JSONResponse(status_code=409, content={"error": "revision_conflict", "currentDraft": _public_admin_draft(current)})
    return _public_admin_draft(updated)


@api.post("/admin/drafts/{draft_id}/request-review")
async def request_admin_draft_review(draft_id: str, request: Request):
    """Move a finished draft into review; this never publishes game content."""
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"draft_[0-9a-f]{32}", draft_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_draft_id"})
    now = _now()
    updated = await admin_drafts.find_one_and_update(
        {"draftId": draft_id, "status": {"$ne": "ready_for_review"}},
        {"$set": {"status": "ready_for_review", "updatedAt": now, "updatedBy": user["email"]}, "$inc": {"revision": 1}},
        return_document=True,
    )
    if updated is None:
        current = await admin_drafts.find_one({"draftId": draft_id}, {"_id": 0})
        if current is None:
            raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
        return _public_admin_draft(current)
    return _public_admin_draft(updated)


@api.get("/admin/drafts/{draft_id}/validation")
async def validate_admin_draft(draft_id: str, request: Request):
    """Return editorial readiness checks without mutating a draft or publishing it."""
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"draft_[0-9a-f]{32}", draft_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_draft_id"})
    draft = await admin_drafts.find_one({"draftId": draft_id}, {"_id": 0})
    if draft is None:
        raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
    known_books = {item.get("id") for item in load_registry().get("series", {}).get("books", []) if isinstance(item, dict)}
    issues = []
    if draft.get("bookId") not in known_books:
        issues.append({"code": "unknown_book", "message": "Choose a book from the series catalogue."})
    if len(draft.get("title", "").strip()) < 3:
        issues.append({"code": "title_too_short", "message": "Use a title of at least 3 characters."})
    if len(draft.get("synopsis", "").strip()) < 40:
        issues.append({"code": "synopsis_too_short", "message": "Add a synopsis of at least 40 characters."})
    if len(draft.get("branchNotes", "").strip()) < 40:
        issues.append({"code": "branch_notes_too_short", "message": "Add at least 40 characters of branch notes."})
    scenes = draft.get("scenes", [])
    if not scenes:
        issues.append({"code": "no_scenes", "message": "Add at least one manually written scene."})
    else:
        scene_ids = {scene.get("sceneId") for scene in scenes if isinstance(scene, dict)}
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            for choice in scene.get("choices", []):
                target = choice.get("nextSceneId") if isinstance(choice, dict) else None
                if target and target not in scene_ids:
                    issues.append({"code": "unknown_scene_target", "message": f"Choice in '{scene.get('sceneId', 'a scene')}' points to missing scene '{target}'."})
    return {"draftId": draft_id, "valid": not issues, "issues": issues}


@api.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = (
        request.cookies.get(SESSION_COOKIE_NAME)
        or request.cookies.get(LEGACY_SESSION_COOKIE_NAME)
        or ""
    )
    if token:
        await sessions.delete_one({"session_token": token})
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", samesite="lax", secure=True)
    response.delete_cookie(
        LEGACY_SESSION_COOKIE_NAME, path="/", samesite="lax", secure=True,
    )
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
