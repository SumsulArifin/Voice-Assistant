"""User-defined commands stored in custom_commands.json.

Each command is {"phrases": [...], "action": "reply" | "url", "value": "..."}.
Only speaking a reply or opening an http(s) website is supported on purpose:
voice commands never execute shell commands.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import List, Optional

from ..text import normalize_phrase

ACTIONS = ("reply", "url")
FUZZY_CUTOFF = 0.86


def spoken_to_url(spoken: str) -> str:
    """'github dot com slash openai' -> 'https://github.com/openai'."""
    s = spoken.strip().lower().rstrip(".?!")
    s = re.sub(r"\s+dot\s+", ".", s)
    s = re.sub(r"\s+slash\s+", "/", s)
    s = re.sub(r"\s+", "", s)
    return s if s.startswith(("http://", "https://")) else "https://" + s


def is_safe_url(url: str) -> bool:
    return bool(re.match(r"^https?://[\w.-]+\.[a-z]{2,}(?:[/?#]\S*)?$", url, re.I))


class CustomCommands:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.commands: List[dict] = []
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = []
        self.commands = [c for c in data if self._valid(c)] if isinstance(data, list) else []

    @staticmethod
    def _valid(cmd) -> bool:
        return (isinstance(cmd, dict) and cmd.get("action") in ACTIONS
                and isinstance(cmd.get("phrases"), list) and cmd["phrases"]
                and isinstance(cmd.get("value"), str)
                and (cmd["action"] == "reply" or is_safe_url(cmd["value"])))

    def match(self, text: str) -> Optional[dict]:
        heard = normalize_phrase(text)
        if not heard:
            return None
        table = {normalize_phrase(p): c for c in self.commands for p in c["phrases"]}
        if heard in table:
            return table[heard]
        close = difflib.get_close_matches(heard, list(table), n=1, cutoff=FUZZY_CUTOFF)
        return table[close[0]] if close else None

    def add(self, phrase: str, action: str, value: str) -> dict:
        phrase = normalize_phrase(phrase)
        if not phrase:
            raise ValueError("The trigger phrase is empty.")
        cmd = {"phrases": [phrase], "action": action, "value": value}
        if not self._valid(cmd):
            raise ValueError("That command isn't valid (replies need text, websites need a proper address).")
        for existing in self.commands:           # replace an existing command with the same phrase
            if phrase in [normalize_phrase(p) for p in existing["phrases"]]:
                existing["phrases"] = [p for p in existing["phrases"] if normalize_phrase(p) != phrase]
        self.commands = [c for c in self.commands if c["phrases"]] + [cmd]
        self._save()
        return cmd

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(self.commands, fh, indent=2)
        os.replace(tmp, self.path)

    def describe(self) -> str:
        if not self.commands:
            return "You don't have any custom commands yet."
        names = [c["phrases"][0] for c in self.commands]
        return "Your custom commands are: " + "; ".join(names) + "."
