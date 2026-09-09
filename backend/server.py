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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

# Highest player-SAVE schema version this server understands (see frontend storage.ts).
SUPPORTED_SAVE_SCHEMA_VERSIONS = {1, 2, 3}
MAX_BODY_BYTES = 512 * 1024  # constrain request size
PLAYER_ID_RE = re.compile(r"^vc_[A-Za-z0-9_-]{8,64}$")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
saves = db["cloud_saves"]

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


app.include_router(api)
