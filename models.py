"""Data models for the P1 dialer bot."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Lead:
    email: Optional[str]
    name: Optional[str]
    phone: str


@dataclass
class Job:
    id: str
    user_id: int
    script: str
    caller_id: Optional[str]
    preset: str
    leads: List[Lead]
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed: bool = False
    completed_at: Optional[datetime] = None
    answered: int = 0
    pressed_one: int = 0
    processed: int = 0

    def total_calls(self) -> int:
        return len(self.leads)


@dataclass
class UserStats:
    user_id: int
    jobs_started: int = 0
    total_calls: int = 0
    total_answered: int = 0
    total_pressed_one: int = 0

    def register_job(self, job: Job) -> None:
        self.jobs_started += 1
        self.total_calls += job.total_calls()

    def register_call_update(
        self, answered: bool, pressed_one: bool
    ) -> None:
        if answered:
            self.total_answered += 1
        if pressed_one:
            self.total_pressed_one += 1


@dataclass
class QueuedLead:
    lead: Lead
    queued_at: datetime
