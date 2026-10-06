"""#5 PII masking (Agno built-in), #6 custom PII patterns, #27 output PII redaction."""

import re
from typing import Dict, Optional

from agno.guardrails import PIIDetectionGuardrail
from agno.run.agent import RunInput, RunOutput

from app.events import record

BUILTIN_PII = {"SSN", "Credit Card", "Email", "Phone"}


class PIIMaskingGuardrail(PIIDetectionGuardrail):
    """#5 masks SSN / card / email / phone; #6 adds domain-specific patterns via `custom_patterns`."""

    def __init__(self, custom_patterns: Optional[Dict[str, str]] = None):
        super().__init__(mask_pii=True, custom_patterns=custom_patterns)

    def check(self, run_input: RunInput) -> None:
        content = run_input.input_content_string()
        found = [name for name, rx in self.pii_patterns.items() if rx.search(content)]
        super().check(run_input)
        builtin = [n for n in found if n in BUILTIN_PII]
        custom = [n for n in found if n not in BUILTIN_PII]
        if builtin:
            record(5, "PII masking", "modified", "masked: " + ", ".join(builtin))
        if custom:
            record(6, "Custom PII patterns", "modified", "masked: " + ", ".join(custom))

    async def async_check(self, run_input: RunInput) -> None:
        self.check(run_input)


OUTPUT_PII_PATTERNS = [  # most specific first so a card number is not eaten by the phone regex
    ("CREDIT_CARD", re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("PHONE", re.compile(r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")),
]


class OutputPIIRedactor:
    """#27 Redact PII the model or a tool put into the final answer."""

    number, name = 27, "Output PII redaction"

    def __call__(self, run_output: RunOutput) -> None:
        if not isinstance(run_output.content, str):
            return
        redacted = []
        for label, rx in OUTPUT_PII_PATTERNS:
            run_output.content, n = rx.subn(f"[REDACTED_{label}]", run_output.content)
            if n:
                redacted.append(f"{n} {label}")
        if redacted:
            record(self.number, self.name, "modified", "redacted: " + ", ".join(redacted))
