"""A lightweight simulation of the aiovoip client used by the bot.

This stub provides enough structure for the bot to run in development
without relying on an external SIP implementation. It mimics the public
surface used by :mod:`job_manager` and can be replaced with the real
library by installing it in the runtime environment.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, List, Optional


class events:
    class Event: ...

    class Answered(Event):
        pass

    @dataclass
    class DigitReceived(Event):
        digit: str

    class Completed(Event):
        pass


@dataclass
class Playback:
    path: str


@dataclass
class Say:
    text: str


class CallSession:
    def __init__(self, destination: str, intro: Playback, message: Say):
        self._destination = destination
        self._intro = intro
        self._message = message
        self._queue: asyncio.Queue[events.Event] = asyncio.Queue()
        self._playback_history: List[Playback] = [intro]
        self._answered = False

    async def simulate(self, press_one: bool = False) -> None:
        await asyncio.sleep(0.1)
        await self._queue.put(events.Answered())
        self._answered = True
        if press_one:
            await asyncio.sleep(0.2)
            await self._queue.put(events.DigitReceived("1"))
        await asyncio.sleep(0.1)
        await self._queue.put(events.Completed())

    async def events(self) -> AsyncIterator[events.Event]:
        while True:
            event = await self._queue.get()
            yield event
            if isinstance(event, events.Completed):
                break

    async def play(self, playback: Playback) -> None:
        self._playback_history.append(playback)


class Client:
    def __init__(self, host: str, username: str, password: str, port: int, transport: str):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.transport = transport

    @classmethod
    async def create(
        cls,
        host: str,
        username: str,
        password: str,
        port: int = 5060,
        transport: str = "udp",
    ) -> "Client":
        await asyncio.sleep(0)
        return cls(host, username, password, port, transport)

    async def start_call(
        self,
        destination: str,
        caller_id: Optional[str] = None,
        media: Optional[List[object]] = None,
    ) -> CallSession:
        intro: Optional[Playback] = None
        say: Optional[Say] = None
        media = media or []
        for item in media:
            if isinstance(item, Playback) and intro is None:
                intro = item
            elif isinstance(item, Say) and say is None:
                say = item
        intro = intro or Playback(path=str(Path("intro.wav")))
        say = say or Say(text="")
        session = CallSession(destination, intro, say)
        asyncio.create_task(session.simulate())
        return session
