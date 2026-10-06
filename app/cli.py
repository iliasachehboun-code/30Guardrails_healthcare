"""Interactive terminal chat for the AcmeHealth assistant."""

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from app import config
from app.agents.healthcare import USERS, build_healthcare_agent
from app.guardrails.observability import AuditLog
from app.runner import ChatSession, TurnResult

console = Console()

VERDICT_STYLE = {"ALLOWED": "green", "BLOCKED": "red", "PAUSED": "yellow", "ERROR": "magenta"}
ACTION_STYLE = {"blocked": "red", "denied": "red", "modified": "yellow", "paused": "cyan",
                "approved": "green", "validated": "green", "rejected": "red", "skipped": "dim"}

GUARDRAIL_MAP = [
    (1, "Keyword filter", "input"), (2, "Prompt injection (regex)", "input"), (3, "Topical restriction", "input (judge)"),
    (4, "Input length limit", "input"), (5, "PII masking", "input"), (6, "Custom PII patterns", "input"),
    (7, "OpenAI moderation", "input + output"), (8, "Loop control / token budget", "agent config"),
    (9, "System-prompt leak guard", "output"), (10, "Human approval (HITL)", "tool"),
    (11, "Tool argument validation", "tool hook"), (12, "Output safety judge", "output (judge)"),
    (13, "Structured output", "triage tool"), (14, "RAG grounding", "output (judge)"), (15, "Brand safety", "output"),
    (16, "Crisis safe completion", "input"), (17, "Observability / audit log", "runner"),
    (18, "Prompt-attack classifier", "input (judge)"), (19, "Invisible text", "input"),
    (20, "Secrets detection", "input + output"), (21, "Language restriction", "input"), (22, "Gibberish detection", "input"),
    (23, "URL allowlist", "input + output"), (24, "Tool permissions (RBAC)", "tool hook"),
    (25, "Indirect prompt injection", "tool hook"), (26, "Rate limit", "input"), (27, "Output PII redaction", "output"),
    (28, "Dangerous code filter", "output"), (29, "Toxicity filter", "output"), (30, "Answer relevance", "output (judge)"),
]

HELP = """[bold]Commands[/bold]
  /help              show this help
  /user <id>         switch user ({users})
  /whoami            current user, role and session
  /new               start a new conversation session
  /guardrails        list the 30 guardrails and where they run
  /log \\[n]           last n turns from the audit log (default 10)
  /stats             verdict and guardrail firing counts
  /quit              exit"""


def show_result(result: TurnResult) -> None:
    style = VERDICT_STYLE.get(result.verdict, "white")
    title = f"[bold {style}]{result.verdict}[/]  [dim]{result.latency_ms} ms[/]"
    console.print(Panel(Markdown(result.content or "(no content)"), title=title, title_align="left", border_style=style))
    if result.events:
        table = Table(title="Guardrails that acted", title_justify="left", show_lines=False, expand=False)
        table.add_column("#", justify="right")
        table.add_column("Guardrail")
        table.add_column("Action")
        table.add_column("Detail", overflow="fold")
        for e in result.events:
            table.add_row(str(e.number), e.name, f"[{ACTION_STYLE.get(e.action, 'white')}]{e.action}[/]", escape(e.detail))
        console.print(table)


def ask_approval(tool_name: str, tool_args: dict) -> tuple[bool, str]:
    args = escape("\n".join(f"  {k}: {v}" for k, v in (tool_args or {}).items()))
    console.print(Panel(f"[bold]{tool_name}[/bold]\n{args}", title="[yellow]Approval required[/]", border_style="yellow"))
    if Confirm.ask("Approve this action?", default=False):
        return True, ""
    return False, Prompt.ask("Reason for rejection", default="Rejected by reviewer")


def show_log(audit: AuditLog, limit: int) -> None:
    table = Table(title=f"Last {limit} turns ({config.AUDIT_DB_FILE.name})", title_justify="left")
    for col in ("id", "time (UTC)", "user", "verdict", "input", "guardrails"):
        table.add_column(col, overflow="fold")
    for row in audit.recent_turns(limit):
        table.add_row(str(row["id"]), row["ts"][11:19], escape(row["user_id"] or ""),
                      f"[{VERDICT_STYLE.get(row['verdict'], 'white')}]{row['verdict']}[/]",
                      escape((row["input"] or "")[:60]), row["fired"] or "")
    console.print(table)


def show_stats(audit: AuditLog) -> None:
    stats = audit.stats()
    total = sum(stats["verdicts"].values()) or 1
    console.print("[bold]Verdicts:[/bold] " + ", ".join(f"{k} {v} ({v / total:.0%})" for k, v in stats["verdicts"].items()))
    table = Table(title="Guardrail firing counts", title_justify="left")
    for col in ("#", "Guardrail", "Action", "Count"):
        table.add_column(col)
    for number, name, action, count in stats["guardrails"]:
        table.add_row(str(number), name, action, str(count))
    console.print(table)


def show_guardrails() -> None:
    table = Table(title="30 guardrails in this agent", title_justify="left")
    table.add_column("#", justify="right")
    table.add_column("Guardrail")
    table.add_column("Stage")
    for number, name, stage in GUARDRAIL_MAP:
        table.add_row(str(number), name, stage)
    console.print(table)


def whoami(session: ChatSession) -> str:
    name = USERS.get(session.user_id, {}).get("name", "unknown")
    return f"user [bold]{escape(session.user_id)}[/bold] ({name}), role [bold]{session.role}[/bold], session {session.session_id}"


def run_cli(user_id: str = "patient_01") -> None:
    if not config.OPENAI_API_KEY:
        console.print("[red]OPENAI_API_KEY is missing.[/red] Copy .env.example to .env and add your key.")
        return

    agent, rbac = build_healthcare_agent()
    audit = AuditLog(config.AUDIT_DB_FILE)
    session = ChatSession(agent, rbac, audit, user_id)

    console.print(Panel(
        f"[bold]AcmeHealth Assistant[/bold] - Agno agent with 30 guardrails\n"
        f"models: main={config.MAIN_MODEL}, judge={config.JUDGE_MODEL}, moderation={config.MODERATION_MODEL}\n"
        f"{whoami(session)}\nType /help for commands.",
        border_style="blue",
    ))

    while True:
        try:
            message = Prompt.ask(f"\n[bold cyan]{escape(session.user_id)}[/]").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not message:
            continue

        if message.startswith("/"):
            cmd, _, arg = message.partition(" ")
            arg = arg.strip()
            if cmd in ("/quit", "/exit"):
                break
            elif cmd == "/help":
                console.print(HELP.format(users=", ".join(USERS)))
            elif cmd == "/whoami":
                console.print(whoami(session))
            elif cmd == "/user":
                if not arg:
                    console.print("Usage: /user <id>  (" + ", ".join(USERS) + "; unknown ids are treated as guests)")
                    continue
                session.switch_user(arg)
                console.print("Switched to " + whoami(session))
            elif cmd == "/new":
                session.new_session()
                console.print("New session: " + session.session_id)
            elif cmd == "/guardrails":
                show_guardrails()
            elif cmd == "/log":
                show_log(audit, int(arg) if arg.isdigit() else 10)
            elif cmd == "/stats":
                show_stats(audit)
            else:
                console.print(f"Unknown command {cmd}. Type /help.")
            continue

        try:
            with console.status("Thinking (running guardrails)..."):
                result = session.send(message)
            while result.verdict == "PAUSED":
                if any(rbac.is_allowed(session.user_id, r.tool_execution.tool_name) for r in result.pending_approvals):
                    show_result(result)
                result = session.resolve_approvals(result, ask_approval)
            show_result(result)
        except KeyboardInterrupt:
            console.print("[dim]Cancelled.[/dim]")
        except Exception as exc:
            console.print(f"[magenta]Unexpected error:[/magenta] {type(exc).__name__}: {exc}")

    console.print("Goodbye.")
