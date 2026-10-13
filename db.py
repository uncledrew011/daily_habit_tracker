"""
Database layer, chosen by environment variables:

- No TURSO_DATABASE_URL: plain local SQLite file (local development).
- TURSO_DATABASE_URL + TURSO_AUTH_TOKEN set: Turso over its HTTP API.

The Turso path uses only the Python standard library (no libsql-client), so
there is nothing native or deprecated to break on Vercel. Nothing connects at
import time, so a bad URL/token shows up as a readable error instead of
crashing the whole function.
"""
import json
import os
import urllib.error
import urllib.request

TURSO_URL = (os.environ.get("TURSO_DATABASE_URL") or "").strip()
TURSO_TOKEN = (os.environ.get("TURSO_AUTH_TOKEN") or "").strip()

USING_TURSO = bool(TURSO_URL)

_last_id = None

if USING_TURSO:
    # libsql://name.turso.io -> https://name.turso.io
    _BASE = TURSO_URL
    for prefix in ("libsql://", "wss://", "ws://"):
        if _BASE.startswith(prefix):
            _BASE = "https://" + _BASE[len(prefix):]
    _BASE = _BASE.rstrip("/")

    def _arg(v):
        if v is None:
            return {"type": "null"}
        if isinstance(v, bool):
            return {"type": "integer", "value": str(int(v))}
        if isinstance(v, int):
            return {"type": "integer", "value": str(v)}
        if isinstance(v, float):
            return {"type": "float", "value": v}
        return {"type": "text", "value": str(v)}

    def _val(cell):
        t = cell.get("type")
        if t == "null":
            return None
        if t == "integer":
            return int(cell["value"])
        if t == "float":
            return float(cell["value"])
        return cell.get("value")

    def _run(sql, params):
        body = {
            "requests": [
                {"type": "execute", "stmt": {"sql": sql, "args": [_arg(p) for p in (params or [])]}},
                {"type": "close"},
            ]
        }
        req = urllib.request.Request(
            _BASE + "/v2/pipeline",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + TURSO_TOKEN,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Turso HTTP {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"Cannot reach Turso at {_BASE}: {e.reason}") from None

        first = data["results"][0]
        if first.get("type") == "error":
            raise RuntimeError("Turso SQL error: " + first["error"].get("message", "unknown"))
        return first["response"]["result"]

    def execute(sql, params=None):
        global _last_id
        result = _run(sql, params)
        rid = result.get("last_insert_rowid")
        if rid is not None:
            _last_id = int(rid)

    def query(sql, params=None):
        result = _run(sql, params)
        cols = [c["name"] for c in result["cols"]]
        return [dict(zip(cols, (_val(c) for c in row))) for row in result["rows"]]

    def last_insert_id():
        return _last_id

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
