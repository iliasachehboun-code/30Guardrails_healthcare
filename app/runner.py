"""Runs one chat turn through the guarded agent and turns the result into a verdict + audit record."""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from agno.agent import Agent
from agno.run.agent import RunOutput
from agno.run.base import RunStatus

from app import events
from app.events import GuardrailEvent, record
from app.guardrails.observability import AuditLog
from app.guardrails.tool_guards import ToolPermissionGuard


class _HideValidationLogs(logging.Filter):
    """Agno logs every blocked input as an ERROR; the CLI already shows the verdict."""

    def filter(self, rec: logging.LogRecord) -> bool:
        return not rec.getMessage().startswith("Validation failed")


logging.getLogger("agno").addFilter(_HideValidationLogs())


@dataclass
class TurnResult:
    verdict: str  # ALLOWED | BLOCKED | PAUSED | ERROR
    content: str
    run: RunOutput
    events: List[GuardrailEvent] = field(default_factory=list)
    latency_ms: int = 0

    @property
    def pending_approvals(self) -> list:
        if self.verdict != "PAUSED":
            return []
        return [r for r in self.run.active_requirements if r.needs_confirmation]


def verdict_of(run: RunOutput) -> str:
    if run.status == RunStatus.error:
        # Input guardrails stop the run before any message is built; provider errors happen later.
        return "BLOCKED" if not run.messages else "ERROR"
    if run.status == RunStatus.paused:
        return "PAUSED"
    return "ALLOWED"


class ChatSession:
    def __init__(self, agent: Agent, rbac: ToolPermissionGuard, audit: AuditLog, user_id: str):
        self.agent = agent
        self.rbac = rbac
        self.audit = audit
        self.user_id = user_id
        self.session_id = self.new_session()

    def new_session(self) -> str:
        self.session_id = f"cli-{uuid.uuid4().hex[:8]}"
        return self.session_id

    def send(self, message: str) -> TurnResult:
        events.drain()
        start = time.perf_counter()
        run = self.agent.run(message, user_id=self.user_id, session_id=self.session_id)
        return self._finish(run, message, start)

    def resolve_approvals(self, result: TurnResult, decide) -> TurnResult:
        """Resolve a paused run. `decide(tool_name, tool_args) -> (approved: bool, note: str)` asks the human.

        Calls the current user's role is not entitled to are rejected before a human is even asked (#24).
        """
        events.drain()
        summary = []
        for req in result.pending_approvals:
            tool_name, tool_args = req.tool_execution.tool_name, req.tool_execution.tool_args
            if not self.rbac.is_allowed(self.user_id, tool_name):
                req.reject(note=self.rbac.deny(self.user_id, tool_name))
                summary.append(f"{tool_name}: auto-rejected (role)")
                continue
            approved, note = decide(tool_name, tool_args)
            if approved:
                req.confirm()
                record(10, "Human approval", "approved", f"{tool_name}({tool_args})")
            else:
                req.reject(note=note or "Rejected by the reviewer.")
                record(10, "Human approval", "rejected", f"{tool_name}: {note}")
            summary.append(f"{tool_name}: {'approved' if approved else 'rejected'}")
        start = time.perf_counter()
        run = self.agent.continue_run(run_response=result.run, user_id=self.user_id, session_id=self.session_id)
        return self._finish(run, "[approval] " + "; ".join(summary), start)

    def _finish(self, run: RunOutput, input_text: str, start: float) -> TurnResult:
        verdict = verdict_of(run)
        skipped = [
            m.tool_name for m in (run.messages or [])
            if m.role == "tool" and str(m.content or "").startswith("Tool call limit reached")
        ]
        if skipped:
            record(8, "Loop control", "blocked", f"tool_call_limit={self.agent.tool_call_limit}, skipped {len(skipped)} call(s)")
        if verdict == "PAUSED":
            for req in run.active_requirements:
                if req.needs_confirmation:
                    record(10, "Human approval", "paused", f"{req.tool_execution.tool_name} awaiting approval")
        content = run.content if isinstance(run.content, str) else str(run.content or "")
        result = TurnResult(verdict, content, run, events.drain(), int((time.perf_counter() - start) * 1000))
        self.audit.log_turn(
            session_id=self.session_id,
            user_id=self.user_id,
            run_id=run.run_id,
            verdict=verdict,
            latency_ms=result.latency_ms,
            input_text=input_text,
            output_text=content,
            tools=[t.tool_name for t in (run.tools or []) if t.tool_name],
            events=result.events,
        )
        return result

    @property
    def role(self) -> str:
        return self.rbac.role_of(self.user_id)

    def switch_user(self, user_id: str) -> Optional[str]:
        self.user_id = user_id
        return self.new_session()
