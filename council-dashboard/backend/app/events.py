"""Typed events and the real async bus.

Primary transport is asyncio.Queue: every published event is appended to
history, fanned out to type subscribers, and queued for stream consumers
(the websocket feed drains the queue). When REDIS_URL is set, each event
is additionally bridged to Redis PubSub on channel `mars-council`.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List

RUN_STARTED = "RUN_STARTED"
MODE_SELECTED = "MODE_SELECTED"
EVENT_START_ROUND_1 = "EVENT_START_ROUND_1"
ROUND_1_SUBMIT = "ROUND_1_SUBMIT"
EVENT_START_ROUND_2 = "EVENT_START_ROUND_2"
COUNTERARGUE = "COUNTERARGUE"
CLUSTER_FORMED = "CLUSTER_FORMED"
EVENT_START_ROUND_3 = "EVENT_START_ROUND_3"
STEER_APPLIED = "STEER_APPLIED"
VOTE_CAST = "VOTE_CAST"
CONSENSUS_REACHED = "CONSENSUS_REACHED"
DISSENT_LOGGED = "DISSENT_LOGGED"
RUN_FINISHED = "RUN_FINISHED"
AUDIO_INGESTED = "AUDIO_INGESTED"
DAMAGE_ZONES = "DAMAGE_ZONES"
MAP_GENERATED = "MAP_GENERATED"
TOOL_REPAIRED = "TOOL_REPAIRED"
DEVIL_VERDICT = "DEVIL_VERDICT"
WONDER_PATHS = "WONDER_PATHS"


@dataclass(frozen=True)
class Event:
    type: str
    agent_id: str = "system"
    payload: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_json(self) -> str:
        return json.dumps({"type": self.type, "agent": self.agent_id,
                           "payload": self.payload, "ts": self.ts,
                           "id": self.id})


Subscriber = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self, maxsize: int = 4096) -> None:
        self.history: List[Event] = []
        self._subs: Dict[str, List[Subscriber]] = {}
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)

    def subscribe(self, event_type: str, fn: Subscriber) -> None:
        self._subs.setdefault(event_type, []).append(fn)

    async def publish(self, event: Event) -> None:
        self.history.append(event)
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
        for fn in list(self._subs.get(event.type, [])):
            await fn(event)
        await self._bridge(event)

    async def _bridge(self, event: Event) -> None:
        url = os.environ.get("REDIS_URL", "")
        if not url:
            return
        try:
            import redis.asyncio as redis
            client = redis.from_url(url)
            await client.publish("mars-council", event.to_json())
            await client.aclose()
        except Exception:
            pass

    async def drain(self) -> AsyncIterator[Event]:
        while True:
            yield await self._queue.get()
