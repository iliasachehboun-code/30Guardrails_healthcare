"""Tool hooks: #24 role-based tool permissions, #11 tool-argument validation, #25 indirect prompt injection."""

import re
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Set

from agno.run import RunContext

from app.events import record


class ToolPermissionGuard:
    """#24 Only let each role call the tools it is entitled to."""

    number, name = 24, "Tool permissions (RBAC)"

    def __init__(self, role_permissions: Mapping[str, Set[str]], user_roles: Mapping[str, str], default_role: str = "guest"):
        self.role_permissions = role_permissions
        self.user_roles = user_roles
        self.default_role = default_role

    def role_of(self, user_id: Optional[str]) -> str:
        return self.user_roles.get(user_id or "", self.default_role)

    def is_allowed(self, user_id: Optional[str], tool_name: str) -> bool:
        return tool_name in self.role_permissions.get(self.role_of(user_id), set())

    def deny(self, user_id: Optional[str], tool_name: str) -> str:
        role = self.role_of(user_id)
        record(self.number, self.name, "denied", f"user={user_id} role={role} tool={tool_name}")
        return f"Permission denied: role '{role}' may not use {tool_name}. Tell the user this action is not available to them."

    def __call__(self, run_context: RunContext, function_name: str, function_call: Callable, arguments: Dict[str, Any]):
        user_id = run_context.user_id if run_context else None
        if not self.is_allowed(user_id, function_name):
            return self.deny(user_id, function_name)
        return function_call(**arguments)


DANGEROUS_SQL = ["drop ", "delete ", "truncate", "update ", "insert ", "alter ", "create ", "grant ", "attach ", "pragma", ";", "--"]


class ToolArgumentValidator:
    """#11 Validate tool arguments before the tool runs (read-only SQL, complete and sane bookings)."""

    number, name = 11, "Tool argument validation"

    def __init__(self, known_doctors: Iterable[str]):
        self.known_doctors = {d.lower() for d in known_doctors}

    def _refuse(self, function_name: str, reason: str) -> str:
        record(self.number, self.name, "blocked", f"{function_name}: {reason}")
        return f"Refused: {reason}"

    def __call__(self, function_name: str, function_call: Callable, arguments: Dict[str, Any]):
        if function_name == "query_appointments_db":
            sql = str(arguments.get("sql", "")).strip().rstrip(";").strip().lower()
            if not sql.startswith("select") or any(tok in sql for tok in DANGEROUS_SQL):
                return self._refuse(function_name, "only single read-only SELECT queries are permitted.")
        if function_name == "book_appointment":
            missing = [k for k in ("patient_name", "date", "doctor") if not str(arguments.get(k, "")).strip()]
            if missing:
                return self._refuse(function_name, f"missing {', '.join(missing)}. Ask the user for it.")
            doctor = re.sub(r"^dr\.?\s+", "", str(arguments["doctor"]).strip().lower())
            if doctor not in self.known_doctors:
                return self._refuse(
                    function_name, f"unknown doctor '{arguments['doctor']}'. Available: {', '.join(sorted(self.known_doctors))}."
                )
        return function_call(**arguments)


INDIRECT_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(all\s+)?(previous|prior|above|your)\s+instructions",
        r"disregard\s+(the\s+)?(system|previous)\s+(prompt|instructions)",
        r"\byou\s+are\s+now\b",
        r"new\s+instructions\s*:",
        r"(send|email|share)\s+(your|the\s+user'?s?|their)\s+(password|credentials|api\s+key|insurance)",
        r"do\s+not\s+(tell|inform)\s+the\s+user",
        r"<\s*/?\s*(system|instructions?)\s*>",
    ]
]


class IndirectInjectionScanner:
    """#25 Strip instruction-like lines from tool results before the model reads them."""

    number, name = 25, "Indirect prompt injection"

    def __call__(self, function_name: str, function_call: Callable, arguments: Dict[str, Any]):
        result = function_call(**arguments)
        lines = str(result).splitlines()
        clean = [ln for ln in lines if not any(p.search(ln) for p in INDIRECT_PATTERNS)]
        removed = len(lines) - len(clean)
        if removed:
            record(self.number, self.name, "modified", f"removed {removed} line(s) from {function_name} output")
            return f"[Sanitized: {removed} line(s) with embedded instructions removed]\n" + "\n".join(clean)
        return result
