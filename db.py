"""
Database layer, chosen by environment variables:

- No TURSO_DATABASE_URL: plain local SQLite file (local development).
- TURSO_DATABASE_URL + TURSO_AUTH_TOKEN set: Turso over its HTTP API.

Speed matters on Vercel: every round trip to Turso costs 0.3-1s. So the main
entry point is run(), which sends SEVERAL statements in ONE request, and the
HTTP session is reused (keep-alive) so TLS is not renegotiated every call.

Nothing connects at import time, so a bad URL/token shows up as a readable
error instead of crashing the whole function.
"""
import os

TURSO_URL = (os.environ.get("TURSO_DATABASE_URL") or "").strip()
TURSO_TOKEN = (os.environ.get("TURSO_AUTH_TOKEN") or "").strip()

USING_TURSO = bool(TURSO_URL)


def execute(sql, params=None):
    """Run one statement, no rows back."""
    run([(sql, params)])


def query(sql, params=None):
    """Run one SELECT, return a list of dicts."""
    return run([(sql, params)])[0]


if USING_TURSO:
    import requests

    # libsql://name.turso.io -> https://name.turso.io
    _BASE = TURSO_URL
    for _prefix in ("libsql://", "wss://", "ws://"):
        if _BASE.startswith(_prefix):
            _BASE = "https://" + _BASE[len(_prefix):]
    _BASE = _BASE.rstrip("/")

    _session = requests.Session()

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

    def run(statements):
        """statements: list of (sql, params). Returns one list-of-dicts per statement."""
        if not TURSO_TOKEN.startswith("eyJ"):
            raise RuntimeError(
                "TURSO_AUTH_TOKEN is missing or is not a token (a real token starts "
                "with 'eyJ' and contains no ':' or spaces). Re-create it in Turso, "
                "paste only the token into Vercel, then Redeploy."
            )
        reqs = [
            {"type": "execute", "stmt": {"sql": sql, "args": [_arg(p) for p in (params or [])]}}
            for sql, params in statements
        ]
        reqs.append({"type": "close"})
        try:
            resp = _session.post(
                _BASE + "/v2/pipeline",
                json={"requests": reqs},
                headers={"Authorization": "Bearer " + TURSO_TOKEN},
                timeout=20,
            )
        except requests.RequestException as e:
            raise RuntimeError(f"Cannot reach Turso at {_BASE}: {e}") from None
        if resp.status_code != 200:
            raise RuntimeError(f"Turso HTTP {resp.status_code}: {resp.text[:300]}")

        out = []
        for item in resp.json()["results"][: len(statements)]:
            if item.get("type") == "error":
                raise RuntimeError("Turso SQL error: " + item["error"].get("message", "unknown"))
            result = item["response"]["result"]
            cols = [c["name"] for c in result["cols"]]
            out.append([dict(zip(cols, (_val(c) for c in row))) for row in result["rows"]])
        return out

elif os.environ.get("VERCEL"):
    # On Vercel the disk is read-only, so a local SQLite file can never work.
    # Fail loudly instead of silently using a stale bundled copy.
    def run(statements):
        raise RuntimeError(
            "TURSO_DATABASE_URL is empty or not set in this Vercel deployment. "
            "Add it under Settings > Environment Variables (Production), then Redeploy."
        )

else:
    import sqlite3

    DB_PATH = os.environ.get("SQLITE_PATH", "habit_tracker.db")
    _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    _conn.row_factory = sqlite3.Row

    def run(statements):
        out = []
        for sql, params in statements:
            cur = _conn.execute(sql, params or [])
            out.append([dict(r) for r in cur.fetchall()] if cur.description else [])
        _conn.commit()
        return out
