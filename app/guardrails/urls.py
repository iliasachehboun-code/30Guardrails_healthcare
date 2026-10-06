"""#23 URL / domain allowlist on input and output."""

import ipaddress
import re
from typing import Iterable
from urllib.parse import urlparse

from agno.run.agent import RunInput, RunOutput

from app.events import record
from app.guardrails.base import Guardrail

URL_RE = re.compile(r"(?:https?|ftp|file|javascript|data):[^\s<>\"')\]]+", re.IGNORECASE)


def url_allowed(url: str, allowed_domains: Iterable[str]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https") or "@" in parsed.netloc:
        return False
    host = (parsed.hostname or "").lower()
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return any(host == d or host.endswith("." + d) for d in allowed_domains)


class URLFilterGuardrail(Guardrail):
    number, name = 23, "URL allowlist (input)"

    def __init__(self, allowed_domains: Iterable[str]):
        self.allowed_domains = list(allowed_domains)

    def check(self, run_input: RunInput) -> None:
        bad = [u for u in URL_RE.findall(run_input.input_content_string()) if not url_allowed(u, self.allowed_domains)]
        if bad:
            self.block(
                "That link points to a domain I'm not allowed to use. Trusted sources: "
                + ", ".join(self.allowed_domains),
                detail="blocked: " + ", ".join(bad),
            )


class URLOutputFilter:
    number, name = 23, "URL allowlist (output)"

    def __init__(self, allowed_domains: Iterable[str]):
        self.allowed_domains = list(allowed_domains)

    def __call__(self, run_output: RunOutput) -> None:
        if not isinstance(run_output.content, str):
            return
        removed = [u for u in set(URL_RE.findall(run_output.content)) if not url_allowed(u, self.allowed_domains)]
        for u in removed:
            run_output.content = run_output.content.replace(u, "[link removed]")
        if removed:
            record(self.number, self.name, "modified", "removed: " + ", ".join(removed))
