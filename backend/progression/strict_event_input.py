"""INERT candidate trusted API input boundary; not imported by server.py.

Limits are provisional and must be reviewed before endpoint registration.
This validates syntax only, NOT authentication, content, reachability or eligibility.
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

EventId = Annotated[StrictStr, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]
ContentId = Annotated[StrictStr, Field(min_length=1, max_length=128)]
Revision = Annotated[StrictInt, Field(ge=0)]
Version = Annotated[StrictInt, Field(ge=1)]


class _StrictEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    eventId: EventId
    bookId: ContentId
    contentVersion: Version
    baseProgressionRevision: Revision


class StrictChoiceEvent(_StrictEvent):
    kind: Literal["choice"]
    fromSceneId: ContentId
    choiceId: ContentId


class StrictLifecycleEvent(_StrictEvent):
    kind: Literal["lifecycle"]
    lifecycleId: ContentId


StrictProgressionEvent = Annotated[
    Union[StrictChoiceEvent, StrictLifecycleEvent], Field(discriminator="kind")
]
