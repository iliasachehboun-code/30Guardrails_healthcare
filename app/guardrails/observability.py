"""#17 Observability: persist every turn and every guardrail decision to SQLite."""

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from app.events import GuardrailEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    user_id TEXT,
    run_id TEXT,
    verdict TEXT NOT NULL,
    latency_ms INTEGER,
    input TEXT,
    output TEXT,
    tools TEXT
);
CREATE TABLE IF NOT EXISTS guardrail_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id INTEGER NOT NULL REFERENCES turns(id),
    number INTEGER NOT NULL,
    name TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT
);
"""


class AuditLog:
    def __init__(self, db_file: Path):
        self.db_file = db_file
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_file)

    def log_turn(
        self,
        *,
        session_id: str,
        user_id: str,
        run_id: Optional[str],
        verdict: str,
        latency_ms: int,
        input_text: str,
        output_text: str,
        tools: List[str],
        events: List[GuardrailEvent],
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO turns (ts, session_id, user_id, run_id, verdict, latency_ms, input, output, tools) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    session_id,
                    user_id,
                    run_id,
                    verdict,
                    latency_ms,
                    input_text[:2000],
                    output_text[:4000],
                    json.dumps(tools),
                ),
            )
            turn_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO guardrail_events (turn_id, number, name, action, detail) VALUES (?, ?, ?, ?, ?)",
                [(turn_id, e.number, e.name, e.action, e.detail) for e in events],
            )
        return turn_id

    def recent_turns(self, limit: int = 10) -> List[sqlite3.Row]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                "SELECT t.*, (SELECT group_concat('#' || number || ' ' || action, ', ') FROM guardrail_events "
                "WHERE turn_id = t.id) AS fired FROM turns t ORDER BY t.id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def stats(self) -> dict:
        with self._connect() as conn:
            verdicts = Counter(dict(conn.execute("SELECT verdict, COUNT(*) FROM turns GROUP BY verdict").fetchall()))
            guards = conn.execute(
                "SELECT number, name, action, COUNT(*) FROM guardrail_events GROUP BY number, name, action "
                "ORDER BY COUNT(*) DESC"
            ).fetchall()
        return {"verdicts": verdicts, "guardrails": guards}
