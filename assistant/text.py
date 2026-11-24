"""Tiny text-similarity toolkit (no third-party NLP dependency).

Used for intent classification, the local knowledge base and fuzzy matching of
custom commands.  Text is tokenised, stop words are dropped, words are
stemmed, and sentences are compared with TF-IDF weighted cosine similarity.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Callable, Dict, Iterable, Optional, Tuple

STOPWORDS = frozenset(
    """a an the is are am was were be to of for in on at it me my you your i im
    do does did can could would will please assistant what whats who whom whose
    which when where why how there this that these those now today tonight and
    or but so with about some any tell say saying says give show let us we our
    um uh just really want like""".split()
)

YES_WORDS = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm",
             "correct", "affirmative", "absolutely", "send", "proceed", "right"}
NO_WORDS = {"no", "nope", "nah", "cancel", "negative", "stop", "never", "dont",
            "don't", "abort"}


def stem(word: str) -> str:
    """Very small suffix stripper: good enough to match 'minutes'/'minute'."""
    if len(word) <= 3 or word.isdigit():
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    for suffix in ("ing", "ed"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokenize(text: str) -> list:
    text = text.lower().replace("’", "'")
    text = re.sub(r"'s\b", "", text).replace("'", "")
    words = re.findall(r"[a-z0-9]+", text)
    return [stem(w) for w in words if w not in STOPWORDS]


def normalize_phrase(text: str) -> str:
    """Lower-case, strip punctuation and filler for exact/fuzzy phrase matching."""
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower().replace("'", ""))
    text = re.sub(r"^(?:(?:please|hey|ok|okay)\s+)+(?:assistant\s+)?", "", text.strip())
    return re.sub(r"\s+", " ", text).strip()


def parse_yes_no(text: Optional[str]) -> Optional[bool]:
    """True for yes-ish, False for no-ish, None when unclear."""
    if not text:
        return None
    words = set(re.findall(r"[a-z']+", text.lower()))
    if words & NO_WORDS:
        return False
    if words & YES_WORDS:
        return True
    return None


class TextMatcher:
    """TF-IDF cosine matcher over a set of labelled example sentences."""

    def __init__(self, labelled_examples: Iterable[Tuple[str, str]],
                 preprocess: Optional[Callable[[str], str]] = None):
        self._pre = preprocess or (lambda t: t)
        docs = []
        df: Counter = Counter()
        for label, example in labelled_examples:
            tokens = tokenize(self._pre(example))
            if not tokens:
                continue
            docs.append((label, Counter(tokens)))
            df.update(set(tokens))
        n = len(docs)
        self._idf: Dict[str, float] = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}
        self._default_idf = math.log(n + 1) + 1
        self._vectors = [(label, *self._vectorise(counts)) for label, counts in docs]

    def _vectorise(self, counts: Counter):
        vec = {t: c * self._idf.get(t, self._default_idf) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return vec, norm

    def scores(self, text: str) -> Dict[str, float]:
        """Best similarity per label (0..1)."""
        tokens = tokenize(self._pre(text))
        if not tokens:
            return {}
        qvec, qnorm = self._vectorise(Counter(tokens))
        best: Dict[str, float] = {}
        for label, vec, norm in self._vectors:
            dot = sum(w * vec.get(t, 0.0) for t, w in qvec.items())
            sim = dot / (qnorm * norm)
            if sim > best.get(label, 0.0):
                best[label] = sim
        return best
