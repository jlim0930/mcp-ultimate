import os
import pathlib
import re
import sqlite3

DB_DIR = pathlib.Path(os.environ.get("SANDBOX_WORKSPACE", "/workspace")).resolve() / ".db"
DB_DIR.mkdir(parents=True, exist_ok=True)

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _db_path(name: str) -> pathlib.Path:
    if not _NAME_RE.match(name):
        raise ValueError(f"invalid database name '{name}': use only letters, numbers, _, -")
    return DB_DIR / f"{name}.db"


def _connect(name: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(name))
    conn.row_factory = sqlite3.Row
    return conn


def db_query(sql: str, params: list | None = None, database: str = "default") -> str:
    """Run a read-only query (SELECT/PRAGMA/WITH) against a SQLite database in the
    sandbox workspace and return the rows. Use db_execute for writes.
    """
    if not sql.strip().lower().startswith(("select", "pragma", "with")):
        return "error: db_query only runs SELECT/PRAGMA/WITH statements -- use db_execute for writes"
    try:
        with _connect(database) as conn:
            rows = conn.execute(sql, params or []).fetchall()
    except (sqlite3.Error, ValueError) as e:
        return f"error: {e}"

    if not rows:
        return "(no rows)"

    cols = rows[0].keys()
    lines = [" | ".join(cols)]
    lines += [" | ".join(str(r[c]) for c in cols) for r in rows]
    return "\n".join(lines)


def db_execute(sql: str, params: list | None = None, database: str = "default") -> str:
    """Run a write statement (CREATE/INSERT/UPDATE/DELETE/etc) against a SQLite
    database in the sandbox workspace. The database file is created on first use.
    """
    try:
        with _connect(database) as conn:
            cur = conn.execute(sql, params or [])
            conn.commit()
            return f"ok: {cur.rowcount} row(s) affected"
    except (sqlite3.Error, ValueError) as e:
        return f"error: {e}"


def db_list_tables(database: str = "default") -> str:
    """List tables in a SQLite database in the sandbox workspace."""
    try:
        with _connect(database) as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    except (sqlite3.Error, ValueError) as e:
        return f"error: {e}"
    if not rows:
        return "(no tables)"
    return "\n".join(r["name"] for r in rows)


def db_schema(table: str, database: str = "default") -> str:
    """Show the CREATE TABLE statement for a table in a SQLite database in the sandbox workspace."""
    try:
        with _connect(database) as conn:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", [table]
            ).fetchone()
    except (sqlite3.Error, ValueError) as e:
        return f"error: {e}"
    if not row:
        return f"error: no such table '{table}'"
    return row["sql"]


def register(mcp):
    mcp.tool()(db_query)
    mcp.tool()(db_execute)
    mcp.tool()(db_list_tables)
    mcp.tool()(db_schema)
