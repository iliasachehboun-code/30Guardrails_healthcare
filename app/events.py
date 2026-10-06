"""Collects every guardrail decision made during the current turn.

Guardrails call `record(...)` whenever they act; the runner drains the list after
each turn so the CLI can show it and the audit log can persist it.
"""

import threading
from dataclasses import dataclass
from typing import List


@dataclass
class GuardrailEvent:
    number: int
    name: str
    action: str  # blocked | modified | denied | paused | approved | rejected | validated | skipped
    detail: str = ""


_events: List[GuardrailEvent] = []
_lock = threading.Lock()


def record(number: int, name: str, action: str, detail: str = "") -> None:
    with _lock:
        _events.append(GuardrailEvent(number, name, action, detail[:300]))


def drain() -> List[GuardrailEvent]:
    with _lock:
        events = list(_events)
        _events.clear()
    return events
