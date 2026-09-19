import sqlite3
from datetime import datetime, timezone

from config import MEMORY_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(MEMORY_DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def add_fact(fact: str) -> None:
    fact = fact.strip()
    if not fact:
        return
    conn = _connect()
    try:
        existing = [row[0] for row in conn.execute("SELECT fact FROM facts")]
        for other in existing:
            if fact.lower() == other.lower() or fact.lower() in other.lower() or other.lower() in fact.lower():
                return
        conn.execute(
            "INSERT INTO facts (fact, created_at) VALUES (?, ?)",
            (fact, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_facts(limit: int = 50) -> list[str]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT fact FROM facts ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def log_turn(role: str, content: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO conversation_log (role, content, timestamp) VALUES (?, ?, ?)",
            (role, content, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    add_fact("mora em São Paulo")
    add_fact("mora em São Paulo")  # duplicado, não deve inserir de novo
    print(get_facts())
