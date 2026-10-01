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
from typing import Any, Dict, List, Optional, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
from pydantic import BaseModel, ConfigDict, Field, field_validator
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
STAGED_RELEASE_PREVIEW_ENABLED = os.environ.get("STAGED_RELEASE_PREVIEW", "").strip().lower() == "true"
BETA_RELEASES_ENABLED = os.environ.get("BETA_RELEASES", "").strip().lower() == "true"
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
staged_preview_sessions = db["staged_preview_sessions"]
beta_release_access = db["beta_release_access"]
beta_player_sessions = db["beta_player_sessions"]
beta_feedback = db["beta_feedback"]
trusted_catalogue_candidates = db["trusted_catalogue_candidates"]
# The live catalogue is a small, database-backed pointer to an immutable
# candidate.  It deliberately does not replace the build-time trusted
# progression registry or mutate any player save documents.
published_catalogue = db["published_catalogue"]

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
    await staged_preview_sessions.create_index("sessionId", unique=True)
    await staged_preview_sessions.create_index("expiresAt", expireAfterSeconds=0)
    await staged_preview_sessions.create_index([("releaseId", 1), ("updatedAt", -1)])
    await beta_release_access.create_index([("releaseId", 1), ("email", 1)], unique=True)
    await beta_player_sessions.create_index([("releaseId", 1), ("userId", 1)], unique=True)
    await beta_player_sessions.create_index([("releaseId", 1), ("updatedAt", -1)])
    await beta_feedback.create_index([("releaseId", 1), ("createdAt", -1)])
    # This audit collection is deliberately separate from the runtime player catalogue.
    await trusted_catalogue_candidates.create_index("releaseId", unique=True)
    await trusted_catalogue_candidates.create_index([("bookId", 1), ("registeredAt", -1)])
    await published_catalogue.create_index("bookId", unique=True)
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


def _safe_oauth_next(value: Optional[str]) -> str:
    """Accept only a same-origin beta return path; never create an open redirect."""
    if not value:
        return ""
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme or parsed.netloc or parsed.path != "/":
        return ""
    beta_book = urllib.parse.parse_qs(parsed.query).get("betaBook", [])
    if len(beta_book) == 1 and re.fullmatch(r"book[1-9][0-9]*", beta_book[0]):
        return f"/?betaBook={urllib.parse.quote(beta_book[0])}"
    return ""


@api.get("/auth/google/start")
async def google_auth_start(next: Optional[str] = None):
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
    safe_next = _safe_oauth_next(next)
    if safe_next:
        response.set_cookie("oauth_next", safe_next, max_age=600, httponly=True, secure=True, samesite="lax", path="/api/auth/google")
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
    response = RedirectResponse(request.cookies.get("oauth_next") or GOOGLE_OAUTH_SUCCESS_URL, status_code=303)
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
    response.delete_cookie("oauth_next", path="/api/auth/google")
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
    playtestValues: Dict[str, int] = Field(default_factory=lambda: {"humanity": 100, "bloodCoins": 250}, max_length=20)

    @field_validator("playtestValues")
    @classmethod
    def _validate_playtest_values(cls, values: Dict[str, int]) -> Dict[str, int]:
        for key, value in values.items():
            if not re.fullmatch(r"^(humanity|bloodCoins|affinity\.[A-Za-z0-9_-]+)$", key) or not isinstance(value, int) or not -10000 <= value <= 10000:
                raise ValueError("invalid_playtest_value")
        return values


class AdminDraftUpdate(AdminDraftInput):
    baseRevision: int = Field(ge=1)


class AdminChoiceInput(BaseModel):
    """One manually-authored route out of a draft scene."""

    model_config = ConfigDict(extra="forbid")
    choiceId: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=300)
    nextSceneId: Optional[str] = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    effectsNotes: str = Field(default="", max_length=1000)
    conditions: List["AdminConditionInput"] = Field(default_factory=list, max_length=6)
    requiredFlags: Dict[str, bool] = Field(default_factory=dict, max_length=12)
    costs: List["AdminEffectInput"] = Field(default_factory=list, max_length=6)
    effects: List["AdminEffectInput"] = Field(default_factory=list, max_length=6)
    setFlags: Dict[str, bool] = Field(default_factory=dict, max_length=12)

    @field_validator("requiredFlags", "setFlags")
    @classmethod
    def _validate_flag_map(cls, values: Dict[str, bool]) -> Dict[str, bool]:
        for key, value in values.items():
            if not re.fullmatch(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$", key) or type(value) is not bool:
                raise ValueError("invalid_story_flag")
        return values


class AdminEffectInput(BaseModel):
    """A bounded, data-only state change for private playtests."""
    model_config = ConfigDict(extra="forbid")
    target: str = Field(pattern=r"^(humanity|bloodCoins|affinity\.[A-Za-z0-9_-]+)$", max_length=100)
    delta: int = Field(ge=-10000, le=10000)


class AdminConditionInput(BaseModel):
    """A numeric gate used only by the private draft playtest."""
    model_config = ConfigDict(extra="forbid")
    target: str = Field(pattern=r"^(humanity|bloodCoins|affinity\.[A-Za-z0-9_-]+)$", max_length=100)
    operator: Literal["gte", "lte", "eq"] = "gte"
    value: int = Field(ge=-10000, le=10000)


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


class StagedPreviewChoiceInput(BaseModel):
    """One optimistic-concurrency choice in an isolated staging session."""
    model_config = ConfigDict(extra="forbid")
    sceneId: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    choiceId: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    baseRevision: int = Field(ge=1)


class BetaAccessUpdate(BaseModel):
    """An explicit allow-list for a signed-in, non-public beta."""
    model_config = ConfigDict(extra="forbid")
    emails: List[str] = Field(default_factory=list, max_length=100)

    @field_validator("emails")
    @classmethod
    def normalise_emails(cls, emails: List[str]) -> List[str]:
        cleaned = sorted({email.strip().lower() for email in emails if isinstance(email, str) and email.strip()})
        if any(not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) for email in cleaned):
            raise ValueError("invalid beta tester email")
        return cleaned


class BetaFeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=3, max_length=2000)


class BetaFeedbackTriageInput(BaseModel):
    """An admin-only review state; beta reports never alter player content."""
    model_config = ConfigDict(extra="forbid")
    status: Literal["open", "resolved"]
    adminNote: str = Field(default="", max_length=2000)


class BetaDecisionInput(BaseModel):
    """A private human release-review record, not a publishing instruction."""
    model_config = ConfigDict(extra="forbid")
    decision: Literal["continue_testing", "ready_for_release_review"]
    note: str = Field(default="", max_length=2000)


class PublicationApprovalInput(BaseModel):
    """Bind a human review approval to the exact immutable release checksum."""
    model_config = ConfigDict(extra="forbid")
    checksum: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    note: str = Field(default="", max_length=2000)


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
            for name, entries in (("condition", choice.conditions), ("cost", choice.costs), ("effect", choice.effects)):
                targets = [entry.target for entry in entries]
                if len(targets) != len(set(targets)):
                    raise HTTPException(status_code=422, detail={"error": f"duplicate_{name}_target", "sceneId": scene.sceneId, "choiceId": choice.choiceId})
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


def _book_two_starter_scenes() -> List[Dict[str, Any]]:
    """A deliberately editable Book II outline, never player-facing content."""
    return [
        {"sceneId": "book2-aftermath", "chapterNumber": 1, "title": "After the Bell", "body": "The final bell at Blackthorn Academy has stopped ringing, but {{player.name}} can still feel it in the bones. Dawn has found the corridors empty—except for the sealed door that was not there last night.\n\nA crimson sigil warms beneath your palm. Someone has left a message for you: *Come alone, and bring what you chose to become.*", "dialogue": [], "choices": [{"choiceId": "open-door", "text": "Break the seal and enter the hidden corridor.", "nextSceneId": "book2-hidden-corridor", "effectsNotes": "Follow the mystery."}, {"choiceId": "find-ally", "text": "Find an ally before you face the message.", "nextSceneId": "book2-ally", "effectsNotes": "Seek support first."}]},
        {"sceneId": "book2-hidden-corridor", "chapterNumber": 1, "title": "The Hidden Corridor", "body": "Behind the door, the academy becomes older. Portraits have been turned to face the wall, and a trail of candlewax leads toward a locked observatory.\n\nInside, a stranger waits beside a map marked with names you recognise.", "dialogue": [], "choices": [{"choiceId": "hear-stranger", "text": "Hear the stranger’s warning.", "nextSceneId": "book2-revelation", "effectsNotes": "Learn the threat."}, {"choiceId": "take-map", "text": "Take the map and leave before the stranger can stop you.", "nextSceneId": "book2-revelation", "effectsNotes": "Keep control of the clue."}]},
        {"sceneId": "book2-ally", "chapterNumber": 1, "title": "An Unsteady Alliance", "body": "Your chosen ally meets you in the abandoned library. Between the shelves, every promise from last term seems to carry a different weight.\n\nTogether, you trace the crimson sigil to a page torn from the academy’s forbidden records.", "dialogue": [], "choices": [{"choiceId": "share-truth", "text": "Share everything you know.", "nextSceneId": "book2-revelation", "effectsNotes": "Strengthen the alliance."}, {"choiceId": "keep-secret", "text": "Keep the most dangerous detail to yourself.", "nextSceneId": "book2-revelation", "effectsNotes": "Protect your secret."}]},
        {"sceneId": "book2-revelation", "chapterNumber": 1, "title": "A New Hunger", "body": "The record names a power beneath Blackthorn Academy—and says it has begun to wake. The message was not an invitation. It was a test.\n\nThis starter chapter ends here. Replace, expand, or branch these scenes before sending the draft to review.", "dialogue": [], "choices": []},
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
        "playtestValues": doc.get("playtestValues", {"humanity": 100, "bloodCoins": 250}),
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
        "stagedAt": doc.get("stagedAt"),
        "stagedBy": doc.get("stagedBy"),
        "betaEnabled": bool(doc.get("betaEnabled")),
        "betaEnabledAt": doc.get("betaEnabledAt"),
        "betaEnabledBy": doc.get("betaEnabledBy"),
        "betaDecision": doc.get("betaDecision"),
        "betaDecisionHistory": doc.get("betaDecisionHistory", []),
        "publicationApproval": doc.get("publicationApproval"),
        "publicationApprovalHistory": doc.get("publicationApprovalHistory", []),
        "catalogueRegistration": doc.get("catalogueRegistration"),
    }


def _staged_preview_session_token(request: Request) -> str:
    token = request.headers.get("x-staged-preview-token", "")
    if not token or len(token) < 32:
        raise HTTPException(status_code=401, detail={"error": "staged_preview_session_required"})
    return token


def _staged_preview_stats(snapshot: Dict[str, Any]) -> Dict[str, int]:
    values = snapshot.get("playtestValues") if isinstance(snapshot.get("playtestValues"), dict) else {}
    return {"humanity": 100, "bloodCoins": 250, **{key: value for key, value in values.items() if isinstance(key, str) and isinstance(value, int)}}


def _staged_condition_passes(stats: Dict[str, int], condition: Dict[str, Any]) -> bool:
    value = stats.get(condition["target"], 0)
    return value >= condition["value"] if condition["operator"] == "gte" else value <= condition["value"] if condition["operator"] == "lte" else value == condition["value"]


def _staged_flags_match(flags: Dict[str, bool], required: Dict[str, Any]) -> bool:
    return all(type(key) is str and type(value) is bool and flags.get(key) == value for key, value in required.items())


def _public_staged_preview_session(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {"sessionId": doc["sessionId"], "bookId": doc["bookId"], "releaseId": doc["releaseId"], "contentVersion": doc["contentVersion"], "sceneId": doc["sceneId"], "stats": doc["stats"], "flags": doc.get("flags", {}), "history": doc.get("history", []), "revision": doc["revision"], "createdAt": doc["createdAt"], "updatedAt": doc["updatedAt"], "expiresAt": doc["expiresAt"], "stagingOnly": True}


def _public_beta_session(doc: Dict[str, Any]) -> Dict[str, Any]:
    """A real signed-in tester session, deliberately separate from account_saves."""
    return {"sessionId": doc["sessionId"], "bookId": doc["bookId"], "releaseId": doc["releaseId"], "contentVersion": doc["contentVersion"], "sceneId": doc["sceneId"], "stats": doc["stats"], "flags": doc.get("flags", {}), "history": doc.get("history", []), "revision": doc["revision"], "createdAt": doc["createdAt"], "updatedAt": doc["updatedAt"], "betaOnly": True}


async def _beta_release_for_user(book_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    if not BETA_RELEASES_ENABLED:
        raise HTTPException(status_code=404, detail={"error": "beta_releases_disabled"})
    if not re.fullmatch(r"book[1-9][0-9]*", book_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_book_id"})
    release = await admin_releases.find_one({"bookId": book_id, "status": "staged", "betaEnabled": True}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "beta_release_not_found"})
    access = await beta_release_access.find_one({"releaseId": release["releaseId"], "email": user["email"].lower()}, {"_id": 0})
    if access is None:
        raise HTTPException(status_code=403, detail={"error": "beta_access_required"})
    return release


def _apply_staged_preview_choice(session: Dict[str, Any], snapshot: Dict[str, Any], scene_id: str, choice_id: str) -> Dict[str, Any]:
    scenes = {scene.get("sceneId"): scene for scene in snapshot.get("scenes", []) if isinstance(scene, dict) and isinstance(scene.get("sceneId"), str)}
    scene = scenes.get(scene_id)
    if scene is None or session.get("sceneId") != scene_id:
        raise HTTPException(status_code=409, detail={"error": "staged_preview_scene_conflict"})
    choice = next((item for item in scene.get("choices", []) if isinstance(item, dict) and item.get("choiceId") == choice_id), None)
    if choice is None:
        raise HTTPException(status_code=422, detail={"error": "staged_preview_choice_not_found"})
    conditions = choice.get("conditions", []) if isinstance(choice.get("conditions"), list) else []
    required_flags = choice.get("requiredFlags", {})
    if not isinstance(required_flags, dict) or not all(isinstance(condition, dict) and _staged_condition_passes(session["stats"], condition) for condition in conditions) or not _staged_flags_match(session.get("flags", {}), required_flags):
        raise HTTPException(status_code=409, detail={"error": "staged_preview_conditions_not_met"})
    stats = dict(session["stats"])
    audit = []
    for kind in ("costs", "effects"):
        for effect in choice.get(kind, []) if isinstance(choice.get(kind), list) else []:
            if not isinstance(effect, dict) or not isinstance(effect.get("target"), str) or not isinstance(effect.get("delta"), int):
                raise HTTPException(status_code=422, detail={"error": "staged_preview_invalid_effect"})
            before = stats.get(effect["target"], 0)
            after = before + effect["delta"]
            if effect["target"] == "humanity":
                after = max(0, min(100, after))
            stats[effect["target"]] = after
            audit.append({"kind": "cost" if kind == "costs" else "effect", "target": effect["target"], "before": before, "delta": effect["delta"], "after": after})
    flags = dict(session.get("flags", {}))
    set_flags = choice.get("setFlags", {})
    if not isinstance(set_flags, dict) or not all(type(key) is str and type(value) is bool for key, value in set_flags.items()):
        raise HTTPException(status_code=422, detail={"error": "staged_preview_invalid_flags"})
    flags.update(set_flags)
    return {"sceneId": choice.get("nextSceneId") or None, "stats": stats, "flags": flags, "event": {"sceneId": scene_id, "choiceId": choice_id, "audit": audit, "flags": set_flags, "at": _now()}}


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


@api.post("/admin/drafts/book-two-starter", status_code=201)
async def create_book_two_starter_admin_draft(request: Request):
    """Create a valid, private Book II production scaffold for an administrator."""
    user = await _current_user(request)
    _require_admin(user)
    now = _now()
    doc = {
        "draftId": f"draft_{uuid.uuid4().hex}",
        "bookId": "book2",
        "title": "A Vampire’s Choice — Book II (working draft)",
        "synopsis": "An editable opening scaffold for Book II: the consequences of Blackthorn Academy’s first term lead to a hidden threat beneath the school.",
        "branchNotes": "Production starter only. Replace the placeholder route with canon prose, character dialogue, effects and meaningful branches before review. This draft never enters player content unless it completes the normal review, beta and controlled release workflow.",
        "storyValues": {},
        "relationshipValues": {},
        "playtestValues": {"humanity": 100, "bloodCoins": 250},
        "scenes": _book_two_starter_scenes(),
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


@api.get("/admin/drafts/{draft_id}/publish-readiness")
async def get_admin_draft_publish_readiness(draft_id: str, request: Request):
    """One consolidated, read-only release view for the author workflow."""
    user = await _current_user(request)
    _require_admin(user)
    draft = await admin_drafts.find_one({"draftId": draft_id}, {"_id": 0})
    if draft is None:
        raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
    issues = _admin_draft_validation_issues(draft)
    approval = draft.get("reviewApproval") if draft.get("status") == "approved_for_release" else None
    release = await admin_releases.find_one({"source.draftId": draft_id, "source.approvedRevision": approval.get("approvedRevision") if isinstance(approval, dict) else None}, {"_id": 0}) if approval else None
    candidate = await trusted_catalogue_candidates.find_one({"releaseId": release["releaseId"]}, {"_id": 0, "playerBundleCandidate": 0, "trustedContract": 0}) if release else None
    blockers = [{"code": item.get("code", "draft_validation"), "message": item.get("message", "Draft needs attention.")} for item in issues]
    if not approval:
        blockers.append({"code": "editorial_approval_required", "message": "Approve the current draft revision before preparing publication."})
    compatibility = None
    if release and release.get("publicationApproval"):
        compatibility = await inspect_admin_trusted_content_compatibility(release["releaseId"], request)
        blockers.extend({"code": item["code"], "message": item["message"]} for item in compatibility["issues"] if item["severity"] == "blocking")
    preflight = await inspect_admin_catalogue_activation_preflight(candidate["candidateId"], request) if candidate else None
    scene_count = len(draft.get("scenes", []))
    choice_count = sum(len(scene.get("choices", [])) for scene in draft.get("scenes", []) if isinstance(scene, dict))
    prepared = bool(candidate and candidate.get("status") == "registered")
    return {
        "format": "vampires-choice-publish-readiness/v1", "draftId": draft_id, "bookId": draft["bookId"], "title": draft["title"], "revision": draft["revision"],
        "status": "ready_to_publish" if prepared and not blockers else "approved" if approval and not blockers else "needs_attention" if issues else "ready_for_approval",
        "summary": {"sceneCount": scene_count, "choiceCount": choice_count, "graphPassed": not any(item["code"] in {"unknown_scene_target", "unreachable_scenes", "no_terminal_scene", "non_terminating_route"} for item in issues), "tokensPassed": not any("token" in item["code"] for item in issues), "mechanicsPassed": not any("effect" in item["code"] or "condition" in item["code"] for item in issues)},
        "editorialApproval": approval, "release": _public_admin_release(release) if release else None, "compatibility": compatibility, "candidate": candidate, "activationPreflight": preflight,
        "blockers": list({item["code"]: item for item in blockers}.values()), "recommendedAction": "publish_confirmation" if prepared and not blockers else "prepare_publication" if approval and not issues else "approve_for_publication" if not issues else "fix_draft",
        "playerFacing": False, "published": False,
    }


@api.post("/admin/drafts/{draft_id}/prepare-publication")
async def prepare_admin_draft_publication(draft_id: str, request: Request):
    """Idempotently orchestrate safe, non-player-facing release preparation.

    This deliberately stops at a registered rollout candidate. The final
    player-facing runtime activation remains a separate explicit operation.
    """
    user = await _current_user(request)
    _require_admin(user)
    draft = await admin_drafts.find_one({"draftId": draft_id}, {"_id": 0})
    if draft is None:
        raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
    if draft.get("status") != "approved_for_release" or not isinstance(draft.get("reviewApproval"), dict):
        raise HTTPException(status_code=409, detail={"error": "draft_not_approved_for_release"})
    issues = _admin_draft_validation_issues(draft)
    if issues:
        raise HTTPException(status_code=422, detail={"error": "draft_not_ready_for_publication", "issues": issues})
    approved_revision = draft["reviewApproval"]["approvedRevision"]
    release = await admin_releases.find_one({"source.draftId": draft_id, "source.approvedRevision": approved_revision}, {"_id": 0})
    if release is None:
        created = await _create_release_version(draft, user)
        release = await admin_releases.find_one({"releaseId": created["releaseId"]}, {"_id": 0})
    if release.get("status") != "staged":
        now = _now()
        await admin_releases.update_many({"bookId": release["bookId"], "status": "selected"}, {"$set": {"status": "prepared"}, "$unset": {"selectedAt": "", "selectedBy": ""}})
        await admin_releases.update_one({"releaseId": release["releaseId"]}, {"$set": {"status": "selected", "selectedAt": now, "selectedBy": user["email"]}})
        if STAGED_RELEASE_PREVIEW_ENABLED:
            await admin_releases.update_many({"bookId": release["bookId"], "status": "staged", "releaseId": {"$ne": release["releaseId"]}}, {"$set": {"status": "prepared"}, "$unset": {"stagedAt": "", "stagedBy": ""}})
            await admin_releases.update_one({"releaseId": release["releaseId"]}, {"$set": {"status": "staged", "stagedAt": now, "stagedBy": user["email"]}})
    release = await admin_releases.find_one({"releaseId": release["releaseId"]}, {"_id": 0})
    if not isinstance(release.get("publicationApproval"), dict) or release["publicationApproval"].get("checksum") != release["manifest"]["sha256"]:
        signoff = {"checksum": release["manifest"]["sha256"], "version": release["version"], "note": "Editorial approval carried from the approved draft revision.", "approvedAt": _now(), "approvedBy": user["email"], "playerFacing": False, "published": False, "workflow": "simplified_publish"}
        await admin_releases.update_one({"releaseId": release["releaseId"]}, {"$set": {"publicationApproval": signoff}, "$push": {"publicationApprovalHistory": {"$each": [signoff], "$slice": -20}}})
    registration = await register_admin_catalogue_candidate(release["releaseId"], request)
    readiness = await get_admin_draft_publish_readiness(draft_id, request)
    return {"release": _public_admin_release(release), "candidate": registration["candidate"], "readiness": readiness, "playerFacing": False, "published": False, "note": "Preparation completed safely. No player content or player save was changed; a final live-publication activation remains explicit."}


@api.get("/admin/releases")
async def list_admin_release_versions(request: Request):
    """List frozen release candidates; none are served to players."""
    user = await _current_user(request)
    _require_admin(user)
    docs = await admin_releases.find({}, {"_id": 0, "snapshot": 0}).sort([("bookId", 1), ("version", -1)]).to_list(length=200)
    return {"releases": [_public_admin_release(doc) for doc in docs], "playerFacing": False}


@api.get("/admin/releases/{release_id}")
async def get_admin_release_version(release_id: str, request: Request):
    """Return one frozen snapshot for human review; never for player playback."""
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"release_[0-9a-f]{32}", release_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_release_id"})
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    return {**_public_admin_release(release), "snapshot": release["snapshot"], "playerFacing": False, "published": False}


@api.get("/staged-releases/{book_id}")
async def get_staged_release_preview(book_id: str):
    """Read-only staging preview of one frozen version.

    This is intentionally off unless ``STAGED_RELEASE_PREVIEW=true`` is set in
    a staging/preview environment. It returns immutable content only and has
    no save, progression, or production-publishing side effect.
    """
    if not STAGED_RELEASE_PREVIEW_ENABLED:
        raise HTTPException(status_code=404, detail={"error": "staged_release_preview_disabled"})
    if not re.fullmatch(r"book[1-9][0-9]*", book_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_book_id"})
    release = await admin_releases.find_one({"bookId": book_id, "status": "staged"}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "staged_release_not_found"})
    return {
        "format": "vampires-choice-staged-release/v1",
        "environment": "staging-preview",
        "playerFacing": True,
        "published": False,
        "release": _public_admin_release(release),
        "snapshot": release["snapshot"],
        "note": "Read-only staging preview. This endpoint does not read or write player saves.",
    }


@api.post("/staged-releases/{book_id}/sessions", status_code=201)
async def create_staged_release_preview_session(book_id: str):
    """Start an isolated, version-pinned staging progression session."""
    if not STAGED_RELEASE_PREVIEW_ENABLED:
        raise HTTPException(status_code=404, detail={"error": "staged_release_preview_disabled"})
    release = await admin_releases.find_one({"bookId": book_id, "status": "staged"}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "staged_release_not_found"})
    snapshot = release["snapshot"]
    scenes = [scene for scene in snapshot.get("scenes", []) if isinstance(scene, dict) and scene.get("sceneId")]
    if not scenes:
        raise HTTPException(status_code=422, detail={"error": "staged_release_has_no_scenes"})
    opening = min(scenes, key=lambda scene: (int(scene.get("chapterNumber", 1)), scene["sceneId"]))["sceneId"]
    now = _now()
    token = secrets.token_urlsafe(32)
    doc = {"sessionId": f"stage_{uuid.uuid4().hex}", "tokenHash": hashlib.sha256(token.encode()).hexdigest(), "releaseId": release["releaseId"], "bookId": book_id, "contentVersion": release["version"], "sceneId": opening, "stats": _staged_preview_stats(snapshot), "flags": {}, "history": [], "revision": 1, "createdAt": now, "updatedAt": now, "expiresAt": datetime.now(timezone.utc) + timedelta(days=7)}
    await staged_preview_sessions.insert_one(doc)
    return {**_public_staged_preview_session(doc), "sessionToken": token}


@api.get("/staged-preview-sessions/{session_id}")
async def get_staged_release_preview_session(session_id: str, request: Request):
    token = _staged_preview_session_token(request)
    doc = await staged_preview_sessions.find_one({"sessionId": session_id, "tokenHash": hashlib.sha256(token.encode()).hexdigest()}, {"_id": 0, "tokenHash": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail={"error": "staged_preview_session_not_found"})
    return _public_staged_preview_session(doc)


@api.post("/staged-preview-sessions/{session_id}/choices")
async def choose_staged_release_preview_session(session_id: str, request: Request, payload: StagedPreviewChoiceInput):
    token = _staged_preview_session_token(request)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = await staged_preview_sessions.find_one({"sessionId": session_id, "tokenHash": token_hash}, {"_id": 0})
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "staged_preview_session_not_found"})
    if session["revision"] != payload.baseRevision:
        raise HTTPException(status_code=409, detail={"error": "staged_preview_revision_conflict", "session": _public_staged_preview_session(session)})
    release = await admin_releases.find_one({"releaseId": session["releaseId"]}, {"_id": 0, "snapshot": 1})
    if release is None:
        raise HTTPException(status_code=409, detail={"error": "staged_preview_release_missing"})
    updated = _apply_staged_preview_choice(session, release["snapshot"], payload.sceneId, payload.choiceId)
    now = _now()
    next_session = await staged_preview_sessions.find_one_and_update({"sessionId": session_id, "tokenHash": token_hash, "revision": payload.baseRevision}, {"$set": {"sceneId": updated["sceneId"], "stats": updated["stats"], "flags": updated["flags"], "updatedAt": now}, "$push": {"history": {"$each": [updated["event"]], "$slice": -200}}, "$inc": {"revision": 1}}, return_document=True)
    if next_session is None:
        raise HTTPException(status_code=409, detail={"error": "staged_preview_revision_conflict"})
    return _public_staged_preview_session(next_session)


@api.post("/staged-preview-sessions/{session_id}/restart")
async def restart_staged_release_preview_session(session_id: str, request: Request):
    token = _staged_preview_session_token(request)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = await staged_preview_sessions.find_one({"sessionId": session_id, "tokenHash": token_hash}, {"_id": 0})
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "staged_preview_session_not_found"})
    release = await admin_releases.find_one({"releaseId": session["releaseId"]}, {"_id": 0, "snapshot": 1})
    if release is None:
        raise HTTPException(status_code=409, detail={"error": "staged_preview_release_missing"})
    scenes = [scene for scene in release["snapshot"].get("scenes", []) if isinstance(scene, dict) and scene.get("sceneId")]
    opening = min(scenes, key=lambda scene: (int(scene.get("chapterNumber", 1)), scene["sceneId"]))["sceneId"]
    updated = await staged_preview_sessions.find_one_and_update({"sessionId": session_id, "tokenHash": token_hash}, {"$set": {"sceneId": opening, "stats": _staged_preview_stats(release["snapshot"]), "flags": {}, "history": [], "updatedAt": _now()}, "$inc": {"revision": 1}}, return_document=True)
    return _public_staged_preview_session(updated)


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


@api.post("/admin/releases/{release_id}/stage")
async def stage_admin_release_version(release_id: str, request: Request):
    """Promote a selected immutable version to the flag-gated staging preview."""
    user = await _current_user(request)
    _require_admin(user)
    if not STAGED_RELEASE_PREVIEW_ENABLED:
        raise HTTPException(status_code=409, detail={"error": "staged_release_preview_disabled"})
    if not re.fullmatch(r"release_[0-9a-f]{32}", release_id):
        raise HTTPException(status_code=400, detail={"error": "invalid_release_id"})
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    if release.get("status") not in {"selected", "staged"}:
        raise HTTPException(status_code=409, detail={"error": "release_not_selected"})
    now = _now()
    await admin_releases.update_many({"bookId": release["bookId"], "status": "staged"}, {"$set": {"status": "prepared"}, "$unset": {"stagedAt": "", "stagedBy": ""}})
    staged = await admin_releases.find_one_and_update(
        {"releaseId": release_id},
        {"$set": {"status": "staged", "stagedAt": now, "stagedBy": user["email"]}},
        return_document=True,
    )
    return _public_admin_release(staged)


@api.get("/admin/releases/{release_id}/staging-readiness")
async def get_admin_staged_release_readiness(release_id: str, request: Request):
    """Show staging-only activity without exposing player or production saves."""
    user = await _current_user(request)
    _require_admin(user)
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    session_count = await staged_preview_sessions.count_documents({"releaseId": release_id})
    completed_count = await staged_preview_sessions.count_documents({"releaseId": release_id, "sceneId": None})
    return {"releaseId": release_id, "bookId": release["bookId"], "version": release["version"], "staged": release.get("status") == "staged", "featureEnabled": STAGED_RELEASE_PREVIEW_ENABLED, "sessionCount": session_count, "completedSessionCount": completed_count, "playerSavesTouched": 0, "productionPublished": False}


@api.get("/admin/releases/{release_id}/beta-readiness")
async def get_admin_beta_readiness(release_id: str, request: Request):
    """Report on a limited beta without exposing participants' personal data."""
    user = await _current_user(request)
    _require_admin(user)
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    invited = await beta_release_access.count_documents({"releaseId": release_id})
    sessions_count = await beta_player_sessions.count_documents({"releaseId": release_id})
    completed = await beta_player_sessions.count_documents({"releaseId": release_id, "sceneId": None})
    feedback_count = await beta_feedback.count_documents({"releaseId": release_id})
    resolved_count = await beta_feedback.count_documents({"releaseId": release_id, "status": "resolved"})
    open_count = feedback_count - resolved_count
    return {"releaseId": release_id, "bookId": release["bookId"], "version": release["version"], "enabled": bool(release.get("betaEnabled")), "featureEnabled": BETA_RELEASES_ENABLED, "invitedCount": invited, "sessionCount": sessions_count, "completedSessionCount": completed, "feedbackCount": feedback_count, "openFeedbackCount": open_count, "resolvedFeedbackCount": resolved_count, "readyForDecision": bool(release.get("betaEnabled")) and sessions_count > 0 and open_count == 0, "decision": release.get("betaDecision"), "accountSavesTouched": 0, "productionPublished": False}


@api.get("/admin/releases/{release_id}/beta-access")
async def get_admin_beta_access(release_id: str, request: Request):
    """Return the saved allow-list to an administrator only."""
    user = await _current_user(request)
    _require_admin(user)
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0, "releaseId": 1})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    access = await beta_release_access.find({"releaseId": release_id}, {"_id": 0, "email": 1}).sort("email", 1).to_list(length=100)
    return {"releaseId": release_id, "emails": [item["email"] for item in access]}


@api.get("/admin/releases/{release_id}/beta-feedback")
async def get_admin_beta_feedback(release_id: str, request: Request):
    """Review beta feedback without exposing account-save or user-id records."""
    user = await _current_user(request)
    _require_admin(user)
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0, "releaseId": 1})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    docs = await beta_feedback.find({"releaseId": release_id}, {"_id": 0, "feedbackId": 1, "sessionId": 1, "testerEmail": 1, "message": 1, "createdAt": 1, "status": 1, "adminNote": 1, "resolvedAt": 1, "resolvedBy": 1}).sort("createdAt", -1).to_list(length=200)
    return {"releaseId": release_id, "feedback": [{"feedbackId": item["feedbackId"], "sessionId": item["sessionId"], "testerEmail": item.get("testerEmail", "Tester"), "message": item["message"], "createdAt": item["createdAt"], "status": item.get("status", "open"), "adminNote": item.get("adminNote", ""), "resolvedAt": item.get("resolvedAt"), "resolvedBy": item.get("resolvedBy")} for item in docs]}


@api.get("/admin/releases/{release_id}/beta-report")
async def export_admin_beta_report(release_id: str, request: Request):
    """A private, portable beta-review hand-off. It cannot promote content."""
    user = await _current_user(request)
    _require_admin(user)
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0, "snapshot": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    invited_count = await beta_release_access.count_documents({"releaseId": release_id})
    session_count = await beta_player_sessions.count_documents({"releaseId": release_id})
    completed_count = await beta_player_sessions.count_documents({"releaseId": release_id, "sceneId": None})
    feedback_docs = await beta_feedback.find({"releaseId": release_id}, {"_id": 0, "feedbackId": 1, "testerEmail": 1, "message": 1, "createdAt": 1, "status": 1, "adminNote": 1, "resolvedAt": 1}).sort("createdAt", -1).to_list(length=200)
    feedback_items = [{"feedbackId": item["feedbackId"], "testerEmail": item.get("testerEmail", "Tester"), "message": item["message"], "createdAt": item["createdAt"], "status": item.get("status", "open"), "adminNote": item.get("adminNote", ""), "resolvedAt": item.get("resolvedAt")} for item in feedback_docs]
    resolved_count = sum(1 for item in feedback_items if item["status"] == "resolved")
    open_count = len(feedback_items) - resolved_count
    return {
        "format": "vampires-choice-private-beta-report/v1",
        "exportedAt": _now(),
        "release": _public_admin_release(release),
        "summary": {"enabled": bool(release.get("betaEnabled")), "invitedCount": invited_count, "sessionCount": session_count, "completedSessionCount": completed_count, "feedbackCount": len(feedback_items), "openFeedbackCount": open_count, "resolvedFeedbackCount": resolved_count, "readyForReleaseReview": bool(release.get("betaEnabled")) and session_count > 0 and open_count == 0, "decision": release.get("betaDecision")},
        "feedback": feedback_items,
        "publication": {"playerFacing": False, "published": False, "note": "This report records private beta evidence only. It cannot publish or change player content."},
    }


@api.get("/admin/releases/{release_id}/beta-route-analytics")
async def get_admin_beta_route_analytics(release_id: str, request: Request):
    """Return aggregate, private beta route signals without exposing testers."""
    user = await _current_user(request)
    _require_admin(user)
    release_doc = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0, "releaseId": 1, "bookId": 1, "version": 1, "snapshot": 1})
    if release_doc is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    release = {key: release_doc[key] for key in ("releaseId", "bookId", "version")}
    scene_labels = {scene.get("sceneId"): scene.get("title", scene.get("sceneId")) for scene in release_doc.get("snapshot", {}).get("scenes", []) if isinstance(scene, dict) and isinstance(scene.get("sceneId"), str)}
    choice_labels = {(scene.get("sceneId"), choice.get("choiceId")): choice.get("text", choice.get("choiceId")) for scene in release_doc.get("snapshot", {}).get("scenes", []) if isinstance(scene, dict) and isinstance(scene.get("sceneId"), str) for choice in scene.get("choices", []) if isinstance(choice, dict) and isinstance(choice.get("choiceId"), str)}
    sessions = await beta_player_sessions.find({"releaseId": release_id}, {"_id": 0, "sceneId": 1, "history": 1}).to_list(length=1000)
    choices: Dict[tuple[str, str], int] = {}
    current_scenes: Dict[str, int] = {}
    completed = 0
    for session in sessions:
        scene_id = session.get("sceneId")
        if scene_id is None:
            completed += 1
        elif isinstance(scene_id, str):
            current_scenes[scene_id] = current_scenes.get(scene_id, 0) + 1
        for event in session.get("history", []):
            if not isinstance(event, dict):
                continue
            from_scene, choice_id = event.get("sceneId"), event.get("choiceId")
            if isinstance(from_scene, str) and isinstance(choice_id, str):
                key = (from_scene, choice_id)
                choices[key] = choices.get(key, 0) + 1
    return {"format": "vampires-choice-private-beta-route-analytics/v1", "generatedAt": _now(), "release": release, "summary": {"sessionCount": len(sessions), "completedSessionCount": completed, "activeSessionCount": len(sessions) - completed, "choiceEventCount": sum(choices.values())}, "topChoices": [{"sceneId": scene_id, "sceneTitle": scene_labels.get(scene_id, scene_id), "choiceId": choice_id, "choiceText": choice_labels.get((scene_id, choice_id), choice_id), "count": count} for (scene_id, choice_id), count in sorted(choices.items(), key=lambda entry: (-entry[1], entry[0]))[:100]], "currentScenes": [{"sceneId": scene_id, "sceneTitle": scene_labels.get(scene_id, scene_id), "count": count} for scene_id, count in sorted(current_scenes.items(), key=lambda entry: (-entry[1], entry[0]))[:100]], "privacy": {"testerIdentitiesIncluded": False, "playerSavesTouched": 0, "published": False}, "note": "Aggregate private-beta telemetry for editorial review only. It cannot publish or alter player progress."}


@api.patch("/admin/releases/{release_id}/beta-feedback/{feedback_id}")
async def triage_admin_beta_feedback(release_id: str, feedback_id: str, request: Request, payload: BetaFeedbackTriageInput):
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"release_[A-Za-z0-9]+", release_id) or not re.fullmatch(r"feedback_[A-Za-z0-9]+", feedback_id):
        raise HTTPException(status_code=404, detail={"error": "beta_feedback_not_found"})
    feedback = await beta_feedback.find_one({"releaseId": release_id, "feedbackId": feedback_id}, {"_id": 0})
    if feedback is None:
        raise HTTPException(status_code=404, detail={"error": "beta_feedback_not_found"})
    now = _now()
    changes = {"status": payload.status, "adminNote": payload.adminNote.strip(), "reviewedAt": now, "reviewedBy": user["email"]}
    if payload.status == "resolved":
        changes.update({"resolvedAt": now, "resolvedBy": user["email"]})
        unset = {}
    else:
        unset = {"resolvedAt": "", "resolvedBy": ""}
    updated = await beta_feedback.find_one_and_update({"releaseId": release_id, "feedbackId": feedback_id}, {"$set": changes, "$unset": unset}, return_document=True)
    return {"feedbackId": updated["feedbackId"], "sessionId": updated["sessionId"], "testerEmail": updated.get("testerEmail", "Tester"), "message": updated["message"], "createdAt": updated["createdAt"], "status": updated.get("status", "open"), "adminNote": updated.get("adminNote", ""), "resolvedAt": updated.get("resolvedAt"), "resolvedBy": updated.get("resolvedBy")}


@api.put("/admin/releases/{release_id}/beta-decision")
async def record_admin_beta_decision(release_id: str, request: Request, payload: BetaDecisionInput):
    """Record a private release-review decision. This endpoint never publishes."""
    user = await _current_user(request)
    _require_admin(user)
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    if release.get("status") != "staged" or not release.get("betaEnabled"):
        raise HTTPException(status_code=409, detail={"error": "beta_release_not_active"})
    open_count = await beta_feedback.count_documents({"releaseId": release_id, "status": {"$ne": "resolved"}})
    if payload.decision == "ready_for_release_review" and open_count:
        raise HTTPException(status_code=409, detail={"error": "beta_feedback_open", "openFeedbackCount": open_count})
    decision = {"decision": payload.decision, "note": payload.note.strip(), "decidedAt": _now(), "decidedBy": user["email"], "openFeedbackCount": open_count, "playerFacing": False, "published": False}
    await admin_releases.update_one({"releaseId": release_id}, {"$set": {"betaDecision": decision}, "$push": {"betaDecisionHistory": {"$each": [decision], "$slice": -20}}, "$unset": {"publicationApproval": "", "catalogueRegistration": ""}})
    await _invalidate_catalogue_registration(release_id, "beta_decision_changed", user["email"])
    return {"releaseId": release_id, "decision": decision, "productionPublished": False}


@api.post("/admin/releases/{release_id}/publication-approval")
async def approve_admin_publication_review(release_id: str, request: Request, payload: PublicationApprovalInput):
    """Create a checksum-bound release sign-off; this endpoint never publishes."""
    user = await _current_user(request)
    _require_admin(user)
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    if release.get("status") != "staged" or not release.get("betaEnabled"):
        raise HTTPException(status_code=409, detail={"error": "beta_release_not_active"})
    if payload.checksum != release["manifest"]["sha256"]:
        raise HTTPException(status_code=409, detail={"error": "release_checksum_mismatch"})
    if release.get("betaDecision", {}).get("decision") != "ready_for_release_review":
        raise HTTPException(status_code=409, detail={"error": "beta_decision_not_ready"})
    if await beta_feedback.count_documents({"releaseId": release_id, "status": {"$ne": "resolved"}}):
        raise HTTPException(status_code=409, detail={"error": "beta_feedback_open"})
    approval = {"checksum": payload.checksum, "version": release["version"], "note": payload.note.strip(), "approvedAt": _now(), "approvedBy": user["email"], "playerFacing": False, "published": False}
    await admin_releases.update_one({"releaseId": release_id}, {"$set": {"publicationApproval": approval}, "$push": {"publicationApprovalHistory": {"$each": [approval], "$slice": -20}}})
    return {"releaseId": release_id, "approval": approval, "productionPublished": False}


@api.get("/admin/releases/{release_id}/publication-handoff")
async def export_admin_publication_handoff(release_id: str, request: Request):
    """Export the approved immutable snapshot for a separately authorised engine integration."""
    user = await _current_user(request)
    _require_admin(user)
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    approval = release.get("publicationApproval")
    if not isinstance(approval, dict) or approval.get("checksum") != release["manifest"]["sha256"]:
        raise HTTPException(status_code=409, detail={"error": "publication_review_not_approved"})
    return {
        "format": "vampires-choice-controlled-publication-handoff/v1",
        "exportedAt": _now(),
        "release": _public_admin_release(release),
        "snapshot": release["snapshot"],
        "compatibility": {
            "sourceFormat": "vampires-choice-admin-release/v1",
            "targetFormat": "vampires-choice-trusted-content-registry/v1",
            "requiresTrustedContentConversion": True,
            "checksum": release["manifest"]["sha256"],
            "note": "A separately authorised deployment must validate and convert this snapshot before adding it to the trusted player-content registry.",
        },
        "publication": {"playerFacing": False, "published": False, "note": "This hand-off is a controlled release artifact only. Downloading it cannot publish or modify player content."},
    }


@api.get("/admin/releases/{release_id}/trusted-content-compatibility")
async def inspect_admin_trusted_content_compatibility(release_id: str, request: Request):
    """Inspect an approved hand-off against the current trusted reducer contract.

    This is deliberately a read-only report. It does not alter the bundled
    registry or make a release playable by normal accounts.
    """
    user = await _current_user(request)
    _require_admin(user)
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    approval = release.get("publicationApproval")
    if not isinstance(approval, dict) or approval.get("checksum") != release["manifest"]["sha256"]:
        raise HTTPException(status_code=409, detail={"error": "publication_review_not_approved"})
    issues: List[Dict[str, Any]] = [{"severity": "required", "code": "narrative_bundle_conversion", "message": "Convert scene titles, bodies, dialogue, and choice text into the player narrative bundle before launch."}]
    supported_effects = 0
    unsupported_effects = 0
    for scene in release["snapshot"].get("scenes", []):
        scene_id = scene.get("sceneId", "unknown") if isinstance(scene, dict) else "unknown"
        if not isinstance(scene, dict):
            issues.append({"severity": "blocking", "code": "invalid_scene", "sceneId": scene_id, "message": "A release scene is not a valid object."})
            continue
        for choice in scene.get("choices", []):
            if not isinstance(choice, dict):
                issues.append({"severity": "blocking", "code": "invalid_choice", "sceneId": scene_id, "message": "A scene contains an invalid choice."})
                continue
            choice_id = choice.get("choiceId", "unknown")
            if choice.get("conditions"):
                issues.append({"severity": "required", "code": "conditions_need_conversion", "sceneId": scene_id, "choiceId": choice_id, "message": "Convert private-draft conditions to the trusted numeric condition contract."})
            if choice.get("requiredFlags"):
                supported_effects += len(choice["requiredFlags"])
                issues.append({"severity": "required", "code": "flags_need_conversion", "sceneId": scene_id, "choiceId": choice_id, "message": "Convert private-draft story flags to the trusted flag condition contract."})
            if choice.get("setFlags"):
                supported_effects += len(choice["setFlags"])
            if not choice.get("nextSceneId"):
                issues.append({"severity": "blocking", "code": "terminal_route_needs_entrypoint", "sceneId": scene_id, "choiceId": choice_id, "message": "Terminal choices need a trusted terminal scene or explicit completion contract."})
            for effect in [*(choice.get("costs") or []), *(choice.get("effects") or [])]:
                if not isinstance(effect, dict):
                    issues.append({"severity": "blocking", "code": "invalid_effect", "sceneId": scene_id, "choiceId": choice_id, "message": "A choice contains an invalid effect."})
                    continue
                target = effect.get("target", "")
                if target in {"bloodCoins", "humanity"} or (isinstance(target, str) and target.startswith("affinity.")):
                    supported_effects += 1
                else:
                    unsupported_effects += 1
                    issues.append({"severity": "blocking", "code": "unsupported_trusted_effect", "sceneId": scene_id, "choiceId": choice_id, "target": target, "message": f"{target or 'Unknown'} is not represented by the current trusted reducer; add a server-authoritative rule before launch."})
    blockers = sum(1 for issue in issues if issue["severity"] == "blocking")
    return {"format": "vampires-choice-trusted-content-compatibility/v1", "checkedAt": _now(), "releaseId": release_id, "checksum": release["manifest"]["sha256"], "summary": {"blockingIssueCount": blockers, "requiredWorkCount": len(issues) - blockers, "supportedEffectCount": supported_effects, "unsupportedEffectCount": unsupported_effects, "eligibleForTrustedConversion": blockers == 0}, "supportedMappings": {"bloodCoins": "effects.coinsChange", "humanity": "effects.humanityChange", "affinity.<characterId>": "effects.relationshipChanges", "numeric conditions": "condition: [{target, operator, value}]", "story flags": "effects.setFlags / condition.requiredFlags"}, "issues": issues, "publication": {"playerFacing": False, "published": False, "note": "Validation only. The trusted registry and player catalogue remain unchanged."}}


@api.get("/admin/releases/{release_id}/narrative-conversion-preview")
async def preview_admin_narrative_conversion(release_id: str, request: Request):
    """Build a portable candidate from an approved draft without registering it.

    The standard player bundle retains narrative text and supported browser
    effects. Its ``trustedContract`` carries the server-authoritative humanity
    and condition data for the later, explicit engine integration step.
    """
    user = await _current_user(request)
    _require_admin(user)
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    approval = release.get("publicationApproval")
    if not isinstance(approval, dict) or approval.get("checksum") != release["manifest"]["sha256"]:
        raise HTTPException(status_code=409, detail={"error": "publication_review_not_approved"})
    snapshot = release["snapshot"]
    source_scenes = [scene for scene in snapshot.get("scenes", []) if isinstance(scene, dict)]
    if not source_scenes:
        raise HTTPException(status_code=422, detail={"error": "release_has_no_scenes"})
    ordered = sorted(source_scenes, key=lambda scene: (int(scene.get("chapterNumber", 1)), scene.get("sceneId", "")))
    chapter_scenes: Dict[int, List[Dict[str, Any]]] = {}
    for scene in ordered:
        chapter_scenes.setdefault(int(scene.get("chapterNumber", 1)), []).append(scene)
    converted_scenes, trusted_choices, warnings = [], {}, ["This is a conversion preview. It is not registered in the player content loader or trusted registry."]
    for chapter, scenes in chapter_scenes.items():
        for index, scene in enumerate(scenes, start=1):
            choices = []
            for choice in scene.get("choices", []):
                if not isinstance(choice, dict):
                    continue
                browser_effects: Dict[str, Any] = {}
                relationships: Dict[str, int] = {}
                coins_change = 0
                humanity_change = 0
                for effect in [*(choice.get("costs") or []), *(choice.get("effects") or [])]:
                    if not isinstance(effect, dict) or type(effect.get("delta")) is not int:
                        continue
                    target, delta = effect.get("target"), effect["delta"]
                    if target == "bloodCoins":
                        coins_change += delta
                    elif target == "humanity":
                        humanity_change += delta
                    elif isinstance(target, str) and target.startswith("affinity."):
                        character_id = target.removeprefix("affinity.")
                        relationships[character_id] = relationships.get(character_id, 0) + delta
                if coins_change:
                    browser_effects["coinsChange"] = coins_change
                if relationships:
                    browser_effects["relationshipChanges"] = relationships
                if choice.get("setFlags"):
                    browser_effects["setFlags"] = choice["setFlags"]
                choice_id = choice.get("choiceId", "")
                conditions = choice.get("conditions") or []
                if humanity_change:
                    browser_effects["humanityChange"] = humanity_change
                browser_condition: Dict[str, Any] = {}
                relationship_conditions: Dict[str, Dict[str, int]] = {}
                for condition in conditions:
                    if not isinstance(condition, dict):
                        continue
                    target, operator, value = condition.get("target"), condition.get("operator"), condition.get("value")
                    if type(value) is not int or operator not in {"gte", "lte"}:
                        continue
                    if target == "humanity":
                        browser_condition["minHumanity" if operator == "gte" else "maxHumanity"] = value
                    elif target == "bloodCoins":
                        browser_condition["minCoins" if operator == "gte" else "maxCoins"] = value
                    elif isinstance(target, str) and target.startswith("affinity."):
                        character_id = target.removeprefix("affinity.")
                        relationship_conditions.setdefault(character_id, {})["min" if operator == "gte" else "max"] = value
                if relationship_conditions:
                    browser_condition["relationships"] = [{"characterId": character_id, **bounds} for character_id, bounds in relationship_conditions.items()]
                if choice.get("requiredFlags"):
                    browser_condition["requiredFlags"] = choice["requiredFlags"]
                trusted_choices[f"{scene.get('sceneId')}:{choice_id}"] = {"conditions": conditions, "requiredFlags": choice.get("requiredFlags") or {}, "setFlags": choice.get("setFlags") or {}, "humanityChange": humanity_change, "costs": choice.get("costs") or [], "effects": choice.get("effects") or []}
                if humanity_change:
                    warnings.append(f"{scene.get('sceneId')} / {choice_id}: humanity is retained in trustedContract and needs the future player-state presentation bridge.")
                if conditions:
                    warnings.append(f"{scene.get('sceneId')} / {choice_id}: conditions are retained in trustedContract for trusted numeric conversion.")
                if choice.get("requiredFlags") or choice.get("setFlags"):
                    warnings.append(f"{scene.get('sceneId')} / {choice_id}: story flags are retained in the browser bundle and trustedContract.")
                choices.append({"id": choice_id, "text": choice.get("text", ""), "nextSceneId": choice.get("nextSceneId") or scene.get("sceneId"), "endsBook": not bool(choice.get("nextSceneId")), "consequencesSummary": choice.get("effectsNotes") or None, "effects": browser_effects or None, "condition": browser_condition or None})
            converted_scenes.append({"id": scene.get("sceneId"), "bookId": snapshot.get("bookId"), "chapterNumber": chapter, "chapterTitle": scenes[0].get("title", f"Chapter {chapter}"), "sceneTitle": scene.get("title", "Untitled scene"), "sceneIndex": index, "paragraphs": [part for part in str(scene.get("body", "")).split("\n\n") if part] or [""], "dialogues": [{"speaker": line.get("displayName", line.get("speakerId", "Narrator")), "text": line.get("text", ""), "characterId": line.get("speakerId"), "mood": line.get("mood") if line.get("mood") in {"neutral", "intense", "whisper", "romantic", "warning"} else "neutral"} for line in scene.get("dialogue", []) if isinstance(line, dict)], "choices": choices})
    chapters = [{"number": chapter, "title": scenes[0].get("title", f"Chapter {chapter}"), "summary": "Converted from approved draft.", "firstSceneId": scenes[0].get("sceneId"), "totalScenes": len(scenes), "rewardCoins": 0} for chapter, scenes in sorted(chapter_scenes.items())]
    bundle = {"contentSchemaVersion": 1, "book": {"id": snapshot["bookId"], "version": release["version"], "seriesId": "draft-series", "order": 0, "title": snapshot.get("title", "Untitled"), "subtitle": "Converted release candidate", "synopsis": snapshot.get("synopsis", ""), "coverArtStyle": "gothic-romance", "startingSceneId": ordered[0].get("sceneId"), "chapters": chapters}, "scenes": converted_scenes}
    return {"format": "vampires-choice-narrative-conversion-preview/v1", "exportedAt": _now(), "release": _public_admin_release(release), "playerBundleCandidate": bundle, "trustedContract": {"humanityInitial": snapshot.get("playtestValues", {}).get("humanity", 100), "humanityMin": 0, "humanityMax": 100, "choices": trusted_choices}, "warnings": list(dict.fromkeys(warnings)), "publication": {"playerFacing": False, "published": False, "note": "Preview artifact only. It has not been added to the content loader, trusted registry, or public catalogue."}}


@api.post("/admin/releases/{release_id}/catalogue-registration")
async def register_admin_catalogue_candidate(release_id: str, request: Request):
    """Register a reviewed conversion as an auditable rollout candidate.

    Registration is intentionally not publication: normal player content, saves
    and the trusted runtime registry remain untouched.
    """
    user = await _current_user(request)
    _require_admin(user)
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    approval = release.get("publicationApproval")
    if not isinstance(approval, dict) or approval.get("checksum") != release["manifest"]["sha256"]:
        raise HTTPException(status_code=409, detail={"error": "publication_review_not_approved"})
    compatibility = await inspect_admin_trusted_content_compatibility(release_id, request)
    if compatibility["summary"]["blockingIssueCount"]:
        raise HTTPException(status_code=409, detail={"error": "trusted_content_blocked", "blockingIssueCount": compatibility["summary"]["blockingIssueCount"]})
    preview = await preview_admin_narrative_conversion(release_id, request)
    now = _now()
    registration = {"releaseId": release_id, "bookId": release["bookId"], "releaseVersion": release["version"], "checksum": release["manifest"]["sha256"], "status": "registered", "registeredAt": now, "registeredBy": user["email"], "playerFacing": False, "published": False, "note": "Registered for a later explicit rollout only; it is not in the player catalogue."}
    try:
        await trusted_catalogue_candidates.update_one(
            {"releaseId": release_id},
            {"$setOnInsert": {"candidateId": f"candidate_{uuid.uuid4().hex}", "createdAt": now}, "$set": {**registration, "playerBundleCandidate": preview["playerBundleCandidate"], "trustedContract": preview["trustedContract"], "compatibility": compatibility["summary"]}, "$inc": {"registrationRevision": 1}, "$push": {"history": {"$each": [{"action": "registered", "at": now, "by": user["email"], "checksum": registration["checksum"]}], "$slice": -20}}},
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail={"error": "catalogue_registration_conflict"})
    candidate = await trusted_catalogue_candidates.find_one({"releaseId": release_id}, {"_id": 0, "playerBundleCandidate": 0, "trustedContract": 0})
    await admin_releases.update_one({"releaseId": release_id}, {"$set": {"catalogueRegistration": candidate}})
    return {"candidate": candidate, "productionPublished": False, "note": "Registered as a private rollout candidate only. The player catalogue and all player saves are unchanged."}


async def _invalidate_catalogue_registration(release_id: str, reason: str, by: str) -> None:
    """Keep the audit trail but prevent stale beta evidence being rolled out."""
    now = _now()
    await trusted_catalogue_candidates.update_one({"releaseId": release_id, "status": "registered"}, {"$set": {"status": "invalidated", "invalidatedAt": now, "invalidatedBy": by, "invalidationReason": reason, "playerFacing": False, "published": False}, "$push": {"history": {"$each": [{"action": "invalidated", "at": now, "by": by, "reason": reason}], "$slice": -20}}})
    await admin_releases.update_one({"releaseId": release_id}, {"$unset": {"catalogueRegistration": ""}})


@api.get("/admin/catalogue-candidates")
async def list_admin_catalogue_candidates(request: Request):
    """List rollout candidates without exposing their content payloads."""
    user = await _current_user(request)
    _require_admin(user)
    candidates = await trusted_catalogue_candidates.find({}, {"_id": 0, "playerBundleCandidate": 0, "trustedContract": 0}).sort("registeredAt", -1).to_list(length=200)
    return {"candidates": candidates, "playerFacing": False, "published": False}


@api.post("/admin/catalogue-candidates/{candidate_id}/withdraw")
async def withdraw_admin_catalogue_candidate(candidate_id: str, request: Request):
    """Withdraw a registered rollout candidate while retaining its audit history."""
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"candidate_[0-9a-f]{32}", candidate_id):
        raise HTTPException(status_code=404, detail={"error": "catalogue_candidate_not_found"})
    now = _now()
    candidate = await trusted_catalogue_candidates.find_one_and_update(
        {"candidateId": candidate_id, "status": "registered"},
        {"$set": {"status": "withdrawn", "withdrawnAt": now, "withdrawnBy": user["email"], "playerFacing": False, "published": False}, "$push": {"history": {"$each": [{"action": "withdrawn", "at": now, "by": user["email"]}], "$slice": -20}}},
        return_document=True,
    )
    if candidate is None:
        raise HTTPException(status_code=409, detail={"error": "catalogue_candidate_not_registered"})
    await admin_releases.update_one({"releaseId": candidate["releaseId"]}, {"$unset": {"catalogueRegistration": ""}})
    candidate.pop("_id", None)
    candidate.pop("playerBundleCandidate", None)
    candidate.pop("trustedContract", None)
    return {"candidate": candidate, "productionPublished": False, "note": "Candidate withdrawn. No player content or player save changed."}


@api.get("/admin/catalogue-candidates/{candidate_id}/activation-preflight")
async def inspect_admin_catalogue_activation_preflight(candidate_id: str, request: Request):
    """Check whether a frozen candidate can be explicitly made public."""
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"candidate_[0-9a-f]{32}", candidate_id):
        raise HTTPException(status_code=404, detail={"error": "catalogue_candidate_not_found"})
    candidate = await trusted_catalogue_candidates.find_one({"candidateId": candidate_id}, {"_id": 0, "playerBundleCandidate": 0, "trustedContract": 0})
    if candidate is None:
        raise HTTPException(status_code=404, detail={"error": "catalogue_candidate_not_found"})
    release = await admin_releases.find_one({"releaseId": candidate["releaseId"]}, {"_id": 0})
    matching_approval = bool(release and isinstance(release.get("publicationApproval"), dict) and release["publicationApproval"].get("checksum") == candidate["checksum"] and release["manifest"]["sha256"] == candidate["checksum"])
    registered = candidate.get("status") == "registered"
    compatibility = candidate.get("compatibility", {})
    no_blockers = compatibility.get("blockingIssueCount") == 0
    checks = [
        {"id": "candidate_registered", "passed": registered, "message": "Candidate remains registered and has not been withdrawn or invalidated."},
        {"id": "checksum_approval", "passed": matching_approval, "message": "The immutable release and controlled approval still match the candidate checksum."},
        {"id": "trusted_compatibility", "passed": no_blockers, "message": "The recorded trusted-content compatibility report has no blockers."},
        {"id": "public_runtime_boundary", "passed": True, "message": "The runtime catalogue can pin this immutable candidate without changing existing player saves."},
    ]
    ready = all(check["passed"] for check in checks)
    return {"format": "vampires-choice-catalogue-activation-preflight/v1", "checkedAt": _now(), "candidate": candidate, "checks": checks, "activationReady": ready, "productionPublished": candidate.get("published") is True, "rollbackPlan": {"action": "select a prior immutable candidate for this book, or unpublish it", "playerSavesTouched": 0, "playerCatalogueChanged": True}, "note": "Read-only preflight. A separate confirmed action is required to expose this version in the public runtime catalogue."}


def _public_catalogue_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {key: entry[key] for key in ("bookId", "candidateId", "releaseId", "releaseVersion", "checksum", "publishedAt", "publishedBy", "previousCandidateId", "publicationRevision") if key in entry}


@api.post("/admin/catalogue-candidates/{candidate_id}/publish")
async def publish_admin_catalogue_candidate(candidate_id: str, request: Request):
    """Explicitly activate one checksum-bound candidate in the public catalogue.

    This only changes the published catalogue pointer. Candidate and release
    snapshots remain immutable, and account/player saves are not read or
    written by this endpoint.
    """
    user = await _current_user(request)
    _require_admin(user)
    if not re.fullmatch(r"candidate_[0-9a-f]{32}", candidate_id):
        raise HTTPException(status_code=404, detail={"error": "catalogue_candidate_not_found"})
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict) or body.get("confirm") is not True:
        raise HTTPException(status_code=422, detail={"error": "publication_confirmation_required"})
    candidate = await trusted_catalogue_candidates.find_one({"candidateId": candidate_id}, {"_id": 0})
    if candidate is None:
        raise HTTPException(status_code=404, detail={"error": "catalogue_candidate_not_found"})
    if body.get("checksum") != candidate.get("checksum"):
        raise HTTPException(status_code=409, detail={"error": "publication_checksum_mismatch"})
    release = await admin_releases.find_one({"releaseId": candidate["releaseId"]}, {"_id": 0})
    approved = bool(release and isinstance(release.get("publicationApproval"), dict) and release["publicationApproval"].get("checksum") == candidate["checksum"] and release["manifest"]["sha256"] == candidate["checksum"])
    compatible = candidate.get("compatibility", {}).get("blockingIssueCount") == 0
    if candidate.get("status") != "registered" or not approved or not compatible:
        raise HTTPException(status_code=409, detail={"error": "publication_preflight_failed"})
    now = _now()
    previous = await published_catalogue.find_one({"bookId": candidate["bookId"]}, {"_id": 0})
    entry = {"bookId": candidate["bookId"], "candidateId": candidate_id, "releaseId": candidate["releaseId"], "releaseVersion": candidate["releaseVersion"], "checksum": candidate["checksum"], "playerBundle": candidate["playerBundleCandidate"], "trustedContract": candidate["trustedContract"], "publishedAt": now, "publishedBy": user["email"], "previousCandidateId": previous.get("candidateId") if previous else None, "publicationRevision": (previous.get("publicationRevision", 0) + 1) if previous else 1}
    await published_catalogue.replace_one({"bookId": candidate["bookId"]}, entry, upsert=True)
    await trusted_catalogue_candidates.update_one({"candidateId": candidate_id}, {"$set": {"published": True, "playerFacing": True, "publishedAt": now, "publishedBy": user["email"]}, "$push": {"history": {"$each": [{"action": "published", "at": now, "by": user["email"], "checksum": candidate["checksum"]}], "$slice": -20}}})
    return {"published": _public_catalogue_entry(entry), "playerSavesTouched": 0, "note": "This immutable release is now available through the public player catalogue. Existing player saves were not changed."}


@api.post("/admin/catalogue/{book_id}/rollback")
async def rollback_published_catalogue_book(book_id: str, request: Request):
    """Point a live book back to a prior immutable candidate or unpublish it."""
    user = await _current_user(request)
    _require_admin(user)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict) or body.get("confirm") is not True:
        raise HTTPException(status_code=422, detail={"error": "rollback_confirmation_required"})
    active = await published_catalogue.find_one({"bookId": book_id}, {"_id": 0})
    if active is None:
        raise HTTPException(status_code=404, detail={"error": "published_book_not_found"})
    target_id = body.get("candidateId")
    if target_id is None:
        await published_catalogue.delete_one({"bookId": book_id})
        action = "unpublished"
    else:
        target = await trusted_catalogue_candidates.find_one({"candidateId": target_id, "bookId": book_id}, {"_id": 0})
        if target is None or target.get("compatibility", {}).get("blockingIssueCount") != 0:
            raise HTTPException(status_code=409, detail={"error": "rollback_candidate_unavailable"})
        now = _now()
        replacement = {"bookId": book_id, "candidateId": target_id, "releaseId": target["releaseId"], "releaseVersion": target["releaseVersion"], "checksum": target["checksum"], "playerBundle": target["playerBundleCandidate"], "trustedContract": target["trustedContract"], "publishedAt": now, "publishedBy": user["email"], "previousCandidateId": active.get("candidateId"), "publicationRevision": active.get("publicationRevision", 0) + 1}
        await published_catalogue.replace_one({"bookId": book_id}, replacement, upsert=True)
        action = "rolled_back"
    await trusted_catalogue_candidates.update_one({"candidateId": active["candidateId"]}, {"$set": {"published": False, "playerFacing": False}, "$push": {"history": {"$each": [{"action": action, "at": _now(), "by": user["email"]}], "$slice": -20}}})
    return {"action": action, "bookId": book_id, "playerSavesTouched": 0, "note": "The public catalogue changed; immutable release snapshots and all player saves remain intact."}


@api.get("/player/catalogue")
async def public_player_catalogue():
    """Public, version-pinned listing used by the isolated live release reader."""
    entries = await published_catalogue.find({}, {"_id": 0, "playerBundle": 0, "trustedContract": 0}).sort("bookId", 1).to_list(length=100)
    return {"books": [_public_catalogue_entry(entry) for entry in entries], "format": "vampires-choice-public-catalogue/v1"}


@api.get("/player/catalogue/{book_id}")
async def public_player_catalogue_book(book_id: str):
    entry = await published_catalogue.find_one({"bookId": book_id}, {"_id": 0})
    if entry is None:
        raise HTTPException(status_code=404, detail={"error": "published_book_not_found"})
    return {"published": _public_catalogue_entry(entry), "playerBundle": entry["playerBundle"], "trustedContract": entry["trustedContract"], "playerSavesTouched": 0, "note": "This is an immutable, version-pinned public story release. Existing player saves remain separate."}


@api.put("/admin/releases/{release_id}/beta-access")
async def configure_admin_beta_access(release_id: str, request: Request, payload: BetaAccessUpdate):
    """Enable a selected, authenticated beta only for the supplied email list."""
    user = await _current_user(request)
    _require_admin(user)
    if not BETA_RELEASES_ENABLED:
        raise HTTPException(status_code=409, detail={"error": "beta_releases_disabled"})
    release = await admin_releases.find_one({"releaseId": release_id}, {"_id": 0})
    if release is None:
        raise HTTPException(status_code=404, detail={"error": "release_not_found"})
    if release.get("status") != "staged":
        raise HTTPException(status_code=409, detail={"error": "beta_release_not_staged"})
    if not payload.emails:
        await beta_release_access.delete_many({"releaseId": release_id})
        await admin_releases.update_one({"releaseId": release_id}, {"$set": {"betaEnabled": False, "betaDisabledAt": _now(), "betaDisabledBy": user["email"]}, "$unset": {"betaDecision": "", "publicationApproval": "", "catalogueRegistration": ""}})
        await _invalidate_catalogue_registration(release_id, "beta_access_changed", user["email"])
        return {"releaseId": release_id, "enabled": False, "invitedCount": 0, "playerFacing": False, "productionPublished": False}
    await beta_release_access.delete_many({"releaseId": release_id})
    now = _now()
    await beta_release_access.insert_many([{"releaseId": release_id, "email": email, "createdAt": now, "createdBy": user["email"]} for email in payload.emails])
    await admin_releases.update_one({"releaseId": release_id}, {"$set": {"betaEnabled": True, "betaEnabledAt": now, "betaEnabledBy": user["email"]}, "$unset": {"betaDisabledAt": "", "betaDisabledBy": "", "betaDecision": "", "publicationApproval": "", "catalogueRegistration": ""}})
    await _invalidate_catalogue_registration(release_id, "beta_access_changed", user["email"])
    return {"releaseId": release_id, "enabled": True, "invitedCount": len(payload.emails), "playerFacing": True, "productionPublished": False}


@api.get("/beta-releases/{book_id}")
async def get_beta_release(book_id: str, request: Request):
    user = await _current_user(request)
    release = await _beta_release_for_user(book_id, user)
    return {"format": "vampires-choice-private-beta/v1", "environment": "beta", "release": _public_admin_release(release), "snapshot": release["snapshot"], "note": "Invite-only beta. It uses a version-pinned beta session and never modifies the account save."}


@api.post("/beta-releases/{book_id}/sessions")
async def create_or_resume_beta_session(book_id: str, request: Request):
    user = await _current_user(request)
    release = await _beta_release_for_user(book_id, user)
    existing = await beta_player_sessions.find_one({"releaseId": release["releaseId"], "userId": user["user_id"]}, {"_id": 0})
    if existing:
        return _public_beta_session(existing)
    scenes = [scene for scene in release["snapshot"].get("scenes", []) if isinstance(scene, dict) and scene.get("sceneId")]
    if not scenes:
        raise HTTPException(status_code=422, detail={"error": "beta_release_has_no_scenes"})
    now = _now()
    doc = {"sessionId": f"beta_{uuid.uuid4().hex}", "releaseId": release["releaseId"], "bookId": book_id, "userId": user["user_id"], "contentVersion": release["version"], "sceneId": min(scenes, key=lambda scene: (int(scene.get("chapterNumber", 1)), scene["sceneId"]))["sceneId"], "stats": _staged_preview_stats(release["snapshot"]), "flags": {}, "history": [], "revision": 1, "createdAt": now, "updatedAt": now}
    try:
        await beta_player_sessions.insert_one(doc)
    except DuplicateKeyError:
        doc = await beta_player_sessions.find_one({"releaseId": release["releaseId"], "userId": user["user_id"]}, {"_id": 0})
    return _public_beta_session(doc)


@api.post("/beta-player-sessions/{session_id}/choices")
async def choose_beta_session(session_id: str, request: Request, payload: StagedPreviewChoiceInput):
    user = await _current_user(request)
    session = await beta_player_sessions.find_one({"sessionId": session_id, "userId": user["user_id"]}, {"_id": 0})
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "beta_session_not_found"})
    release = await _beta_release_for_user(session["bookId"], user)
    if release["releaseId"] != session["releaseId"]:
        raise HTTPException(status_code=409, detail={"error": "beta_release_changed"})
    if session["revision"] != payload.baseRevision:
        raise HTTPException(status_code=409, detail={"error": "beta_session_revision_conflict"})
    updated = _apply_staged_preview_choice(session, release["snapshot"], payload.sceneId, payload.choiceId)
    next_session = await beta_player_sessions.find_one_and_update({"sessionId": session_id, "userId": user["user_id"], "revision": payload.baseRevision}, {"$set": {"sceneId": updated["sceneId"], "stats": updated["stats"], "flags": updated["flags"], "updatedAt": _now()}, "$push": {"history": {"$each": [updated["event"]], "$slice": -200}}, "$inc": {"revision": 1}}, return_document=True)
    if next_session is None:
        raise HTTPException(status_code=409, detail={"error": "beta_session_revision_conflict"})
    return _public_beta_session(next_session)


@api.post("/beta-player-sessions/{session_id}/restart")
async def restart_beta_session(session_id: str, request: Request):
    user = await _current_user(request)
    session = await beta_player_sessions.find_one({"sessionId": session_id, "userId": user["user_id"]}, {"_id": 0})
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "beta_session_not_found"})
    release = await _beta_release_for_user(session["bookId"], user)
    scenes = [scene for scene in release["snapshot"].get("scenes", []) if isinstance(scene, dict) and scene.get("sceneId")]
    opening = min(scenes, key=lambda scene: (int(scene.get("chapterNumber", 1)), scene["sceneId"]))["sceneId"]
    next_session = await beta_player_sessions.find_one_and_update({"sessionId": session_id, "userId": user["user_id"]}, {"$set": {"sceneId": opening, "stats": _staged_preview_stats(release["snapshot"]), "flags": {}, "history": [], "updatedAt": _now()}, "$inc": {"revision": 1}}, return_document=True)
    return _public_beta_session(next_session)


@api.post("/beta-player-sessions/{session_id}/feedback", status_code=201)
async def submit_beta_feedback(session_id: str, request: Request, payload: BetaFeedbackInput):
    user = await _current_user(request)
    session = await beta_player_sessions.find_one({"sessionId": session_id, "userId": user["user_id"]}, {"_id": 0})
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "beta_session_not_found"})
    await _beta_release_for_user(session["bookId"], user)
    await beta_feedback.insert_one({"feedbackId": f"feedback_{uuid.uuid4().hex}", "releaseId": session["releaseId"], "sessionId": session_id, "userId": user["user_id"], "testerEmail": user["email"], "message": payload.message.strip(), "status": "open", "adminNote": "", "createdAt": _now()})
    await admin_releases.update_one({"releaseId": session["releaseId"]}, {"$unset": {"betaDecision": "", "publicationApproval": "", "catalogueRegistration": ""}})
    await _invalidate_catalogue_registration(session["releaseId"], "new_beta_feedback", user["email"])
    return {"ok": True}


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
