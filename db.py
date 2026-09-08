"""
Database layer that works two ways, controlled entirely by environment variables:

- Locally (no TURSO_DATABASE_URL set): uses a plain SQLite file, same as before.
- On Vercel (TURSO_DATABASE_URL + TURSO_AUTH_TOKEN set): uses Turso, a hosted
  SQLite-compatible database, over HTTP. Same SQL syntax either way.

Every function returns/accepts plain dicts and lists, so app.py never needs
to know which backend is active.
"""
import os

TURSO_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

USING_TURSO = bool(TURSO_URL)

if USING_TURSO:
    import libsql_client

    _client = libsql_client.create_client_sync(url=TURSO_URL, auth_token=TURSO_TOKEN)

    def execute(sql, params=None):
        """Run a statement that doesn't need rows back (INSERT/UPDATE/CREATE)."""
        _client.execute(sql, params or [])

    def query(sql, params=None):
        """Run a SELECT and return a list of dicts."""
        rs = _client.execute(sql, params or [])
        return [dict(zip(rs.columns, row)) for row in rs.rows]

    def last_insert_id():
        rs = _client.execute("SELECT last_insert_rowid() AS id", [])
        return rs.rows[0][0]

else:
    import sqlite3

    DB_PATH = os.environ.get("SQLITE_PATH", "habit_tracker.db")
    _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    _conn.row_factory = sqlite3.Row

    def execute(sql, params=None):
        _conn.execute(sql, params or [])
        _conn.commit()

    def query(sql, params=None):
        cur = _conn.execute(sql, params or [])
        return [dict(r) for r in cur.fetchall()]

    def last_insert_id():
        cur = _conn.execute("SELECT last_insert_rowid() AS id")
        return cur.fetchone()[0]
