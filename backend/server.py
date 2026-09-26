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
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
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
STORY_TOKEN_RE = re.compile(r"{{\s*([A-Za-z][A-Za-z0-9_.-]*)\s*}}")
ALLOWED_STORY_TOKENS = {"player.name", "player.subject", "player.object", "player.possessive", "player.species", "speaker.name"}
STORY_CONTEXT_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
saves = db["cloud_saves"]        # anonymous saves (weaker trust model)
account_saves = db["account_saves"]  # account-owned saves (authenticated)
users = db["users"]
sessions = db["user_sessions"]
progression_ledgers = db["progression_ledgers"]
progression_events = db["progression_events"]
admin_drafts = db["admin_drafts"]
admin_characters = db["admin_characters"]
admin_releases = db["admin_releases"]

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
    await admin_characters.create_index("characterId", unique=True)
    await admin_releases.create_index("releaseId", unique=True)
    await admin_releases.create_index([("bookId", 1), ("version", 1)], unique=True)
    # One approved snapshot creates one immutable release version. Editing a
    # draft clears its approval, so a later approval deliberately creates a
    # new source revision instead of silently replacing this record.
    await admin_releases.create_index([("source.draftId", 1), ("source.approvedRevision", 1)], unique=True)
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
    storyValues: Dict[str, str] = Field(default_factory=dict, max_length=20)
    relationshipValues: Dict[str, str] = Field(default_factory=dict, max_length=20)


class AdminDraftUpdate(AdminDraftInput):
    baseRevision: int = Field(ge=1)


class AdminChoiceInput(BaseModel):
    """One manually-authored route out of a draft scene."""

    model_config = ConfigDict(extra="forbid")
    choiceId: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=300)
    nextSceneId: Optional[str] = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    effectsNotes: str = Field(default="", max_length=1000)
    effects: List["AdminEffectInput"] = Field(default_factory=list, max_length=6)


class AdminEffectInput(BaseModel):
    """A bounded, data-only state change for private playtests."""
    model_config = ConfigDict(extra="forbid")
    target: str = Field(pattern=r"^(humanity|bloodCoins|affinity\.[A-Za-z0-9_-]+)$", max_length=100)
    delta: int = Field(ge=-10000, le=10000)


class AdminDialogueInput(BaseModel):
    """A presentational dialogue beat in a private authoring draft."""

    model_config = ConfigDict(extra="forbid")
    speakerId: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    displayName: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=4000)
    mood: str = Field(default="neutral", max_length=40, pattern=r"^[A-Za-z0-9_-]+$")


class AdminCharacterInput(BaseModel):
    """Portable character metadata for private authoring and dialogue UI."""

    model_config = ConfigDict(extra="forbid")
    characterId: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    displayName: str = Field(min_length=1, max_length=120)
    defaultMood: str = Field(default="neutral", max_length=40, pattern=r"^[A-Za-z0-9_-]+$")


class AdminSceneInput(BaseModel):
    """A bounded manual scene format, separate from published story content."""

    model_config = ConfigDict(extra="forbid")
    sceneId: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    chapterNumber: int = Field(ge=1, le=200)
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=12000)
    dialogue: List[AdminDialogueInput] = Field(default_factory=list, max_length=20)
    choices: List[AdminChoiceInput] = Field(default_factory=list, max_length=8)


class AdminDraftScenesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseRevision: int = Field(ge=1)
    scenes: List[AdminSceneInput] = Field(default_factory=list, max_length=200)


class AdminAiDraftRequest(BaseModel):
    """Bounded creative brief for admin-only OpenRouter draft generation."""

    model_config = ConfigDict(extra="forbid")
    bookId: str = Field(min_length=1, max_length=80)
    premise: str = Field(min_length=20, max_length=2000)
    desiredTitle: str = Field(default="", max_length=160)


class AdminBookJsonImport(BaseModel):
    """An uploaded authoring file. It is always converted to a private draft."""
    model_config = ConfigDict(extra="forbid")
    content: Dict[str, Any]


class AdminGeneratedDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    synopsis: str = Field(max_length=8000)
    branchNotes: str = Field(max_length=12000)
    scenes: List[AdminSceneInput] = Field(min_length=3, max_length=8)


def _story_context_tokens(story_values: Optional[Dict[str, str]] = None, relationship_values: Optional[Dict[str, str]] = None) -> set[str]:
    story_values = story_values or {}
    relationship_values = relationship_values or {}
    for values in (story_values, relationship_values):
        for key, value in values.items():
            if not STORY_CONTEXT_KEY_RE.fullmatch(key) or not isinstance(value, str) or len(value) > 160:
                raise HTTPException(status_code=422, detail={"error": "invalid_story_context"})
    return ALLOWED_STORY_TOKENS | {f"story.{key}" for key in story_values} | {f"relationship.{key}" for key in relationship_values}


def _validate_manual_scenes(scenes: List[AdminSceneInput], story_values: Optional[Dict[str, str]] = None, relationship_values: Optional[Dict[str, str]] = None) -> None:
    allowed_tokens = _story_context_tokens(story_values, relationship_values)
    scene_ids = [scene.sceneId for scene in scenes]
    if len(scene_ids) != len(set(scene_ids)):
        raise HTTPException(status_code=422, detail={"error": "duplicate_scene_id"})
    for scene in scenes:
        for value, field in ((scene.title, "title"), (scene.body, "body")):
            unknown = sorted({token for token in STORY_TOKEN_RE.findall(value) if token not in allowed_tokens})
            if unknown:
                raise HTTPException(status_code=422, detail={"error": "unknown_story_token", "sceneId": scene.sceneId, "field": field, "tokens": unknown})
        choice_ids = [choice.choiceId for choice in scene.choices]
        if len(choice_ids) != len(set(choice_ids)):
            raise HTTPException(status_code=422, detail={"error": "duplicate_choice_id", "sceneId": scene.sceneId})
        for choice in scene.choices:
            unknown = sorted({token for token in STORY_TOKEN_RE.findall(choice.text) if token not in allowed_tokens})
            if unknown:
                raise HTTPException(status_code=422, detail={"error": "unknown_story_token", "sceneId": scene.sceneId, "field": "choice", "tokens": unknown})
        for dialogue in scene.dialogue:
            for value, field in ((dialogue.displayName, "dialogueDisplayName"), (dialogue.text, "dialogueText")):
                unknown = sorted({token for token in STORY_TOKEN_RE.findall(value) if token not in allowed_tokens})
                if unknown:
                    raise HTTPException(status_code=422, detail={"error": "unknown_story_token", "sceneId": scene.sceneId, "field": field, "tokens": unknown})


def _import_book_json(content: Dict[str, Any]) -> Dict[str, Any]:
    """Convert supported book JSON into the private draft format; never publish."""
    source = content.get("draft", content) if isinstance(content, dict) else {}
    if not isinstance(source, dict):
        raise HTTPException(status_code=422, detail={"error": "invalid_book_json"})
    raw_scenes = source.get("scenes", [])
    if not isinstance(raw_scenes, list):
        raise HTTPException(status_code=422, detail={"error": "invalid_book_scenes"})
    book = source.get("book") if isinstance(source.get("book"), dict) else {}
    book_id = source.get("bookId", book.get("id", ""))
    title = source.get("title", book.get("title", ""))
    synopsis = source.get("synopsis", book.get("synopsis", ""))
    branch_notes = source.get("branchNotes", book.get("subtitle", "Imported from Book JSON for editorial review."))
    converted = []
    for index, scene in enumerate(raw_scenes):
        if not isinstance(scene, dict):
            continue
        if "sceneId" in scene:
            converted.append(scene)
            continue
        paragraphs = scene.get("paragraphs", [])
        body_parts = [part for part in paragraphs if isinstance(part, str)] if isinstance(paragraphs, list) else []
        for dialogue in scene.get("dialogues", []) if isinstance(scene.get("dialogues", []), list) else []:
            if isinstance(dialogue, dict) and isinstance(dialogue.get("text"), str):
                speaker = dialogue.get("speaker", "")
                body_parts.append(f"{speaker}: {dialogue['text']}" if speaker else dialogue["text"])
        choices = []
        for choice_index, choice in enumerate(scene.get("choices", []) if isinstance(scene.get("choices", []), list) else []):
            if not isinstance(choice, dict):
                continue
            notes = choice.get("consequencesSummary", "")
            if choice.get("effects"):
                notes = f"{notes}\nEffects: {_json.dumps(choice['effects'], separators=(',', ':'))}".strip()
            choices.append({"choiceId": choice.get("id", f"choice-{choice_index + 1}"), "text": choice.get("text", ""), "nextSceneId": None if choice.get("endsBook") else choice.get("nextSceneId"), "effectsNotes": notes[:1000]})
        dialogue = scene.get("dialogue", []) if isinstance(scene.get("dialogue"), list) else []
        converted.append({"sceneId": scene.get("id", f"scene-{index + 1}"), "chapterNumber": scene.get("chapterNumber", 1), "title": scene.get("sceneTitle", scene.get("title", "")), "body": "\n\n".join(body_parts), "dialogue": dialogue, "choices": choices})
    try:
        details = AdminDraftInput(bookId=book_id, title=title, synopsis=synopsis, branchNotes=branch_notes)
        scenes = [AdminSceneInput.model_validate(scene) for scene in converted]
    except Exception:
        raise HTTPException(status_code=422, detail={"error": "invalid_book_json"})
    _validate_manual_scenes(scenes)
    draft = {**details.model_dump(), "scenes": [scene.model_dump() for scene in scenes]}
    issues = _admin_draft_validation_issues(draft)
    if issues:
        raise HTTPException(status_code=422, detail={"error": "book_json_failed_validation", "issues": issues})
    return draft


def _openrouter_json(prompt: str) -> Dict[str, Any]:
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=503, detail={"error": "openrouter_not_configured"})
    request_body = _json.dumps({
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "You are a gothic fantasy interactive-fiction drafting assistant. Generate original writing only. Return only valid JSON; no markdown or commentary."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.85,
        "max_tokens": 5000,
        "response_format": {"type": "json_object"},
    }).encode()
    upstream = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=request_body,
        method="POST",
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(upstream, timeout=45) as response:
            payload = _json.loads(response.read().decode())
        content = payload["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        # Some free models still add a short sentence around the requested JSON.
        # Keep the API strict, while accepting that harmless presentation wrapper.
        if not content.startswith("{"):
            start, end = content.find("{"), content.rfind("}")
            if start >= 0 and end > start:
                content = content[start:end + 1]
        return _json.loads(content)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail={"error": "openrouter_generation_failed"})


def _generated_identifier(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "")).strip("-_")
    return (cleaned[:80] or fallback)


def _unique_generated_identifier(value: Any, fallback: str, used: set[str]) -> str:
    base = _generated_identifier(value, fallback)
    candidate, suffix = base, 2
    while candidate in used:
        ending = f"-{suffix}"
        candidate = f"{base[:80 - len(ending)]}{ending}"
        suffix += 1
    used.add(candidate)
    return candidate


def _normalise_generated_draft(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Accept small presentational variations from free models, then validate strictly."""
    raw_scenes = raw.get("scenes", raw.get("nodes", [])) if isinstance(raw, dict) else []
    original_to_clean = {}
    scenes = []
    used_scene_ids: set[str] = set()
    for index, item in enumerate(raw_scenes if isinstance(raw_scenes, list) else []):
        if not isinstance(item, dict):
            continue
        original_id = str(item.get("sceneId", item.get("id", "")))
        scene_id = _unique_generated_identifier(original_id, f"scene-{index + 1}", used_scene_ids)
        original_to_clean[original_id] = scene_id
        choices = []
        used_choice_ids: set[str] = set()
        for choice_index, choice in enumerate(item.get("choices", []) if isinstance(item.get("choices", []), list) else []):
            if not isinstance(choice, dict):
                continue
            target = choice.get("nextSceneId", choice.get("next", choice.get("destination")))
            choices.append({
                "choiceId": _unique_generated_identifier(choice.get("choiceId", choice.get("id")), f"choice-{choice_index + 1}", used_choice_ids),
                "text": choice.get("text", choice.get("label", "")),
                "nextSceneId": target,
                "effectsNotes": choice.get("effectsNotes", choice.get("effects", "")),
            })
        scenes.append({
            "sceneId": scene_id,
            "chapterNumber": 1,
            "title": item.get("title", ""),
            "body": item.get("body", item.get("content", item.get("text", ""))),
            "choices": choices,
        })
    for scene in scenes:
        for choice in scene["choices"]:
            if choice["nextSceneId"] is not None:
                choice["nextSceneId"] = original_to_clean.get(str(choice["nextSceneId"]), _generated_identifier(choice["nextSceneId"], "missing-scene"))
    return {
        "title": raw.get("title", "") if isinstance(raw, dict) else "",
        "synopsis": raw.get("synopsis", raw.get("summary", "")) if isinstance(raw, dict) else "",
        "branchNotes": raw.get("branchNotes", raw.get("notes", "")) if isinstance(raw, dict) else "",
        "scenes": scenes,
    }


def _sample_story_scenes() -> List[Dict[str, Any]]:
    """A complete, private sample for exercising the admin editor and playtest."""
    return [
        {"sceneId": "sample-gates", "chapterNumber": 1, "title": "The Gates of Blackthorn", "body": "Rain traced silver lines down Blackthorn Academy's iron gates. A stranger in a dark coat waited beneath the archway.\n\n‘You came,’ he said. ‘That is either very brave, or very foolish.’", "choices": [{"choiceId": "follow", "text": "Follow the stranger into the academy.", "nextSceneId": "sample-hall", "effectsNotes": "Trust Lucien."}, {"choiceId": "courtyard", "text": "Search the silent courtyard instead.", "nextSceneId": "sample-courtyard", "effectsNotes": "Independent route."}]},
        {"sceneId": "sample-hall", "chapterNumber": 1, "title": "The Candlelit Hall", "body": "Inside, the academy smelled of old books, candle wax, and roses left too long in water.\n\n‘My name is Lucien,’ the stranger said. ‘Tonight, be careful who you trust.’", "choices": [{"choiceId": "ask", "text": "Ask Lucien why you were invited.", "nextSceneId": "sample-invitation", "effectsNotes": "Direct route."}, {"choiceId": "portrait", "text": "Study the portrait watching you.", "nextSceneId": "sample-portrait", "effectsNotes": "Mystery route."}]},
        {"sceneId": "sample-courtyard", "chapterNumber": 1, "title": "The Silent Courtyard", "body": "Rainwater gathered around a black stone fountain. In the statue's open palm rested a second envelope, sealed with dark red wax and marked with your name.", "choices": [{"choiceId": "letter", "text": "Take the second envelope.", "nextSceneId": "sample-invitation", "effectsNotes": "Secret clue."}, {"choiceId": "return", "text": "Return to Lucien and demand answers.", "nextSceneId": "sample-hall", "effectsNotes": "Returns with lower trust."}]},
        {"sceneId": "sample-invitation", "chapterNumber": 1, "title": "The Second Invitation", "body": "The letter contains a single sentence: ‘At midnight, choose who you wish to become.’\n\nThe academy clock begins to strike eleven.", "choices": [{"choiceId": "accept", "text": "Keep the invitation and step into the academy.", "nextSceneId": "sample-ending", "effectsNotes": "Accept the mystery."}]},
        {"sceneId": "sample-portrait", "chapterNumber": 1, "title": "A Familiar Face", "body": "The portrait shows a young woman wearing your face. Beneath the frame, a brass plaque reads: ‘The last heir of Blackthorn.’", "choices": [{"choiceId": "question", "text": "Demand that Lucien explain the portrait.", "nextSceneId": "sample-ending", "effectsNotes": "Family mystery."}]},
        {"sceneId": "sample-ending", "chapterNumber": 1, "title": "Midnight Approaches", "body": "The academy doors close behind you. Somewhere in the dark, a bell rings twelve times.\n\nThis is the end of the sample route—for now.", "choices": []},
    ]


def _public_admin_draft(doc: Dict[str, Any]) -> Dict[str, Any]:
    current_approval = doc.get("reviewApproval")
    # Phase 16 introduced a history log. Older approved drafts still have the
    # current approval record, so expose it as their first history entry.
    history = doc.get("reviewHistory") or ([current_approval] if current_approval else [])
    return {
        "draftId": doc["draftId"],
        "bookId": doc["bookId"],
        "title": doc["title"],
        "synopsis": doc["synopsis"],
        "branchNotes": doc["branchNotes"],
        "storyValues": doc.get("storyValues", {}),
        "relationshipValues": doc.get("relationshipValues", {}),
        "scenes": doc.get("scenes", []),
        "status": doc.get("status", "draft"),
        "reviewApproval": current_approval,
        "reviewHistory": history,
        "revision": doc["revision"],
        "createdAt": doc["createdAt"],
        "updatedAt": doc["updatedAt"],
        "updatedBy": doc["updatedBy"],
    }


def _admin_draft_validation_issues(draft: Dict[str, Any]) -> List[Dict[str, str]]:
    """Editorial checks shared by review and export; never publish content."""
    issues: List[Dict[str, str]] = []
    # Drafts may be for a future instalment (for example `book3`) that is not
    # yet in the player catalogue. The catalogue is reference information, not
    # a publication gate. Keep only a stable ID-format check here.
    if not re.fullmatch(r"book[1-9][0-9]*", str(draft.get("bookId", ""))):
        issues.append({"code": "invalid_book_id", "message": "Use a future-safe book ID such as book1, book2 or book3."})
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
        graph = _draft_graph_report(draft)
        if graph["unreachableSceneIds"]:
            issues.append({"code": "unreachable_scenes", "message": f"Connect or remove unreachable scenes: {', '.join(graph['unreachableSceneIds'])}."})
        if not graph["terminalSceneIds"]:
            issues.append({"code": "no_terminal_scene", "message": "Add at least one terminal scene so a route can conclude."})
        elif graph["nonTerminatingSceneIds"]:
            issues.append({"code": "non_terminating_route", "message": f"These reachable scenes cannot reach an ending: {', '.join(graph['nonTerminatingSceneIds'])}."})
    return issues


def _draft_graph_report(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Analyse authoring routes without mutating a draft or player content."""
    scenes = [scene for scene in draft.get("scenes", []) if isinstance(scene, dict) and scene.get("sceneId")]
    scene_ids = [scene["sceneId"] for scene in scenes]
    if not scenes:
        return {"startSceneId": None, "sceneCount": 0, "reachableSceneIds": [], "unreachableSceneIds": [], "terminalSceneIds": [], "nonTerminatingSceneIds": []}
    known = set(scene_ids)
    edges = {scene_id: set() for scene_id in scene_ids}
    reverse = {scene_id: set() for scene_id in scene_ids}
    terminal = []
    for scene in scenes:
        scene_id = scene["sceneId"]
        targets = {choice.get("nextSceneId") for choice in scene.get("choices", []) if isinstance(choice, dict) and choice.get("nextSceneId") in known}
        edges[scene_id] = targets
        if not targets:
            terminal.append(scene_id)
        for target in targets:
            reverse[target].add(scene_id)
    start = scene_ids[0]
    reachable, pending = set(), [start]
    while pending:
        scene_id = pending.pop()
        if scene_id in reachable:
            continue
        reachable.add(scene_id)
        pending.extend(edges[scene_id] - reachable)
    can_finish, pending = set(), list(terminal)
    while pending:
        scene_id = pending.pop()
        if scene_id in can_finish:
            continue
        can_finish.add(scene_id)
        pending.extend(reverse[scene_id] - can_finish)
    return {"startSceneId": start, "sceneCount": len(scene_ids), "reachableSceneIds": [scene_id for scene_id in scene_ids if scene_id in reachable], "unreachableSceneIds": [scene_id for scene_id in scene_ids if scene_id not in reachable], "terminalSceneIds": terminal, "nonTerminatingSceneIds": [scene_id for scene_id in scene_ids if scene_id in reachable and scene_id not in can_finish]}


def _release_package(draft: Dict[str, Any]) -> Dict[str, Any]:
    """A checksum-protected hand-off package; it has no live publish effect."""
    draft_data = _public_admin_draft(draft)
    source = {"draftId": draft["draftId"], "approvedRevision": draft.get("reviewApproval", {}).get("approvedRevision"), "currentRevision": draft["revision"]}
    canonical = _json.dumps({"source": source, "draft": draft_data}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {"format": "vampires-choice-release-package/v1", "createdAt": _now(), "source": source, "manifest": {"sha256": hashlib.sha256(canonical).hexdigest(), "sceneCount": len(draft_data["scenes"]), "playerFacing": False, "published": False}, "draft": draft_data, "note": "This package is a review hand-off only. It cannot update live player content."}


def _review_export(draft: Dict[str, Any]) -> Dict[str, Any]:
    """A portable review package, intentionally separate from playable content."""
    if draft.get("status") == "approved_for_release":
        return _release_package(draft)
    return {
        "format": "vampires-choice-review-export/v1",
        "exportedAt": _now(),
        "source": {"draftId": draft["draftId"], "revision": draft["revision"], "status": draft.get("status", "draft")},
        "draft": _public_admin_draft(draft),
        "publication": {"playerFacing": False, "published": False, "note": "This file is for human review only and cannot update live story content."},
    }


def _public_admin_release(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Expose release-registry metadata without turning it into game content."""
    return {
        "releaseId": doc["releaseId"],
        "bookId": doc["bookId"],
        "version": doc["version"],
        "status": doc.get("status", "prepared"),
        "source": doc["source"],
        "manifest": doc["manifest"],
        "createdAt": doc["createdAt"],
        "createdBy": doc["createdBy"],
        "selectedAt": doc.get("selectedAt"),
        "selectedBy": doc.get("selectedBy"),
    }


async def _create_release_version(draft: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    """Freeze one approved draft revision for the private release registry.

    This is intentionally not connected to ``load_registry`` or any player
    endpoint. A later, separately authorised integration can consume this
    immutable snapshot after compatibility checks are defined.
    """
    package = _release_package(draft)
    source = package["source"]
    for _ in range(3):
        latest = await admin_releases.find_one({"bookId": draft["bookId"]}, {"version": 1}, sort=[("version", -1)])
        version = int(latest.get("version", 0)) + 1 if latest else 1
        now = _now()
        doc = {
            "releaseId": f"release_{uuid.uuid4().hex}",
            "bookId": draft["bookId"],
            "version": version,
            "status": "prepared",
            "source": source,
            "manifest": package["manifest"],
            "snapshot": package["draft"],
            "createdAt": now,
            "createdBy": user["email"],
        }
        try:
            await admin_releases.insert_one(doc)
            return _public_admin_release(doc)
        except DuplicateKeyError:
            existing = await admin_releases.find_one({"source.draftId": source["draftId"], "source.approvedRevision": source["approvedRevision"]}, {"_id": 0})
            if existing:
                return _public_admin_release(existing)
    raise HTTPException(status_code=409, detail={"error": "release_version_conflict"})


@api.get("/admin/drafts")
async def list_admin_drafts(request: Request):
    user = await _current_user(request)
    _require_admin(user)
    docs = await admin_drafts.find({}, {"_id": 0}).sort("updatedAt", -1).to_list(length=100)
    return {"drafts": [_public_admin_draft(doc) for doc in docs]}


@api.get("/admin/ai/status")
async def admin_ai_status(request: Request):
    user = await _current_user(request)
    _require_admin(user)
    return {"configured": bool(OPENROUTER_API_KEY), "model": OPENROUTER_MODEL if OPENROUTER_API_KEY else None}


@api.get("/admin/characters")
async def list_admin_characters(request: Request):
    user = await _current_user(request)
    _require_admin(user)
    characters = await admin_characters.find({}, {"_id": 0}).sort("displayName", 1).to_list(length=200)
    return {"characters": characters}


@api.post("/admin/characters", status_code=201)
async def create_admin_character(request: Request, payload: AdminCharacterInput):
    """Create private authoring metadata; never changes player content."""
    user = await _current_user(request)
    _require_admin(user)
    doc = {**payload.model_dump(), "createdAt": _now(), "createdBy": user["email"]}
    try:
        await admin_characters.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail={"error": "duplicate_character_id"})
    return {key: value for key, value in doc.items() if key != "_id"}


@api.put("/admin/characters/{character_id}")
async def update_admin_character(character_id: str, request: Request, payload: AdminCharacterInput):
    user = await _current_user(request)
    _require_admin(user)
    if character_id != payload.characterId:
        raise HTTPException(status_code=400, detail={"error": "character_id_immutable"})
    updated = await admin_characters.find_one_and_update({"characterId": character_id}, {"$set": {"displayName": payload.displayName, "defaultMood": payload.defaultMood, "updatedAt": _now(), "updatedBy": user["email"]}}, return_document=True)
    if updated is None:
        raise HTTPException(status_code=404, detail={"error": "character_not_found"})
    return {key: value for key, value in updated.items() if key != "_id"}


@api.delete("/admin/characters/{character_id}", status_code=204)
async def delete_admin_character(character_id: str, request: Request):
    user = await _current_user(request)
    _require_admin(user)
    deleted = await admin_characters.delete_one({"characterId": character_id})
    if not deleted.deleted_count:
        raise HTTPException(status_code=404, detail={"error": "character_not_found"})
    return Response(status_code=204)


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


@api.post("/admin/drafts/sample", status_code=201)
async def create_sample_admin_draft(request: Request):
    """Create a complete testing draft for an allow-listed administrator."""
    user = await _current_user(request)
    _require_admin(user)
    now = _now()
    doc = {
        "draftId": f"draft_{uuid.uuid4().hex}",
        "bookId": "book2",
        "title": "Sample: The Invitation",
        "synopsis": "A complete private sample story for testing manual scene authoring and draft playthroughs at Blackthorn Academy.",
        "branchNotes": "This sample is safe to edit or delete. It demonstrates a complete six-scene route with linked choices and no player-facing publication.",
        "scenes": _sample_story_scenes(),
        "revision": 1,
        "status": "draft",
        "createdAt": now,
        "updatedAt": now,
        "updatedBy": user["email"],
    }
    await admin_drafts.insert_one(doc)
    return _public_admin_draft(doc)


@api.post("/admin/drafts/import-book-json", status_code=201)
async def import_admin_book_json(request: Request, payload: AdminBookJsonImport):
    """Validate a Book JSON file, then create a private editable draft only."""
    user = await _current_user(request)
    _require_admin(user)
    imported = _import_book_json(payload.content)
    now = _now()
    doc = {"draftId": f"draft_{uuid.uuid4().hex}", **imported, "revision": 1, "status": "draft", "importedAt": now, "importedBy": user["email"], "createdAt": now, "updatedAt": now, "updatedBy": user["email"]}
    await admin_drafts.insert_one(doc)
    return _public_admin_draft(doc)


@api.post("/admin/drafts/generate", status_code=201)
async def generate_admin_draft(request: Request, payload: AdminAiDraftRequest):
    """Use OpenRouter to create a private, editable draft for an administrator."""
    user = await _current_user(request)
    _require_admin(user)
    schema = '{"title":"string","synopsis":"string","branchNotes":"string","scenes":[{"sceneId":"id","chapterNumber":1,"title":"string","body":"string","choices":[{"choiceId":"id","text":"string","nextSceneId":"id or null","effectsNotes":"string"}]}]}'
    brief = f"Create a self-contained 3 to 6 scene interactive gothic fantasy romance opening for bookId '{payload.bookId}'. Premise: {payload.premise}\nDesired title: {payload.desiredTitle or 'Choose an evocative original title.'}\nThis is one chapter: every scene must have chapterNumber set to 1. Scenes are branching beats within that single chapter, not separate chapters. Use only scene and choice IDs containing letters, numbers, underscores or hyphens. Every non-null nextSceneId must name a scene in the response. Include choices on most scenes and a terminal final scene. Output exactly this JSON shape: {schema}"
    try:
        generated = AdminGeneratedDraft.model_validate(_normalise_generated_draft(_openrouter_json(brief)))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail={"error": "openrouter_invalid_draft"})
    _validate_manual_scenes(generated.scenes)
    scene_ids = {scene.sceneId for scene in generated.scenes}
    if any(choice.nextSceneId and choice.nextSceneId not in scene_ids for scene in generated.scenes for choice in scene.choices):
        raise HTTPException(status_code=502, detail={"error": "openrouter_invalid_links"})
    now = _now()
    doc = {"draftId": f"draft_{uuid.uuid4().hex}", "bookId": payload.bookId, **generated.model_dump(), "revision": 1, "status": "draft", "createdAt": now, "updatedAt": now, "updatedBy": user["email"]}
    await admin_drafts.insert_one(doc)
    return _public_admin_draft(doc)


@api.put("/admin/drafts/{draft_id}")
async def update_admin_draft(draft_id: str, request: Request, payload: AdminDraftUpdate):
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"draft_[0-9a-f]{32}", draft_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_draft_id"})
    current = await admin_drafts.find_one({"draftId": draft_id}, {"_id": 0})
    if current is None:
        raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
    _validate_manual_scenes([AdminSceneInput.model_validate(scene) for scene in current.get("scenes", [])], payload.storyValues, payload.relationshipValues)
    now = _now()
    changes = payload.model_dump(exclude={"baseRevision"})
    updated = await admin_drafts.find_one_and_update(
        {"draftId": draft_id, "revision": payload.baseRevision, "status": {"$ne": "archived"}},
        {"$set": {**changes, "status": "draft", "updatedAt": now, "updatedBy": user["email"]}, "$unset": {"reviewApproval": ""}, "$inc": {"revision": 1}},
        return_document=True,
    )
    if updated is None:
        return JSONResponse(status_code=409, content={"error": "revision_conflict", "currentDraft": _public_admin_draft(current)})
    return _public_admin_draft(updated)


@api.put("/admin/drafts/{draft_id}/scenes")
async def update_admin_draft_scenes(draft_id: str, request: Request, payload: AdminDraftScenesUpdate):
    """Replace a draft's manual scene list; this does not publish content."""
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"draft_[0-9a-f]{32}", draft_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_draft_id"})
    current = await admin_drafts.find_one({"draftId": draft_id}, {"_id": 0})
    if current is None:
        raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
    _validate_manual_scenes(payload.scenes, current.get("storyValues"), current.get("relationshipValues"))
    now = _now()
    updated = await admin_drafts.find_one_and_update(
        {"draftId": draft_id, "revision": payload.baseRevision, "status": {"$ne": "archived"}},
        {"$set": {"scenes": [scene.model_dump() for scene in payload.scenes], "status": "draft", "updatedAt": now, "updatedBy": user["email"]}, "$unset": {"reviewApproval": ""}, "$inc": {"revision": 1}},
        return_document=True,
    )
    if updated is None:
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
        {"draftId": draft_id, "status": "draft"},
        {"$set": {"status": "ready_for_review", "updatedAt": now, "updatedBy": user["email"]}, "$inc": {"revision": 1}},
        return_document=True,
    )
    if updated is None:
        current = await admin_drafts.find_one({"draftId": draft_id}, {"_id": 0})
        if current is None:
            raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
        return _public_admin_draft(current)
    return _public_admin_draft(updated)


@api.post("/admin/drafts/{draft_id}/approve-release")
async def approve_admin_draft_release_candidate(draft_id: str, request: Request):
    """Record a human approval checkpoint; it cannot publish game content."""
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"draft_[0-9a-f]{32}", draft_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_draft_id"})
    draft = await admin_drafts.find_one({"draftId": draft_id}, {"_id": 0})
    if draft is None:
        raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
    if draft.get("status") != "ready_for_review":
        raise HTTPException(status_code=409, detail={"error": "draft_not_ready_for_approval"})
    issues = _admin_draft_validation_issues(draft)
    if issues:
        raise HTTPException(status_code=422, detail={"error": "draft_not_ready_for_approval", "issues": issues})
    now = _now()
    approval = {"approvedAt": now, "approvedBy": user["email"], "approvedRevision": draft["revision"]}
    approved = await admin_drafts.find_one_and_update(
        {"draftId": draft_id, "revision": draft["revision"], "status": "ready_for_review"},
        {"$set": {"status": "approved_for_release", "reviewApproval": approval, "updatedAt": now, "updatedBy": user["email"]}, "$push": {"reviewHistory": {"$each": [approval], "$slice": -20}}, "$inc": {"revision": 1}},
        return_document=True,
    )
    if approved is None:
        raise HTTPException(status_code=409, detail={"error": "revision_conflict"})
    return _public_admin_draft(approved)


@api.post("/admin/drafts/{draft_id}/archive")
async def archive_admin_draft(draft_id: str, request: Request):
    """Hide a draft from active work without deleting it or publishing it."""
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"draft_[0-9a-f]{32}", draft_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_draft_id"})
    now = _now()
    updated = await admin_drafts.find_one_and_update({"draftId": draft_id, "status": {"$ne": "archived"}}, {"$set": {"status": "archived", "archivedAt": now, "archivedBy": user["email"], "updatedAt": now, "updatedBy": user["email"]}, "$inc": {"revision": 1}}, return_document=True)
    if updated is None:
        current = await admin_drafts.find_one({"draftId": draft_id}, {"_id": 0})
        if current is None:
            raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
        return _public_admin_draft(current)
    return _public_admin_draft(updated)


@api.post("/admin/drafts/{draft_id}/restore")
async def restore_admin_draft(draft_id: str, request: Request):
    """Restore an archived draft to private editable draft status."""
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"draft_[0-9a-f]{32}", draft_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_draft_id"})
    now = _now()
    updated = await admin_drafts.find_one_and_update({"draftId": draft_id, "status": "archived"}, {"$set": {"status": "draft", "updatedAt": now, "updatedBy": user["email"]}, "$unset": {"archivedAt": "", "archivedBy": "", "reviewApproval": ""}, "$inc": {"revision": 1}}, return_document=True)
    if updated is None:
        current = await admin_drafts.find_one({"draftId": draft_id}, {"_id": 0})
        if current is None:
            raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
        return _public_admin_draft(current)
    return _public_admin_draft(updated)


@api.delete("/admin/drafts/{draft_id}", status_code=204)
async def delete_admin_draft(draft_id: str, request: Request):
    """Permanently remove one private draft; never touches published content."""
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"draft_[0-9a-f]{32}", draft_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_draft_id"})
    deleted = await admin_drafts.delete_one({"draftId": draft_id})
    if not deleted.deleted_count:
        raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
    return Response(status_code=204)


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
    issues = _admin_draft_validation_issues(draft)
    return {"draftId": draft_id, "valid": not issues, "issues": issues}


@api.get("/admin/drafts/{draft_id}/review-export")
async def export_admin_draft_for_review(draft_id: str, request: Request):
    """Export a validated review candidate. This endpoint can never publish it."""
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"draft_[0-9a-f]{32}", draft_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_draft_id"})
    draft = await admin_drafts.find_one({"draftId": draft_id}, {"_id": 0})
    if draft is None:
        raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
    if draft.get("status") not in {"ready_for_review", "approved_for_release"}:
        raise HTTPException(status_code=409, detail={"error": "draft_not_ready_for_review"})
    issues = _admin_draft_validation_issues(draft)
    if issues:
        raise HTTPException(status_code=422, detail={"error": "draft_not_ready_for_export", "issues": issues})
    return _review_export(draft)


@api.get("/admin/releases")
async def list_admin_release_versions(request: Request):
    """List frozen release candidates; none are served to players."""
    user = await _current_user(request)
    _require_admin(user)
    docs = await admin_releases.find({}, {"_id": 0, "snapshot": 0}).sort([("bookId", 1), ("version", -1)]).to_list(length=200)
    return {"releases": [_public_admin_release(doc) for doc in docs], "playerFacing": False}


@api.post("/admin/drafts/{draft_id}/release-versions", status_code=201)
async def create_admin_release_version(draft_id: str, request: Request):
    """Freeze an approved draft as an immutable, private release candidate."""
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"draft_[0-9a-f]{32}", draft_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_draft_id"})
    draft = await admin_drafts.find_one({"draftId": draft_id}, {"_id": 0})
    if draft is None:
        raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
    if draft.get("status") != "approved_for_release":
        raise HTTPException(status_code=409, detail={"error": "draft_not_approved_for_release"})
    issues = _admin_draft_validation_issues(draft)
    if issues:
        raise HTTPException(status_code=422, detail={"error": "draft_not_ready_for_release_version", "issues": issues})
    return await _create_release_version(draft, user)


@api.post("/admin/releases/{release_id}/select")
async def select_admin_release_version(release_id: str, request: Request):
    """Select a registry version for later rollout; never changes live content."""
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"release_[0-9a-f]{32}", release_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_release_id"})
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    now = _now()
    await admin_releases.update_many({"bookId": release["bookId"], "status": "selected"}, {"$set": {"status": "prepared"}, "$unset": {"selectedAt": "", "selectedBy": ""}})
    selected = await admin_releases.find_one_and_update(
        {"releaseId": release_id},
        {"$set": {"status": "selected", "selectedAt": now, "selectedBy": user["email"]}},
        return_document=True,
    )
    return _public_admin_release(selected)


@api.post("/admin/releases/{release_id}/rollback")
async def rollback_admin_release_version(release_id: str, request: Request):
    """Re-select a prior immutable candidate in the private registry only."""
    return await select_admin_release_version(release_id, request)


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
