"""Configuration utilities for the P1 Telegram dialer bot."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Set


@dataclass
class SIPTrunkConfig:
    """Configuration needed to register against a SIP trunk."""

    host: str
    username: str
    password: str
    port: int = 5060
    transport: str = "udp"


@dataclass
class BotSettings:
    """Telegram bot related configuration."""

    token: str
    admin_ids: Set[int] = field(default_factory=set)
    initial_whitelist: Set[int] = field(default_factory=set)
    presets_dir: str = "presets"
    data_dir: str = "data"


@dataclass
class CallDefaults:
    """Default values for call execution."""

    caller_id: Optional[str] = None
    script_text: str = "example"
    intro_preset: str = "preset 1"


@dataclass
class Config:
    """Application wide configuration holder."""

    sip: SIPTrunkConfig
    bot: BotSettings
    defaults: CallDefaults


def _parse_int_set(raw: Optional[str]) -> Set[int]:
    if not raw:
        return set()
    result: Set[int] = set()
    for value in raw.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            result.add(int(value))
        except ValueError:
            continue
    return result


def load_config() -> Config:
    """Load configuration from environment variables.

    Environment variables used:
        P1_SIP_HOST, P1_SIP_USERNAME, P1_SIP_PASSWORD, P1_SIP_PORT,
        P1_SIP_TRANSPORT, P1_BOT_TOKEN, P1_ADMIN_IDS, P1_WHITELIST_IDS,
        P1_PRESETS_DIR, P1_DATA_DIR, P1_DEFAULT_CALLER_ID, P1_DEFAULT_SCRIPT,
        P1_DEFAULT_PRESET
    """

    sip = SIPTrunkConfig(
        host=os.environ.get("P1_SIP_HOST", "sip.example.com"),
        username=os.environ.get("P1_SIP_USERNAME", "user"),
        password=os.environ.get("P1_SIP_PASSWORD", "pass"),
        port=int(os.environ.get("P1_SIP_PORT", "5060")),
        transport=os.environ.get("P1_SIP_TRANSPORT", "udp"),
    )

    bot = BotSettings(
        token=os.environ.get("P1_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN"),
        admin_ids=_parse_int_set(os.environ.get("P1_ADMIN_IDS")),
        initial_whitelist=_parse_int_set(os.environ.get("P1_WHITELIST_IDS")),
        presets_dir=os.environ.get("P1_PRESETS_DIR", "presets"),
        data_dir=os.environ.get("P1_DATA_DIR", "data"),
    )

    defaults = CallDefaults(
        caller_id=os.environ.get("P1_DEFAULT_CALLER_ID"),
        script_text=os.environ.get("P1_DEFAULT_SCRIPT", "example"),
        intro_preset=os.environ.get("P1_DEFAULT_PRESET", "preset 1"),
    )

    return Config(sip=sip, bot=bot, defaults=defaults)
