"""Greeting, time/date and web search."""
from __future__ import annotations

import webbrowser
from datetime import datetime
from typing import Callable, Optional
from urllib.parse import quote_plus

GREETING = "Hello! I'm your voice assistant. How can I help you today?"


def greeting() -> str:
    return GREETING


def time_text(now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    return f"The time is {now.strftime('%I:%M %p').lstrip('0')}."


def date_text(now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    return f"Today is {now.strftime('%A, %B')} {now.day}, {now.year}."


def search_url(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def web_search(query: str, opener: Callable[[str], object] = webbrowser.open) -> str:
    opener(search_url(query))
    return f"Searching the web for {query}."


HELP_TEXT = (
    "I can greet you, tell the time and date, search the web, read the weather, "
    "send an email, set reminders and timers, answer general questions, and run "
    "your own custom commands. You can also say 'add a custom command' to teach me a new one."
)
