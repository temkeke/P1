"""Asynchronous job handling for the P1 dialer bot."""
from __future__ import annotations

import asyncio
import threading
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable, Deque, Dict, Iterable, List, Optional

import aiovoip  # type: ignore

from config import Config
from models import Job, Lead, QueuedLead


class JobManager:
    """Manage call jobs by coordinating with the aiovoip client."""

    def __init__(
        self,
        config: Config,
        bot,
        on_call_complete: Optional[Callable[[Job, Lead, bool, bool], None]] = None,
    ):
        self._config = config
        self._bot = bot
        self._on_call_complete = on_call_complete
        self._jobs: Dict[str, Job] = {}
        self._press_one_queue: Dict[int, Deque[QueuedLead]] = {}
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever, name="p1-voip-loop", daemon=True
        )
        self._loop_thread.start()
        self._client_ready = asyncio.run_coroutine_threadsafe(
            self._create_client(), self._loop
        )

    async def _create_client(self):
        sip = self._config.sip
        return await aiovoip.Client.create(
            host=sip.host,
            username=sip.username,
            password=sip.password,
            port=sip.port,
            transport=sip.transport,
        )

    def _get_client(self):
        return self._client_ready.result()

    def create_job(
        self,
        user_id: int,
        leads: Iterable[Lead],
        script: str,
        caller_id: Optional[str],
        preset: str,
    ) -> Job:
        job_id = str(uuid.uuid4())[:8]
        job = Job(
            id=job_id,
            user_id=user_id,
            script=script,
            caller_id=caller_id,
            preset=preset,
            leads=list(leads),
        )
        self._jobs[job_id] = job
        self._press_one_queue.setdefault(user_id, deque())
        self._bot.send_message(
            job.user_id,
            (
                "✅ Job Started! \n\n"
                f"📋 Job ID: {job.id}\n"
                f"📊 Lines Started: {job.processed} / {job.total_calls()}\n"
                f"emoji, script: {job.script}\n\n\n\n"
                "Use /status to check progress."
            ),
        )
        asyncio.run_coroutine_threadsafe(self._process_job(job), self._loop)
        return job

    async def _process_job(self, job: Job) -> None:
        client = self._get_client()
        preset_dir = Path(self._config.bot.presets_dir) / job.preset
        intro = preset_dir / "intro.wav"
        outro = preset_dir / "outro.wav"

        for lead in job.leads:
            await self._dial_lead(client, job, lead, intro, outro)

        job.completed = True
        job.completed_at = datetime.utcnow()
        self._bot.send_message(
            job.user_id,
            (
                "✅ Job Completed\n\n"
                f"Job ID: {job.id}\n\n"
                "Results:\n"
                f"• Total Calls: {job.total_calls()}\n"
                f"• Completed: {job.processed}\n"
                f"• Answered: {job.answered}\n"
                f"• Pressed 1: {job.pressed_one}"
            ),
        )

    async def _dial_lead(
        self,
        client,
        job: Job,
        lead: Lead,
        intro: Path,
        outro: Path,
    ) -> None:
        script = job.script
        caller_id = job.caller_id

        call = await client.start_call(
            destination=lead.phone,
            caller_id=caller_id,
            media=[
                aiovoip.Playback(str(intro)),
                aiovoip.Say(script),
            ],
        )

        answered = False
        pressed_one = False

        async for event in call.events():
            if isinstance(event, aiovoip.events.Answered):
                answered = True
            elif isinstance(event, aiovoip.events.DigitReceived) and event.digit == "1":
                pressed_one = True
                await call.play(aiovoip.Playback(str(outro)))
                self._notify_press_one(job, lead)
            elif isinstance(event, aiovoip.events.Completed):
                break

        job.processed += 1
        if answered:
            job.answered += 1
        if pressed_one:
            job.pressed_one += 1
        if self._on_call_complete:
            self._on_call_complete(job, lead, answered, pressed_one)

    def _notify_press_one(self, job: Job, lead: Lead) -> None:
        queue = self._press_one_queue.setdefault(job.user_id, deque())
        queue.append(QueuedLead(lead=lead, queued_at=datetime.utcnow()))
        self._bot.send_message(
            job.user_id,
            (
                "🔔 P1 Alert\n\n"
                f"📞 {lead.phone}\n\n"
                f"Use /line to get full details ({job.id} in queue)"
            ),
        )

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def get_next_press_one(self, user_id: int) -> Optional[QueuedLead]:
        queue = self._press_one_queue.setdefault(user_id, deque())
        if not queue:
            return None
        return queue.popleft()

    def press_one_count(self, user_id: int) -> int:
        queue = self._press_one_queue.setdefault(user_id, deque())
        return len(queue)

    def list_jobs_for_user(self, user_id: int) -> List[Job]:
        return [job for job in self._jobs.values() if job.user_id == user_id]
