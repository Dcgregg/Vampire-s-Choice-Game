"""Phase 6 progression CONTRACTS (foundation only).

Pydantic mirrors of the client-side TS contracts (src/progression/contracts.ts).
INERT in 6A: not imported by server.py, no routes, no authority. Present so the
event/ledger wire shape is reviewed and pinned before 6B implements it.
"""
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class ChoiceProgressionEvent(BaseModel):
    kind: Literal["choice"]
    eventId: str
    bookId: str
    contentVersion: int
    fromSceneId: str
    choiceId: str
    baseProgressionRevision: int = 0


class LifecycleProgressionEvent(BaseModel):
    kind: Literal["lifecycle"]
    eventId: str
    bookId: str
    contentVersion: int
    lifecycleId: str
    baseProgressionRevision: int = 0


ProgressionEvent = Union[ChoiceProgressionEvent, LifecycleProgressionEvent]


class EventResult(BaseModel):
    eventId: str
    status: Literal["confirmed", "duplicate", "rejected"]
    reason: Optional[str] = None


class PublicLedgerAchievement(BaseModel):
    unlockedAt: int
    source: Literal["awarded", "imported"]


class PublicLedgerCoins(BaseModel):
    confirmed: int = Field(ge=0)


class PublicLedgerCheckpoint(BaseModel):
    bookId: str
    currentSceneId: str


class PublicLedger(BaseModel):
    ownerType: Literal["anon", "account"]
    coins: PublicLedgerCoins
    achievements: Dict[str, PublicLedgerAchievement] = {}
    checkpoint: PublicLedgerCheckpoint
    progressionRevision: int = 0
