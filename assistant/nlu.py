"""Natural-language understanding: free-form sentence -> intent + slots.

Approach (hybrid, no heavy dependencies):
1. Slot patterns such as durations ("in an hour and a half") are masked so the
   classifier sees structure instead of specific numbers.
2. The sentence is compared with several example phrasings per intent using
   TF-IDF cosine similarity (see text.py), so wording can vary freely.
3. A few regex "boosts" add confidence when a strong signal is present
   (e.g. a duration together with "remind").
4. Slots (city, search query, recipient, duration, ...) are extracted with
   targeted patterns.
5. Low-scoring question-shaped sentences fall back to the knowledge intent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .text import TextMatcher

INTENT_EXAMPLES: Dict[str, List[str]] = {
    "greeting": ["hello", "hi", "hey", "hi there", "hey assistant", "good morning",
                 "good afternoon", "good evening", "howdy", "greetings"],
    "time": ["what time is it", "tell me the time", "current time",
             "what's the time now", "do you have the time"],
    "date": ["what's the date", "what day is it", "today's date",
             "which day is today", "current date", "what is the date today"],
    "web_search": ["search for something", "google it", "look up", "search the web",
                   "find information online", "browse the internet", "search online"],
    "weather": ["what's the weather like", "weather forecast", "how's the weather in london",
                "temperature outside", "is it going to rain", "do I need an umbrella",
                "how hot is it outside", "how cold is it", "is it sunny",
                "current weather in paris", "should I take a jacket"],
    "send_email": ["send an email", "email someone", "compose an email",
                   "write an email", "mail someone", "send email to alice"],
    "set_reminder": ["remind me in 5 minutes", "set a reminder", "set a timer for 10 minutes",
                     "set an alarm", "wake me up in an hour", "notify me in 30 seconds",
                     "start a countdown", "remind me to call mom in 2 hours"],
    "add_command": ["add a custom command", "create a new command",
                    "teach you a new command", "add a new voice command",
                    "learn a new command"],
    "help": ["help", "help me", "list commands", "show commands"],
    "exit": ["goodbye", "bye", "exit", "quit", "stop listening", "shut down",
             "see you later", "that is all"],
}

# Checked before classification (sentences made only of stop-words, small talk).
RULES: List[Tuple[str, re.Pattern, Optional[str]]] = [
    ("help", re.compile(r"^(?:what can you do|what are your (?:features|commands)|how do i use you)\b", re.I), None),
    ("smalltalk", re.compile(r"^(?:how are you|how's it going|how is it going|what's up|how do you do)\b", re.I),
     "I'm doing great, thanks for asking! What can I do for you?"),
    ("smalltalk", re.compile(r"\b(?:thank you|thanks)\b", re.I), "You're welcome!"),
    ("smalltalk", re.compile(r"\b(?:who are you|your name)\b", re.I),
     "I'm a Python voice assistant. Say help to hear what I can do."),
]

THRESHOLD = 0.35
QUESTION_START = re.compile(
    r"^(?:please\s+)?(?:can you\s+|could you\s+)?(?:tell me\s+)?"
    r"(?:what|who|whom|whose|where|when|why|how|which|is|are|was|were|does|do|did|"
    r"define|explain|describe|tell me about)\b", re.I)

# ---------------------------------------------------------------- durations
_NUM = (r"\d+(?:\.\d+)?|half an?|"
        r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[\s-](?:one|two|three|four|five|six|seven|eight|nine))?|"
        r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
        r"fifteen|sixteen|seventeen|eighteen|nineteen|an?")
DURATION_RE = re.compile(
    rf"\b(?P<num>{_NUM})\s*(?P<unit>hours?|hrs?|minutes?|mins?|seconds?|secs?)\b", re.I)
_PREFIX_RE = re.compile(r"\b(?:in|for|after|within)\s+$", re.I)
_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
          "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
          "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}
_UNIT_SECONDS = {"h": 3600, "m": 60, "s": 1}


def number_value(token: str) -> float:
    token = token.lower().strip()
    if token in ("a", "an"):
        return 1.0
    if token.startswith("half"):
        return 0.5
    try:
        return float(token)
    except ValueError:
        pass
    parts = re.split(r"[\s-]+", token)
    return float(sum(_TENS.get(p, _UNITS.get(p, 0)) for p in parts))


def find_durations(text: str) -> Tuple[int, List[Tuple[int, int]]]:
    """Total seconds mentioned in text plus the character spans they occupy."""
    total = 0.0
    spans: List[Tuple[int, int]] = []
    for m in DURATION_RE.finditer(text):
        unit_secs = _UNIT_SECONDS[m.group("unit")[0].lower()]
        total += number_value(m.group("num")) * unit_secs
        start, end = m.start(), m.end()
        half = re.match(r"\s*and\s+a\s+half\b", text[end:], re.I)
        if half:                                  # "an hour and a half"
            total += 0.5 * unit_secs
            end += half.end()
        prefix = _PREFIX_RE.search(text[:start])
        if prefix:
            start = prefix.start()
        spans.append((start, end))
    return int(round(total)), spans


def _remove_spans(text: str, spans: List[Tuple[int, int]], filler: str = " ") -> str:
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + filler + text[end:]
    return text


def mask_durations(text: str) -> str:
    return _remove_spans(text, find_durations(text)[1], " durationslot ")


# -------------------------------------------------------------- slot helpers
_BODY_MARKER = re.compile(r"\b(?:saying|says|that says|with (?:the )?message|and say)\b", re.I)
_NOT_A_CITY = {"today", "tomorrow", "now", "tonight", "me", "here", "the weekend",
               "this week", "the morning", "the evening"}


def extract_search_query(text: str) -> Optional[str]:
    m = re.match(
        r"^(?:(?:please|can you|could you|hey|ok)\s+)*"
        r"(?:search|google|look up|lookup|find|browse)"
        r"(?:\s+(?:the\s+)?(?:web|internet|online))?"
        r"(?:\s+(?:for|about|up))?\s*(.*)$", text.strip(), re.I)
    query = m.group(1) if m else ""
    query = re.sub(r"\s+(?:on|in) (?:the )?(?:web|internet|google|browser)$", "", query, flags=re.I)
    query = query.strip(" .?!")
    return query or None


def extract_city(text: str) -> Optional[str]:
    m = re.search(
        r"\b(?:in|at|for|of)\s+([A-Za-z][A-Za-z.\-]*(?:\s+[A-Za-z][A-Za-z.\-]*){0,3}?)"
        r"(?:\s+(?:today|tomorrow|now|right now|tonight|please|outside|this\b.*)|[?.!,]*$)", text.strip(), re.I)
    if not m:
        return None
    city = m.group(1).strip()
    return None if city.lower() in _NOT_A_CITY else city.title()


def extract_reminder_message(text: str) -> Optional[str]:
    rest = _remove_spans(text, find_durations(text)[1])
    m = re.search(r"\b(?:to|about|that)\s+(.+)$", rest, re.I)
    if not m:
        return None
    msg = re.sub(r"\s+", " ", m.group(1)).strip(" .?!")
    return msg or None


def spoken_to_email(spoken: str) -> str:
    """'john at example dot com' -> 'john@example.com'."""
    s = spoken.strip().lower().rstrip(".?!")
    s = re.sub(r"\s+at\s+", "@", s)
    s = re.sub(r"\s+dot\s+", ".", s)
    return re.sub(r"\s+", "", s)


def extract_email_slots(text: str) -> Dict[str, str]:
    slots: Dict[str, str] = {}
    body = re.search(r"\b(?:saying|says|that says|with (?:the )?message|and say)\s+(.+)$", text, re.I)
    head = text[:body.start()] if body else text
    if body:
        slots["body"] = body.group(1).strip()
    rec = re.search(r"\bto\s+(\S+(?:\s+at\s+\S+(?:\s+dot\s+\S+)+)?)", head, re.I)
    if rec:
        slots["recipient"] = spoken_to_email(rec.group(1))
    subj = re.search(r"\b(?:about|subject|regarding)\s+(.+)$", head, re.I)
    if subj:
        slots["subject"] = subj.group(1).strip(" .?!")
    return slots


# ----------------------------------------------------------------- the model
@dataclass
class Intent:
    name: str
    score: float = 0.0
    slots: Dict[str, object] = field(default_factory=dict)
    text: str = ""


class IntentClassifier:
    def __init__(self, threshold: float = THRESHOLD):
        self.threshold = threshold
        examples = [(name, ex) for name, exs in INTENT_EXAMPLES.items() for ex in exs]
        self._matcher = TextMatcher(examples, preprocess=mask_durations)

    def parse(self, text: str) -> Intent:
        text = text.strip()
        for name, pattern, reply in RULES:
            if pattern.search(text):
                return Intent(name, 1.0, {"reply": reply} if reply else {}, text)

        classify_text = text[:_BODY_MARKER.search(text).start()] if _BODY_MARKER.search(text) else text
        scores = dict(self._matcher.scores(classify_text))
        has_duration = bool(find_durations(text)[1])
        boosts = [
            ("web_search", re.match(r"^(?:(?:please|can you|could you|hey|ok)\s+)*(?:search|google|look up|browse)\b", text, re.I), 0.5),
            ("send_email", re.search(r"\be-?mail\b", text, re.I), 0.4),
            ("weather", re.search(r"\b(?:weather|forecast|temperature|umbrella)\b", text, re.I), 0.3),
            ("set_reminder", has_duration and re.search(r"\b(?:remind|reminder|timer|alarm|wake|notify|countdown)", text, re.I), 0.5),
        ]
        for name, hit, bonus in boosts:
            if hit:
                scores[name] = scores.get(name, 0.0) + bonus

        best, best_score = (max(scores.items(), key=lambda kv: kv[1]) if scores else ("unknown", 0.0))
        if best_score >= self.threshold:
            name = best
        elif QUESTION_START.match(text) or text.endswith("?"):
            name = "knowledge"
        else:
            name = "unknown"
        return Intent(name, round(best_score, 3), self._slots(name, text), text)

    @staticmethod
    def _slots(name: str, text: str) -> Dict[str, object]:
        if name == "web_search":
            return {"query": extract_search_query(text)}
        if name == "weather":
            return {"city": extract_city(text)}
        if name == "set_reminder":
            seconds, _ = find_durations(text)
            return {"seconds": seconds or None, "message": extract_reminder_message(text)}
        if name == "send_email":
            return dict(extract_email_slots(text))
        return {}
