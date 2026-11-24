"""Minimal HTTP bridge so a web frontend can talk to the assistant's NLU/actions.

Run with: uvicorn assistant.api:app --reload --port 8000
Voice I/O stays in the browser (Web Speech API); this only exchanges text.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import Config
from .core import Assistant
from .actions.reminders import ReminderManager


class _CapturingSpeaker:
    """Stands in for Speaker: collects replies instead of speaking them."""

    def __init__(self) -> None:
        self.replies: list[str] = []

    def speak(self, text: str) -> None:
        self.replies.append(text)


class _NullListener:
    def listen(self) -> str:
        return ""


app = FastAPI(title="Voice Assistant API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_cfg = Config.load()
_assistant = Assistant(_cfg, _CapturingSpeaker(), _NullListener(), reminders=ReminderManager())


class ChatRequest(BaseModel):
    text: str


class ChatResponse(BaseModel):
    replies: list[str]
    done: bool


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    _assistant.speaker.replies = []
    keep_going = _assistant.handle(req.text)
    return ChatResponse(replies=list(_assistant.speaker.replies), done=not keep_going)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
