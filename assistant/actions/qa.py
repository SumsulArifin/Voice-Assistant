"""General-knowledge answers: local knowledge base first, Wikipedia as fallback."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

import requests

from ..text import TextMatcher

WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
HEADERS = {"User-Agent": "PythonVoiceAssistant/1.0 (learning project)"}
LOCAL_THRESHOLD = 0.55


def extract_topic(question: str) -> str:
    q = question.strip().rstrip("?.! ")
    q = re.sub(r"^(?:please\s+)?(?:can you\s+|could you\s+)?(?:tell me\s+)?"
               r"(?:about\s+|what(?:'s| is| are| was| were)?\s+|who(?:'s| is| was| were)?\s+|"
               r"where(?:'s| is| was)?\s+|when\s+(?:is|was|did)?\s*|how\s+(?:does|do|did)?\s*|"
               r"why\s+(?:is|are|does|do|did)?\s*|define\s+|explain\s+|describe\s+)", "", q, flags=re.I)
    q = re.sub(r"^(?:a|an|the)\s+", "", q, flags=re.I)
    return q.strip() or question


def first_sentences(text: str, n: int = 2) -> str:
    return " ".join(re.split(r"(?<=[.!?])\s+", text.strip())[:n])


class KnowledgeBase:
    def __init__(self, entries: Optional[List[dict]] = None, wikipedia: bool = True, session=None):
        self.entries = entries or []
        self.wikipedia = wikipedia
        self.session = session or requests
        self._matcher = TextMatcher(
            [(str(i), q) for i, e in enumerate(self.entries) for q in e.get("questions", [])])

    @classmethod
    def from_file(cls, path: Path, wikipedia: bool = True, session=None) -> "KnowledgeBase":
        try:
            entries = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            entries = []
        return cls(entries, wikipedia, session)

    def local_answer(self, question: str) -> Optional[str]:
        scores = self._matcher.scores(question)
        if not scores:
            return None
        idx, score = max(scores.items(), key=lambda kv: kv[1])
        return self.entries[int(idx)]["answer"] if score >= LOCAL_THRESHOLD else None

    def wikipedia_answer(self, question: str, timeout: float = 8) -> Optional[str]:
        topic = extract_topic(question)
        try:
            r = self.session.get(WIKI_SEARCH, headers=HEADERS, timeout=timeout, params={
                "action": "query", "list": "search", "srsearch": topic,
                "srlimit": 1, "format": "json"})
            hits = r.json()["query"]["search"]
            if not hits:
                return None
            title = hits[0]["title"].replace(" ", "_")
            r2 = self.session.get(WIKI_SUMMARY + quote(title), headers=HEADERS, timeout=timeout)
            extract = r2.json().get("extract")
            return first_sentences(extract) if extract else None
        except (requests.RequestException, KeyError, ValueError):
            return None

    def answer(self, question: str) -> Optional[str]:
        return self.local_answer(question) or (
            self.wikipedia_answer(question) if self.wikipedia else None)
