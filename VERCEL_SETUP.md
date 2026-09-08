# Deploying to Vercel (with Turso for persistent storage)

Vercel's filesystem is temporary — it resets on every deploy and often between
requests. A local SQLite file will NOT survive there. This project already
handles that: if `TURSO_DATABASE_URL` is set, it talks to **Turso** (a free,
SQLite-compatible cloud database) instead of a local file. Same SQL, no
rewrite needed on your side.

## 1. Create a free Turso database

1. Go to **turso.tech** → sign up (GitHub login is fine) → free tier is plenty for personal use
2. Install their CLI, or just use the dashboard's "Create Database" button
3. Name it something like `habit-tracker`
4. From the dashboard, grab two values:
   - **Database URL** (looks like `libsql://habit-tracker-yourname.turso.io`)
   - **Auth Token** (generate one from the database's "Tokens" tab)

## 2. Push this project to GitHub

```bash
cd thread-habit-tracker
git init
git add .
git commit -m "Habit tracker"
```
Create a new repo on GitHub, then push it there.

## 3. Import into Vercel

1. Go to **vercel.com** → **Add New → Project** → import your GitHub repo
2. Vercel will detect `vercel.json` and use the Python runtime automatically
3. Before deploying, add **Environment Variables** (Settings → Environment Variables):
   - `TURSO_DATABASE_URL` = the URL from step 1
   - `TURSO_AUTH_TOKEN` = the token from step 1
4. Click **Deploy**

## 4. First run seeds itself

The very first request to your deployed app creates the tables and seeds
your 12 habits + sample history in Turso automatically — same as it does
locally with SQLite. After that, every checkbox click writes straight to
Turso, so your data persists across deploys, restarts, everything.

## 5. Local development still works unchanged

If you don't set `TURSO_DATABASE_URL` locally, the app just falls back to a
local `habit_tracker.db` file automatically — nothing else to configure.

```bash
pip install -r requirements.txt
python app.py
```

## Notes
- Turso's free tier (500 databases, generous row/storage limits) is more than
  enough for a single-person habit tracker.
- If you ever outgrow Turso or want to self-host the DB too, the `db.py`
  module is the only file that would need to change — everything in `app.py`
  just calls `db.query()` / `db.execute()` regardless of backend.
