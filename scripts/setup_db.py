#!/usr/bin/env python3
"""Create or update the Change Desk store in the local Supabase Postgres, then prove the app login's limits.

Copied from the GTM pipeline (scripts/setup_run_log.py) and shaped for this build:
  1. Applies db/changedesk.sql, db/run_log.sql, db/views.sql and db/app_functions.sql as the
     database owner (inside the Supabase db container). Safe to run again.
  2. Creates the login changedesk_app. Its password is made here, written straight to .env as
     CHANGEDESK_DB_PASSWORD and never printed. Israel pastes it into the n8n Postgres credential.
  3. Grants that login read access to the changedesk schema and the checked write functions,
     nothing else: no insert, update or delete on any table, and no other schema.
  4. Loads pricing/claude_prices.json, sample/goals.json and, the first time only,
     settings/settings.json (after that the settings table is the one home: R14).
  5. Signs in as changedesk_app and checks what it can and cannot do.

  python scripts/setup_db.py            # all five steps
  python scripts/setup_db.py --check    # step 5 only

Exit codes: 0 done and every check passed, 1 a check failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

REPO = Path(__file__).resolve().parents[1]
ENV = REPO / ".env"
SQL_FILES = ["db/changedesk.sql", "db/run_log.sql", "db/views.sql", "db/app_functions.sql"]
PRICES = REPO / "pricing" / "claude_prices.json"
SETTINGS = REPO / "settings" / "settings.json"
GOALS = REPO / "sample" / "goals.json"
ROLE = "changedesk_app"
PASSWORD_KEY = "CHANGEDESK_DB_PASSWORD"
WRITE_FUNCTIONS = [
    "add_request(jsonb)", "log_triage(jsonb, jsonb, jsonb)", "confirm_lanes(jsonb)", "change_score(jsonb)",
    "decide(jsonb)", "log_drafts(jsonb, jsonb, jsonb)", "set_setting(text, jsonb, text, text)",
]
READ_FUNCTIONS = ["setting(text)", "setting_num(text)", "effort_points(numeric)", "ranked_standard(date)", "decide_list_at(date)"]


def db_settings() -> dict[str, str]:
    """Where the app login connects from the Mac. n8n uses host.docker.internal instead."""
    return {
        "container": os.environ.get("SUPABASE_DB_CONTAINER", "supabase_db_hubspot-ai-database"),
        "host": os.environ.get("CHANGEDESK_DB_HOST", "127.0.0.1"),
        "port": os.environ.get("CHANGEDESK_DB_PORT", "54322"),
        "dbname": os.environ.get("CHANGEDESK_DB_NAME", "postgres"),
        "user": ROLE,
    }


def ensure_password() -> str:
    """Return the app password from .env, making and saving one if there is none. Never printed."""
    current = (dotenv_values(ENV).get(PASSWORD_KEY) if ENV.exists() else None) or ""
    if current:
        return current
    password = secrets.token_urlsafe(24)  # letters, digits, - and _ only: safe inside a SQL literal
    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    if f"{PASSWORD_KEY}=" in text:
        lines = [f"{PASSWORD_KEY}={password}" if line.startswith(f"{PASSWORD_KEY}=") else line for line in text.splitlines()]
        text = "\n".join(lines) + "\n"
    else:
        text += ("" if text.endswith("\n") or not text else "\n")
        text += ("\n# The changedesk_app login (made by scripts/setup_db.py). Israel pastes it into the n8n "
                 f"Postgres credential \"Change Desk (Postgres)\".\n{PASSWORD_KEY}={password}\n")
    ENV.write_text(text, encoding="utf-8")
    ENV.chmod(0o600)
    return password


def psql(container: str, sql: str) -> str:
    """Run SQL as the owner inside the db container. The SQL goes in on stdin, so no secret is on a command line."""
    out = subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-q", "-At"],
        input=sql, capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip().replace(os.environ.get(PASSWORD_KEY, "\0"), "<hidden>") or "psql failed")
    return out.stdout


def role_sql(password: str) -> str:
    if not password.replace("-", "").replace("_", "").isalnum():
        raise ValueError("the app password must be letters, digits, - and _ only")
    grants_w = "\n".join(f"grant execute on function changedesk.{f} to {ROLE};" for f in WRITE_FUNCTIONS)
    grants_r = "\n".join(f"grant execute on function changedesk.{f} to {ROLE};" for f in READ_FUNCTIONS)
    return f"""
do $$
begin
  if not exists (select 1 from pg_roles where rolname = '{ROLE}') then
    create role {ROLE} login password '{password}' connection limit 5;
  else
    alter role {ROLE} login password '{password}' connection limit 5;
  end if;
end $$;
-- Nobody but the owner gets anything by default.
revoke all on schema changedesk from public;
revoke all on all tables in schema changedesk from public;
revoke all on all sequences in schema changedesk from public;
revoke all on all functions in schema changedesk from public;
do $$
declare r text;
begin
  foreach r in array array['anon', 'authenticated', 'service_role', '{ROLE}'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on schema changedesk from %I', r);
      execute format('revoke all on all tables in schema changedesk from %I', r);
      execute format('revoke all on all sequences in schema changedesk from %I', r);
      execute format('revoke all on all functions in schema changedesk from %I', r);
    end if;
  end loop;
end $$;
alter role {ROLE} set search_path = changedesk;
grant usage on schema changedesk to {ROLE};
grant select on all tables in schema changedesk to {ROLE};
{grants_w}
{grants_r}
"""


def lit(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def jsonb_lit(v) -> str:
    return lit(json.dumps(v)) + "::jsonb"


def prices_sql(prices: dict) -> str:
    rows = ["(" + ", ".join(lit(x) for x in (model, p["input"], p["output"], p["long_prompt_over_tokens"], p["long_input"],
                                              p["long_output"], p["read_on"], p["source"])) + ")"
            for model, p in prices["models"].items()]
    return (
        "insert into changedesk.model_prices (model, input_per_mtok, output_per_mtok, long_prompt_over_tokens, "
        "long_input_per_mtok, long_output_per_mtok, read_on, source) values\n  " + ",\n  ".join(rows) + "\n"
        "on conflict (model) do update set input_per_mtok = excluded.input_per_mtok, output_per_mtok = excluded.output_per_mtok, "
        "long_prompt_over_tokens = excluded.long_prompt_over_tokens, long_input_per_mtok = excluded.long_input_per_mtok, "
        "long_output_per_mtok = excluded.long_output_per_mtok, read_on = excluded.read_on, source = excluded.source;\n"
    )


def settings_sql(settings: dict) -> str:
    """First load only: a setting already in the table is never overwritten from the file."""
    rows = ["(" + ", ".join([lit(s["key"]), jsonb_lit(s["value"]), lit(s["description"]), lit(s["source"]),
                             lit("setup_db.py"), "now()", lit("starting value, " + s["source"])]) + ")"
            for s in settings["settings"]]
    return ("insert into changedesk.settings (key, value, description, source, changed_by, changed_at, why) values\n  "
            + ",\n  ".join(rows) + "\non conflict (key) do nothing;\n")


def goals_sql(goals: dict) -> str:
    rows = ["(" + ", ".join(lit(g[k]) for k in ("goal_id", "title", "description", "owner_role")) + ")" for g in goals["goals"]]
    return ("insert into changedesk.goals (goal_id, title, description, owner_role) values\n  " + ",\n  ".join(rows)
            + "\non conflict (goal_id) do update set title = excluded.title, description = excluded.description, "
              "owner_role = excluded.owner_role;\n")


def connect(settings: dict[str, str], password: str, autocommit: bool = True):
    import psycopg

    return psycopg.connect(host=settings["host"], port=settings["port"], dbname=settings["dbname"],
                           user=settings["user"], password=password, connect_timeout=5, autocommit=autocommit)


def check_limits(settings: dict[str, str], password: str) -> list[tuple[str, bool]]:
    """What the app login can and cannot do. Each check is (description, passed). Nothing it tries is kept."""
    import psycopg

    results = []
    with connect(settings, password, autocommit=False) as conn:
        def denied(label: str, sql: str):
            conn.execute("savepoint probe")
            try:
                conn.execute(sql)
                results.append((label, False))
            except psycopg.errors.InsufficientPrivilege:
                results.append((label, True))
            conn.execute("rollback to savepoint probe")

        conn.execute("select count(*) from changedesk.requests").fetchone()
        results.append(("can read the requests table", True))
        conn.execute("select count(*) from changedesk.decide_list").fetchone()
        results.append(("can read the decide list view", True))
        new_id = conn.execute("select changedesk.add_request(%s::jsonb)", (json.dumps(
            {"requester_role": "Setup check", "title": "Setup check request", "body": "Made by setup_db.py --check and rolled back."}),)).fetchone()[0]
        history = conn.execute("select count(*) from changedesk.status_history where request_id = %s", (new_id,)).fetchone()[0]
        results.append(("can add a request through add_request, which writes its status history (rolled back)", history == 1))
        denied("cannot insert into requests directly", "insert into changedesk.requests (request_id) values ('CD-9999')")
        denied("cannot update a request directly", "update changedesk.requests set lane = 'urgent'")
        denied("cannot delete status history", "delete from changedesk.status_history")
        denied("cannot change a setting directly", "update changedesk.settings set value = '1'::jsonb")
        denied("cannot insert into the run log directly", "insert into changedesk.run_log (call_id) values ('x')")
        denied("cannot create a table in changedesk", "create table changedesk.probe (x int)")
        # pg_tables lists every table whatever the login may read (information_schema would hide them).
        for schema in ("gtm_v2", "ec", "public"):
            other = conn.execute(
                "select quote_ident(schemaname) || '.' || quote_ident(tablename) from pg_tables "
                "where schemaname = %s order by tablename limit 1", (schema,)
            ).fetchone()
            if other:
                denied(f"cannot read the {schema} schema ({other[0]})", f"select 1 from {other[0]} limit 1")
        conn.rollback()
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="only sign in as the app login and check its limits")
    args = ap.parse_args(argv)
    load_dotenv(ENV)
    settings = db_settings()
    try:
        password = ensure_password()
        os.environ[PASSWORD_KEY] = password
        if not args.check:
            for rel in SQL_FILES:
                psql(settings["container"], (REPO / rel).read_text(encoding="utf-8"))
                print(f"Applied {rel}.")
            psql(settings["container"], role_sql(password))
            print(f"Login {ROLE} ready: reads schema changedesk, writes through {len(WRITE_FUNCTIONS)} checked functions. "
                  f"Password is in .env as {PASSWORD_KEY} (length {len(password)}).")
            prices = json.loads(PRICES.read_text(encoding="utf-8"))
            psql(settings["container"], prices_sql(prices))
            goals = json.loads(GOALS.read_text(encoding="utf-8"))
            psql(settings["container"], goals_sql(goals))
            before = int(psql(settings["container"], "select count(*) from changedesk.settings;").strip())
            conf = json.loads(SETTINGS.read_text(encoding="utf-8"))
            psql(settings["container"], settings_sql(conf))
            after = int(psql(settings["container"], "select count(*) from changedesk.settings;").strip())
            print(f"Loaded {len(prices['models'])} model prices and {len(goals['goals'])} goals; "
                  f"settings: {after - before} added, {before} already in the table and left as they are.")
        results = check_limits(settings, password)
    except (RuntimeError, OSError, ValueError) as e:
        print(f"CANNOT RUN {e}")
        return 2
    except Exception as e:  # psycopg connection errors
        print(f"CANNOT RUN {type(e).__name__}: {str(e).replace(os.environ.get(PASSWORD_KEY, chr(0)), '<hidden>')}")
        return 2
    for label, ok in results:
        print(f"{'PASS' if ok else 'FAIL'} {ROLE} {label}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
