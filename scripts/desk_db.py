"""Connect to the Change Desk store as the app's own login (changedesk_app), and read what the engines need.

The login reads the changedesk schema and writes only through its checked functions (db/app_functions.sql).
Its password is in .env (CHANGEDESK_DB_PASSWORD, made by scripts/setup_db.py) and is never printed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[1]
ENV = REPO / ".env"


def password() -> str:
    value = (dotenv_values(ENV).get("CHANGEDESK_DB_PASSWORD") if ENV.exists() else None) or ""
    if not value:
        raise LookupError("CHANGEDESK_DB_PASSWORD is not in .env: run python scripts/setup_db.py")
    return value


def connect(autocommit: bool = True):
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(
        host=os.environ.get("CHANGEDESK_DB_HOST", "127.0.0.1"), port=os.environ.get("CHANGEDESK_DB_PORT", "54322"),
        dbname=os.environ.get("CHANGEDESK_DB_NAME", "postgres"), user="changedesk_app", password=password(),
        connect_timeout=5, autocommit=autocommit, row_factory=dict_row,
    )


def plain(v):
    """Rows as the engines expect them: dates and times as ISO text, numbers as numbers."""
    from datetime import date, datetime
    from decimal import Decimal

    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat().replace("+00:00", "Z")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [plain(x) for x in v]
    return v


def rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    return [plain(dict(r)) for r in conn.execute(sql, params).fetchall()]


def settings(conn) -> list[dict]:
    return rows(conn, "select key, value from changedesk.settings order by key")


def goals(conn) -> list[dict]:
    return rows(conn, "select goal_id, title, description, active from changedesk.goals where active order by goal_id")


def call_function(conn, sql: str, *payloads) -> object:
    return conn.execute(sql, tuple(json.dumps(p, default=str) for p in payloads)).fetchone()
