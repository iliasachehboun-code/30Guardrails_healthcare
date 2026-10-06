"""#20 Secrets / credential detection: block secrets in input, redact them from output."""

import re
from typing import List

from agno.exceptions import CheckTrigger
from agno.run.agent import RunInput, RunOutput

from app.events import record
from app.guardrails.base import Guardrail

SECRET_PATTERNS = {
    "OpenAI key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "Groq key": re.compile(r"\bgsk_[A-Za-z0-9]{20,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "Private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "Bearer token": re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]{20,}=*"),
    "Password": re.compile(r"(?i)\b(?:password|passwd|pwd)\s*[:=]\s*\S{6,}"),
}


def find_secrets(text: str) -> List[str]:
    return [name for name, rx in SECRET_PATTERNS.items() if rx.search(text)]


class SecretsGuardrail(Guardrail):
    number, name = 20, "Secrets detection (input)"

    def check(self, run_input: RunInput) -> None:
        found = find_secrets(run_input.input_content_string())
        if found:
            self.block(
                "Please don't share credentials or secrets. Revoke that secret and try again without it.",
                detail="found: " + ", ".join(found),
                trigger=CheckTrigger.PII_DETECTED,
                data={"secrets": found},
            )


class SecretsRedactor:
    number, name = 20, "Secrets redaction (output)"

    def __call__(self, run_output: RunOutput) -> None:
        if not isinstance(run_output.content, str):
            return
        redacted = []
        for label, rx in SECRET_PATTERNS.items():
            run_output.content, n = rx.subn(f"[REDACTED_{label.upper().replace(' ', '_')}]", run_output.content)
            if n:
                redacted.append(label)
        if redacted:
            record(self.number, self.name, "modified", "redacted: " + ", ".join(redacted))
