from datetime import date, datetime, timedelta, timezone
from flask import Flask, jsonify, request, render_template

import db

app = Flask(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def today_local():
    """Today in India time (the server itself runs in UTC)."""
    return datetime.now(IST).date()


def init_db():
    """One round trip: create tables, seed starter habits once, clean duplicates."""
    db.run(
        [
            (
                """CREATE TABLE IF NOT EXISTS habits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    icon TEXT DEFAULT '⭐',
                    category TEXT DEFAULT 'general',
                    sort_order INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (date('now'))
                )""",
                None,
            ),
            (
                """CREATE TABLE IF NOT EXISTS habit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    habit_id INTEGER NOT NULL,
                    log_date TEXT NOT NULL,
                    status INTEGER DEFAULT 0,
                    UNIQUE(habit_id, log_date)
                )""",
                None,
            ),
            # Starter habits, added in ONE atomic statement and only if the table
            # is empty (two requests starting at once can't both seed).
            (
                """WITH v(name, icon, category, sort_order) AS (VALUES
                    ('5hr sleep', '😴', 'wellness', 0),
                    ('Early morning', '🌅', 'morning', 1),
                    ('Shower', '🚿', 'wellness', 2),
                    ('Pray', '🙏', 'mindfulness', 3),
                    ('Drink water', '💧', 'wellness', 4),
                    ('Breakfast', '🍳', 'meals', 5),
                    ('Exercise', '🏋️', 'fitness', 6),
                    ('Lunch', '🍲', 'meals', 7),
                    ('Self study', '📚', 'learning', 8),
                    ('Work on skills', '🛠️', 'learning', 9),
                    ('Dinner', '🍽️', 'meals', 10),
                    ('No porn', '🚫', 'discipline', 11))
                   INSERT INTO habits (name, icon, category, sort_order)
                   SELECT name, icon, category, sort_order FROM v
                   WHERE (SELECT COUNT(*) FROM habits) = 0""",
                None,
            ),
            # Remove exact duplicates left by an earlier double-seed (keeps oldest).
            (
                """DELETE FROM habits WHERE id NOT IN
                   (SELECT MIN(id) FROM habits GROUP BY name, category, sort_order)""",
                None,
            ),
            ("DELETE FROM habit_logs WHERE habit_id NOT IN (SELECT id FROM habits)", None),
        ]
    )


def week_bounds(anchor: date):
    monday = anchor - timedelta(days=anchor.weekday())
    return monday, monday + timedelta(days=6)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/today")
def today():
    return jsonify({"today": today_local().isoformat()})


def streaks_from(done_dates):
    """Current streak per habit. Counts back from today, or from yesterday if
    today isn't ticked yet (so the streak doesn't show 0 each morning)."""
    t = today_local()
    result = {}
    for hid, dates in done_dates.items():
        cursor = t if t in dates else t - timedelta(days=1)
        n = 0
        while cursor in dates:
            n += 1
            cursor -= timedelta(days=1)
        result[hid] = n
    return result


@app.route("/api/week")
def get_week():
    ref = request.args.get("date")
    anchor = date.fromisoformat(ref) if ref else today_local()
    start, end = week_bounds(anchor)

    # One round trip for everything this page needs.
    habits, logs, done = db.run(
        [
            ("SELECT * FROM habits WHERE is_active=1 ORDER BY sort_order", None),
            (
                "SELECT habit_id, log_date, status FROM habit_logs WHERE log_date BETWEEN ? AND ?",
                [start.isoformat(), end.isoformat()],
            ),
            (
                "SELECT habit_id, log_date FROM habit_logs WHERE status=1 AND log_date<=?",
                [today_local().isoformat()],
            ),
        ]
    )
    log_map = {(r["habit_id"], r["log_date"]): r["status"] for r in logs}

    done_dates = {}
    for r in done:
        done_dates.setdefault(r["habit_id"], set()).add(date.fromisoformat(r["log_date"]))
    streaks = streaks_from(done_dates)

    days = [(start + timedelta(days=i)).isoformat() for i in range(7)]

    result = []
    for h in habits:
        vals = [log_map.get((h["id"], d), 0) for d in days]
        result.append(
            {
                "id": h["id"],
                "name": h["name"],
                "icon": h["icon"],
                "category": h["category"],
                "values": vals,
                "pct": round(sum(vals) / 7 * 100),
                "streak": streaks.get(h["id"], 0),
            }
        )

    return jsonify(
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": days,
            "today": today_local().isoformat(),
            "habits": result,
        }
    )


@app.route("/api/toggle", methods=["POST"])
def toggle():
    data = request.get_json()
    habit_id, log_date = data["habit_id"], data["date"]
    want = data.get("status")
    if want is not None:
        # Explicit status from the browser: safe to repeat, one round trip.
        status = 1 if want else 0
        db.execute(
            """INSERT INTO habit_logs (habit_id, log_date, status) VALUES (?,?,?)
               ON CONFLICT(habit_id, log_date) DO UPDATE SET status = excluded.status""",
            [habit_id, log_date, status],
        )
        return jsonify({"status": status})
    _, rows = db.run(
        [
            (
                """INSERT INTO habit_logs (habit_id, log_date, status) VALUES (?,?,1)
                   ON CONFLICT(habit_id, log_date) DO UPDATE SET status = 1 - status""",
                [habit_id, log_date],
            ),
            ("SELECT status FROM habit_logs WHERE habit_id=? AND log_date=?", [habit_id, log_date]),
        ]
    )
    return jsonify({"status": rows[0]["status"] if rows else 0})


@app.route("/api/habits", methods=["POST"])
def add_habit():
    data = request.get_json()
    _, rows = db.run(
        [
            (
                """INSERT INTO habits (name, icon, category, sort_order)
                   VALUES (?,?,?, (SELECT COALESCE(MAX(sort_order),-1)+1 FROM habits))""",
                [data["name"], data.get("icon", "⭐"), data.get("category", "general")],
            ),
            ("SELECT last_insert_rowid() AS id", None),
        ]
    )
    return jsonify({"id": rows[0]["id"]})


@app.route("/api/habits/<int:habit_id>", methods=["DELETE"])
def delete_habit(habit_id):
    db.execute("UPDATE habits SET is_active=0 WHERE id=?", [habit_id])
    return jsonify({"ok": True})


@app.route("/api/weekly-stats")
def weekly_stats():
    weeks = int(request.args.get("weeks", 8))
    monday = today_local() - timedelta(days=today_local().weekday())
    first = monday - timedelta(days=7 * (weeks - 1))

    total_rows, done_rows = db.run(
        [
            ("SELECT COUNT(*) AS c FROM habits WHERE is_active=1", None),
            (
                """SELECT l.log_date FROM habit_logs l
                   JOIN habits h ON h.id = l.habit_id
                   WHERE l.status=1 AND h.is_active=1 AND l.log_date BETWEEN ? AND ?""",
                [first.isoformat(), (monday + timedelta(days=6)).isoformat()],
            ),
        ]
    )
    total = total_rows[0]["c"]
    done_by_date = {}
    for r in done_rows:
        done_by_date[r["log_date"]] = done_by_date.get(r["log_date"], 0) + 1

    stats = []
    for i in range(weeks - 1, -1, -1):
        w_start = monday - timedelta(days=7 * i)
        done = sum(
            done_by_date.get((w_start + timedelta(days=d)).isoformat(), 0) for d in range(7)
        )
        possible = total * 7
        stats.append(
            {"label": w_start.strftime("%b %d"), "pct": round(done / possible * 100) if possible else 0}
        )
    return jsonify(stats)


_db_ready = False


@app.before_request
def ensure_db():
    """Create tables on the first request; report DB problems instead of crashing."""
    global _db_ready
    if _db_ready:
        return None
    try:
        init_db()
        _db_ready = True
    except Exception as e:  # shows the real reason in the browser and Vercel logs
        app.logger.exception("Database init failed")
        return jsonify({"error": "database init failed", "detail": str(e)}), 500
    return None


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", debug=debug, port=port)
