"""INERT candidate trusted API input boundary; not imported by server.py.

Content-ID limits remain provisional. This validates syntax only, NOT
identity, content, reachability, ledger ownership or lifecycle eligibility.
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

# Approved v1 event identity: lowercase hyphenated RFC 4122 UUID version 4.
EventId = Annotated[StrictStr, Field(min_length=36, max_length=36, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")]
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
