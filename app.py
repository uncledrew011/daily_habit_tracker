import random
from datetime import date, timedelta
from flask import Flask, jsonify, request, render_template

import db

app = Flask(__name__)


def init_db():
    db.execute(
        """CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '⭐',
            category TEXT DEFAULT 'general',
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (date('now'))
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            status INTEGER DEFAULT 0,
            UNIQUE(habit_id, log_date)
        )"""
    )

    count = db.query("SELECT COUNT(*) c FROM habits")[0]["c"]
    if count == 0:
        sample_habits = [
            ("5hr sleep", "😴", "wellness", 0),
            ("Early morning", "🌅", "morning", 1),
            ("Shower", "🚿", "wellness", 2),
            ("Pray", "🙏", "mindfulness", 3),
            ("Drink water", "💧", "wellness", 4),
            ("Breakfast", "🍳", "meals", 5),
            ("Exercise", "🏋️", "fitness", 6),
            ("Lunch", "🍲", "meals", 7),
            ("Self study", "📚", "learning", 8),
            ("Work on skills", "🛠️", "learning", 9),
            ("Dinner", "🍽️", "meals", 10),
            ("No porn", "🚫", "discipline", 11),
        ]
        habit_ids = []
        for name, icon, category, order in sample_habits:
            db.execute(
                "INSERT INTO habits (name, icon, category, sort_order) VALUES (?,?,?,?)",
                [name, icon, category, order],
            )
            habit_ids.append(db.last_insert_id())

        random.seed(7)
        today = date.today()
        for offset in range(56, -1, -1):
            d = today - timedelta(days=offset)
            for hid in habit_ids:
                if random.random() < 0.68:
                    db.execute(
                        "INSERT OR IGNORE INTO habit_logs (habit_id, log_date, status) VALUES (?,?,1)",
                        [hid, d.isoformat()],
                    )


def week_bounds(anchor: date):
    monday = anchor - timedelta(days=anchor.weekday())
    return monday, monday + timedelta(days=6)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/today")
def today():
    return jsonify({"today": date.today().isoformat()})


@app.route("/api/week")
def get_week():
    ref = request.args.get("date")
    anchor = date.fromisoformat(ref) if ref else date.today()
    start, end = week_bounds(anchor)

    habits = db.query("SELECT * FROM habits WHERE is_active=1 ORDER BY sort_order")
    logs = db.query(
        "SELECT * FROM habit_logs WHERE log_date BETWEEN ? AND ?",
        [start.isoformat(), end.isoformat()],
    )
    log_map = {(r["habit_id"], r["log_date"]): r["status"] for r in logs}

    days = [(start + timedelta(days=i)).isoformat() for i in range(7)]

    result = []
    for h in habits:
        vals = [log_map.get((h["id"], d), 0) for d in days]
        pct = round(sum(vals) / 7 * 100)
        result.append(
            {
                "id": h["id"],
                "name": h["name"],
                "icon": h["icon"],
                "category": h["category"],
                "values": vals,
                "pct": pct,
                "streak": current_streak(h["id"]),
            }
        )

    return jsonify(
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": days,
            "today": date.today().isoformat(),
            "habits": result,
        }
    )


def current_streak(habit_id):
    rows = db.query(
        "SELECT log_date FROM habit_logs WHERE habit_id=? AND status=1 ORDER BY log_date DESC",
        [habit_id],
    )
    dates = {date.fromisoformat(r["log_date"]) for r in rows}
    streak = 0
    cursor = date.today()
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@app.route("/api/toggle", methods=["POST"])
def toggle():
    data = request.get_json()
    habit_id, log_date = data["habit_id"], data["date"]
    row = db.query(
        "SELECT status FROM habit_logs WHERE habit_id=? AND log_date=?",
        [habit_id, log_date],
    )
    new_status = 0 if row and row[0]["status"] else 1
    db.execute(
        """INSERT INTO habit_logs (habit_id, log_date, status) VALUES (?,?,?)
           ON CONFLICT(habit_id, log_date) DO UPDATE SET status=?""",
        [habit_id, log_date, new_status, new_status],
    )
    return jsonify({"status": new_status})


@app.route("/api/habits", methods=["POST"])
def add_habit():
    data = request.get_json()
    max_order = db.query("SELECT COALESCE(MAX(sort_order),-1) m FROM habits")[0]["m"]
    db.execute(
        "INSERT INTO habits (name, icon, category, sort_order) VALUES (?,?,?,?)",
        [data["name"], data.get("icon", "⭐"), data.get("category", "general"), max_order + 1],
    )
    return jsonify({"id": db.last_insert_id()})


@app.route("/api/habits/<int:habit_id>", methods=["DELETE"])
def delete_habit(habit_id):
    db.execute("UPDATE habits SET is_active=0 WHERE id=?", [habit_id])
    return jsonify({"ok": True})


@app.route("/api/weekly-stats")
def weekly_stats():
    weeks = int(request.args.get("weeks", 8))
    today_d = date.today()
    monday = today_d - timedelta(days=today_d.weekday())

    stats = []
    total = db.query("SELECT COUNT(*) c FROM habits WHERE is_active=1")[0]["c"]
    for i in range(weeks - 1, -1, -1):
        w_start = monday - timedelta(days=7 * i)
        w_end = w_start + timedelta(days=6)
        done = db.query(
            "SELECT COUNT(*) c FROM habit_logs WHERE status=1 AND log_date BETWEEN ? AND ?",
            [w_start.isoformat(), w_end.isoformat()],
        )[0]["c"]
        possible = total * 7 if total else 1
        pct = round(done / possible * 100) if possible else 0
        stats.append({"label": w_start.strftime("%b %d"), "pct": pct})

    return jsonify(stats)


# Runs on import too (needed for gunicorn / Vercel, where __main__ never executes)
init_db()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", debug=debug, port=port)
