"""Deterministic input guardrails: #1 keywords, #4 length, #19 invisible text,
#21 language, #22 gibberish, #26 rate limit."""

import re
import time
import unicodedata
from collections import defaultdict, deque
from typing import Deque, Dict, Iterable, Optional

from agno.exceptions import CheckTrigger, InputCheckError
from agno.run.agent import RunInput
from langdetect import DetectorFactory, LangDetectException, detect_langs

from app.events import record
from app.guardrails.base import Guardrail

DetectorFactory.seed = 0


class ContentFilterGuardrail(Guardrail):
    """#1 Block requests containing banned keywords or phrases."""

    number, name = 1, "Keyword filter"

    def __init__(self, banned_keywords: Iterable[str], message: str):
        self.patterns = {kw: re.compile(rf"\b{re.escape(kw.lower())}") for kw in banned_keywords}
        self.message = message

    def check(self, run_input: RunInput) -> None:
        content = run_input.input_content_string().lower()
        for kw, rx in self.patterns.items():
            if rx.search(content):
                self.block(self.message, detail=f"banned keyword: '{kw}'")


class InputLengthGuardrail(Guardrail):
    """#4 Reject oversized inputs before they cost tokens."""

    number, name = 4, "Input length limit"

    def __init__(self, max_chars: int = 2000):
        self.max_chars = max_chars

    def check(self, run_input: RunInput) -> None:
        length = len(run_input.input_content_string())
        if length > self.max_chars:
            self.block(
                f"Your message is too long (limit {self.max_chars} characters). Please shorten it.",
                detail=f"{length} chars > {self.max_chars}",
            )


TAG_RANGE = range(0xE0000, 0xE0080)


class InvisibleTextGuardrail(Guardrail):
    """#19 Strip zero-width/format characters; block hidden Unicode-tag payloads (ASCII smuggling)."""

    number, name = 19, "Invisible text"

    def __init__(self, strip: bool = True):
        self.strip = strip

    def check(self, run_input: RunInput) -> None:
        text = run_input.input_content_string()
        hidden = {ch for ch in text if unicodedata.category(ch) in ("Cf", "Co", "Cn") or ord(ch) in TAG_RANGE}
        if not hidden:
            return
        payload = "".join(chr(ord(ch) - 0xE0000) for ch in text if ord(ch) in TAG_RANGE)
        if payload or not self.strip:
            self.block(
                "Your message contains hidden characters that are not allowed.",
                detail=f"hidden payload: {payload!r}" if payload else "hidden characters",
                trigger=CheckTrigger.PROMPT_INJECTION,
            )
        run_input.input_content = "".join(ch for ch in text if ch not in hidden)
        self.note("modified", f"stripped {len(hidden)} invisible character type(s)")


class LanguageGuardrail(Guardrail):
    """#21 Only accept supported languages (skips short or low-confidence text)."""

    number, name = 21, "Language restriction"

    def __init__(self, allowed: tuple = ("en",), min_chars: int = 40, min_confidence: float = 0.9):
        self.allowed = allowed
        self.min_chars = min_chars
        self.min_confidence = min_confidence

    def check(self, run_input: RunInput) -> None:
        text = run_input.input_content_string()
        if len(text) < self.min_chars:
            return
        try:
            best = detect_langs(text)[0]
        except LangDetectException:
            return
        if best.lang not in self.allowed and best.prob >= self.min_confidence:
            self.block(
                f"Sorry, I can only help in: {', '.join(self.allowed)}.",
                detail=f"detected '{best.lang}' ({best.prob:.2f})",
            )


class GibberishGuardrail(Guardrail):
    """#22 Reject keyboard-mash and symbol-flood inputs."""

    number, name = 22, "Gibberish detection"

    def __init__(self, max_gibberish_ratio: float = 0.5, min_words: int = 3):
        self.max_ratio = max_gibberish_ratio
        self.min_words = min_words

    @staticmethod
    def _is_gibberish_word(word: str) -> bool:
        w = word.lower()
        if len(w) < 4 or not w.isalpha():
            return False
        return (
            not re.search(r"[aeiouy]", w)
            or re.search(r"[^aeiouy]{5,}", w) is not None
            or re.search(r"(.)\1{3,}", w) is not None
        )

    def check(self, run_input: RunInput) -> None:
        text = run_input.input_content_string()
        message = "I couldn't understand that message. Could you rephrase it?"
        symbols = sum(1 for c in text if not (c.isalnum() or c.isspace()))
        if len(text) >= 20 and symbols / len(text) > 0.4:
            self.block(message, detail="mostly symbols", trigger=CheckTrigger.VALIDATION_FAILED)
        words = re.findall(r"[A-Za-z]+", text)
        if len(words) >= self.min_words:
            ratio = sum(self._is_gibberish_word(w) for w in words) / len(words)
            if ratio > self.max_ratio:
                self.block(message, detail=f"{ratio:.0%} gibberish words", trigger=CheckTrigger.VALIDATION_FAILED)


class RateLimiter:
    """#26 Sliding-window rate limit per user_id (pre-hook, so it receives user_id)."""

    number, name = 26, "Rate limit"

    def __init__(self, max_requests: int = 10, window_seconds: float = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: Dict[str, Deque[float]] = defaultdict(deque)

    def __call__(self, run_input: RunInput, user_id: Optional[str] = None) -> None:
        key = user_id or "anonymous"
        now = time.monotonic()
        q = self._history[key]
        while q and now - q[0] > self.window_seconds:
            q.popleft()
        if len(q) >= self.max_requests:
            record(self.number, self.name, "blocked", f"{key}: {self.max_requests} req / {self.window_seconds:.0f}s")
            raise InputCheckError(
                f"Rate limit reached ({self.max_requests} requests per {self.window_seconds:.0f}s). "
                "Please wait and try again.",
                check_trigger=CheckTrigger.INPUT_NOT_ALLOWED,
            )
        q.append(now)
