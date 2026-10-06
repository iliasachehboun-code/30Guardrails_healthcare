"""Deterministic output guardrails: #9 system-prompt leak, #15 brand safety, #28 dangerous code,
#29 toxicity / profanity, plus the domain disclaimer rule."""

import re
from typing import Iterable

from agno.run.agent import RunOutput

from app.events import record


class SystemPromptLeakGuard:
    """#9 Redact internal markers if the model echoes its system prompt."""

    number, name = 9, "System-prompt leak guard"

    def __init__(self, secret_markers: Iterable[str]):
        self.markers = list(secret_markers)

    def __call__(self, run_output: RunOutput) -> None:
        if not isinstance(run_output.content, str):
            return
        leaked = [m for m in self.markers if m in run_output.content]
        for m in leaked:
            run_output.content = run_output.content.replace(m, "[REDACTED]")
        if leaked:
            record(self.number, self.name, "modified", f"redacted {len(leaked)} internal marker(s)")


class BrandSafetyFilter:
    """#15 Scrub competitor names from answers."""

    number, name = 15, "Brand safety"

    def __init__(self, banned_terms: Iterable[str], replacement: str = "[another provider]"):
        self.patterns = {t: re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE) for t in banned_terms}
        self.replacement = replacement

    def __call__(self, run_output: RunOutput) -> None:
        if not isinstance(run_output.content, str):
            return
        scrubbed = []
        for term, rx in self.patterns.items():
            run_output.content, n = rx.subn(self.replacement, run_output.content)
            if n:
                scrubbed.append(term)
        if scrubbed:
            record(self.number, self.name, "modified", "scrubbed: " + ", ".join(scrubbed))


DANGEROUS_CODE = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\brm\s+-[a-z]*r[a-z]*f?[a-z]*\s+(/|~|\*|\$HOME)(\s|$)",
        r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z)?sh\b",
        r":\(\)\s*\{\s*:\|:&\s*\};:",
        r"\bmkfs(\.\w+)?\s+/dev/",
        r"\bdd\s+if=\S+\s+of=/dev/(sd|nvme|hd)",
        r"\bchmod\s+-R\s+777\s+/",
        r"powershell(\.exe)?\s+.*-enc(odedcommand)?\b",
        r"\b(Invoke-Expression|iex)\s*\(?\s*\(?\s*(New-Object|iwr|Invoke-WebRequest)",
        r"\bformat\s+c:",
    ]
]


class DangerousCodeFilter:
    """#28 Remove destructive shell / PowerShell commands from answers."""

    number, name = 28, "Dangerous code filter"

    def __call__(self, run_output: RunOutput) -> None:
        if not isinstance(run_output.content, str):
            return
        lines = run_output.content.splitlines()
        kept = [
            "# [command removed by safety filter]" if any(p.search(ln) for p in DANGEROUS_CODE) else ln for ln in lines
        ]
        removed = sum(a != b for a, b in zip(kept, lines))
        if removed:
            run_output.content = "\n".join(kept) + "\n\n> Some commands were removed because they could damage your system."
            record(self.number, self.name, "modified", f"removed {removed} line(s)")


PROFANITY = ["fuck", "shit", "bitch", "bastard", "asshole", "idiot", "moron", "stupid", "dumbass", "crap"]
PROFANITY_RE = re.compile(r"\b(" + "|".join(map(re.escape, PROFANITY)) + r")\w*", re.IGNORECASE)


class ProfanityFilter:
    """#29 Mask profanity and insults in answers."""

    number, name = 29, "Toxicity filter"

    def __call__(self, run_output: RunOutput) -> None:
        if not isinstance(run_output.content, str):
            return
        run_output.content, n = PROFANITY_RE.subn(lambda m: m.group(0)[0] + "*" * (len(m.group(0)) - 1), run_output.content)
        if n:
            record(self.number, self.name, "modified", f"masked {n} word(s)")


class MedicalDisclaimer:
    """Domain output rule: every answer ends with a medical disclaimer."""

    TEXT = "\n\n_This is general health information, not medical advice. Please consult a qualified healthcare professional._"

    def __call__(self, run_output: RunOutput) -> None:
        if isinstance(run_output.content, str) and run_output.content and "not medical advice" not in run_output.content.lower():
            run_output.content += self.TEXT
