# Thread — daily habit tracker

A habit tracker with a weekly checklist sheet, streaks, and a consistency
graph across weeks. Runs on Flask + SQLite, comes pre-seeded with ~8 weeks
of sample data so it looks alive on first run.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5050** in your browser.

The database file `habit_tracker.db` is created automatically on first run
and seeded with 5 sample habits and realistic history. Delete that file
any time to reset.

## What's inside

- `app.py` — Flask server + all API routes + SQLite schema
- `templates/index.html` — the page structure
- `static/css/style.css` — the visual design (dark theme, "thread" motif)
- `static/js/app.js` — fetches data, renders the sheet, handles clicks, draws the chart

## How it behaves

- **Today's column** is detected automatically from the server's clock and
  highlighted — it moves forward on its own each day, no manual update needed.
- **Click any dot**, past or present, to toggle a habit done/not done for
  that day. Past weeks are fully editable.
- Every toggle updates `habit_logs` in SQLite immediately, and the streak,
  weekly %, and the 8-week chart all recalculate live from that table —
  nothing is cached or hardcoded.
- **Add a habit** using the row at the bottom of the sheet.
- Use the **◂ ▸** arrows to browse past/future weeks, or **Today** to jump back.

## Data model

```
habits        (id, name, icon, category, sort_order, is_active)
habit_logs    (id, habit_id, log_date, status)   -- one row per day per habit
```

Weekly/monthly/yearly numbers are never stored directly — they're computed
on the fly from `habit_logs`, so editing history always keeps every rollup
correct.
