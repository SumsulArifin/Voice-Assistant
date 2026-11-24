"""Configuration: environment variables, optionally loaded from a .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    """Minimal .env parser (KEY=VALUE). Real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


@dataclass
class Config:
    weather_api_key: str = ""
    default_city: str = "London"
    units: str = "metric"                     # metric | imperial
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    enable_wikipedia: bool = True
    language: str = "en-US"
    stt_engine: str = "google"                # google | sphinx (offline, needs pocketsphinx)
    custom_commands_path: Path = ROOT / "custom_commands.json"
    knowledge_base_path: Path = ROOT / "knowledge_base.json"
    contacts_path: Path = ROOT / "contacts.json"

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @classmethod
    def load(cls, env_path: Optional[str] = None) -> "Config":
        load_env_file(Path(env_path) if env_path else ROOT / ".env")
        g = os.environ.get
        return cls(
            weather_api_key=g("OPENWEATHER_API_KEY", ""),
            default_city=g("DEFAULT_CITY", "London"),
            units=g("UNITS", "metric"),
            smtp_host=g("SMTP_HOST", ""),
            smtp_port=int(g("SMTP_PORT", "587")),
            smtp_user=g("SMTP_USER", ""),
            smtp_password=g("SMTP_PASSWORD", ""),
            email_from=g("EMAIL_FROM", "") or g("SMTP_USER", ""),
            enable_wikipedia=g("ENABLE_WIKIPEDIA", "true").lower() in ("1", "true", "yes"),
            language=g("SPEECH_LANGUAGE", "en-US"),
            stt_engine=g("STT_ENGINE", "google").lower(),
            custom_commands_path=Path(g("CUSTOM_COMMANDS_FILE", str(ROOT / "custom_commands.json"))),
            knowledge_base_path=Path(g("KNOWLEDGE_BASE_FILE", str(ROOT / "knowledge_base.json"))),
            contacts_path=Path(g("CONTACTS_FILE", str(ROOT / "contacts.json"))),
        )
