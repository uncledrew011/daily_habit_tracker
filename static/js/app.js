"use strict";

/* ------------------------------------------------------------------
   Thread — habit tracker front end

   Speed design:
   - Taps are OPTIMISTIC: the dot fills instantly, the save happens in the
     background (one at a time, in order), and it only undoes itself if the
     save fails.
   - After you stop tapping, one quiet refresh brings streaks/percentages in
     line with the server. No full reload per tap.
   - The last week you looked at is cached in the browser, so the page paints
     immediately and updates when fresh data arrives.
   ------------------------------------------------------------------ */

const DAY_LETTERS = ["M", "Tu", "W", "Th", "F", "Sa", "Su"];
const CHECK = '<i class="ti ti-check"></i>';
const $ = (id) => document.getElementById(id);

let weekData = null;      // the week currently on screen
let shownStart = null;    // Monday of the week being shown or loading (arrows use this)
let todayIso = null;      // today according to the server (India time)
let chartInstance = null;
let tmpCounter = 0;
let navToken = 0;         // ignores late responses after you changed week
let version = 0;          // bumps on every local change
const weekCache = new Map(); // monday-iso -> week data

/* ---------- date helpers (all UTC math, so no off-by-one in any timezone) ---------- */
function parseIso(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}
function addDays(iso, n) {
  const d = parseIso(iso);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
function mondayOf(iso) {
  return addDays(iso, -((parseIso(iso).getUTCDay() + 6) % 7));
}
function fmt(iso, opts) {
  return parseIso(iso).toLocaleDateString(undefined, { ...opts, timeZone: "UTC" });
}
function localTodayIso() {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}

/* ---------- small helpers ---------- */
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}
const postJson = (path, body, method = "POST") =>
  api(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function store(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* private mode etc. */ }
}
function load(key) {
  try { return JSON.parse(localStorage.getItem(key)); } catch (_) { return null; }
}

let toastTimer = null;
function toast(msg) {
  let el = $("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

/* ---------- save queue: one request at a time, in order ---------- */
let queue = Promise.resolve();
let inFlight = 0;
function enqueue(fn) {
  inFlight++;
  const run = queue.then(fn);
  queue = run.catch(() => {}).finally(() => { inFlight--; });
  return run;
}

/* ---------- header ---------- */
function setHeaderDate(iso) {
  $("weekday").textContent = fmt(iso, { weekday: "long" });
  $("fulldate").textContent = fmt(iso, { month: "long", day: "numeric", year: "numeric" });
}

/* ---------- rendering ---------- */
function streakHtml(n) {
  return n > 0
    ? `<span class="streak-cell"><i class="ti ti-flame"></i>${n}</span>`
    : `<span class="streak-cell zero">–</span>`;
}

function setWeekLabel(startIso) {
  const f = { month: "short", day: "numeric" };
  $("weekLabel").textContent = `${fmt(startIso, f)} – ${fmt(addDays(startIso, 6), f)}`;
}

function renderWeek(data) {
  setWeekLabel(data.start);
  const table = $("sheetTable");
  table.classList.remove("loading");

  let html = `<div class="day-headers"><span></span>
    <div class="dh-days">${DAY_LETTERS.map((l) => `<span>${l}</span>`).join("")}</div>
    <span></span><span></span><span></span></div>`;

  for (const h of data.habits) {
    const dots = h.values
      .map((v, i) => {
        const isToday = data.days[i] === data.today;
        return `<div class="day-dot${v ? " done" : ""}${isToday ? " today" : ""}${h.pending ? " pending" : ""}" data-habit="${h.id}" data-date="${data.days[i]}">${v ? CHECK : ""}</div>`;
      })
      .join("");
    html += `<div class="sheet-row" data-row="${h.id}">
      <div class="habit-name"><span class="habit-emoji">${esc(h.icon)}</span><span>${esc(h.name)}</span></div>
      <div class="thread-row"><div class="thread-line"></div><div class="thread-dots">${dots}</div></div>
      <div class="pct-cell">${h.pct}%</div>
      <div class="streak-cell-wrap" style="display:flex;justify-content:flex-end;">${streakHtml(h.streak)}</div>
      <button class="delete-btn" data-habit="${h.id}" title="Delete habit"${h.pending ? " disabled" : ""}><i class="ti ti-x"></i></button>
    </div>`;
  }
  table.innerHTML = html;
  updateSummary(data.habits);
}

/* Update numbers/dots in place (no flicker) when the habit list is unchanged. */
function patchWeek(data) {
  const same =
    weekData &&
    data.start === weekData.start &&
    data.habits.length === weekData.habits.length &&
    data.habits.every((h, i) => h.id === weekData.habits[i].id);

  weekData = data;
  weekCache.set(data.start, data);
  noteToday(data.today);
  if (data.start === mondayOf(data.today)) store("thread.week", data);

  if (!same) { renderWeek(data); return; }

  const table = $("sheetTable");
  for (const h of data.habits) {
    const row = table.querySelector(`.sheet-row[data-row="${h.id}"]`);
    if (!row) continue;
    row.querySelectorAll(".day-dot").forEach((dot, i) => {
      dot.classList.toggle("done", !!h.values[i]);
      const want = h.values[i] ? CHECK : "";
      if (dot.innerHTML !== want) dot.innerHTML = want;
    });
    row.querySelector(".pct-cell").textContent = h.pct + "%";
    row.querySelector(".streak-cell-wrap").innerHTML = streakHtml(h.streak);
  }
  updateSummary(data.habits);
}

function noteToday(iso) {
  if (iso && iso !== todayIso) { todayIso = iso; setHeaderDate(iso); }
}

function updateSummary(habits) {
  const real = habits.filter((h) => !h.pending);
  if (!real.length) {
    $("topStreak").textContent = "—";
    $("weekAvg").textContent = "—";
    return;
  }
  const top = Math.max(...real.map((h) => h.streak));
  const avg = Math.round(real.reduce((a, h) => a + h.pct, 0) / real.length);
  $("topStreak").textContent = top + (top === 1 ? " day" : " days");
  $("weekAvg").textContent = avg + "%";
}

/* ---------- chart ---------- */
function drawChart(stats) {
  if (typeof Chart === "undefined") return;
  const labels = stats.map((s) => s.label);
  const values = stats.map((s) => s.pct);
  if (chartInstance) {
    chartInstance.data.labels = labels;
    chartInstance.data.datasets[0].data = values;
    chartInstance.update();
    return;
  }
  chartInstance = new Chart($("weeksChart"), {
    type: "line",
    data: {
      labels,
      datasets: [{
        data: values,
        borderColor: "#6fa287",
        backgroundColor: "rgba(111,162,135,0.08)",
        fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2,
      }],
    },
    options: {
      maintainAspectRatio: false,
      animation: { duration: 350 },
      plugins: { legend: { display: false } },
      scales: {
        y: { min: 0, max: 100, ticks: { callback: (v) => v + "%", color: "#635f57", font: { family: "IBM Plex Mono", size: 10 } }, grid: { color: "rgba(255,255,255,0.05)" } },
        x: { ticks: { color: "#635f57", font: { family: "IBM Plex Mono", size: 10 } }, grid: { display: false } },
      },
    },
  });
}

async function refreshChart() {
  try {
    const stats = await api("/api/weekly-stats?weeks=8");
    store("thread.chart", stats);
    drawChart(stats);
  } catch (_) { /* keep the old chart */ }
}

/* ---------- loading weeks ---------- */
async function showWeek(anchorIso) {
  const key = mondayOf(anchorIso);
  const token = ++navToken;
  shownStart = key;
  const cached = weekCache.get(key);

  if (cached) {
    weekData = cached;
    renderWeek(cached);
  } else {
    setWeekLabel(key);
    $("sheetTable").classList.add("loading");
  }

  const startVersion = version;
  try {
    const data = await api(`/api/week?date=${key}`);
    if (token !== navToken) return;                 // you moved on
    if (version !== startVersion || inFlight) {      // you tapped meanwhile: keep your changes
      weekCache.set(key, data);
      if (!cached) { weekData = data; renderWeek(data); }
      scheduleRefresh();
      return;
    }
    patchWeek(data);
  } catch (e) {
    if (token !== navToken) return;
    if (!cached) showLoadError(() => showWeek(anchorIso));
  }
}

function showLoadError(retry) {
  const table = $("sheetTable");
  table.classList.remove("loading");
  table.innerHTML = `<div class="load-error">Couldn't load your habits.
    <button type="button" class="today-btn" id="retryBtn">Try again</button></div>`;
  $("retryBtn").addEventListener("click", () => { table.classList.add("loading"); retry(); });
}

/* One quiet refresh after you stop tapping. */
let refreshTimer = null;
function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(async () => {
    if (inFlight) { scheduleRefresh(); return; }
    if (!weekData || shownStart !== weekData.start) return;
    const startVersion = version;
    const key = weekData.start;
    try {
      const data = await api(`/api/week?date=${key}`);
      if (version !== startVersion || inFlight || !weekData || weekData.start !== key) return; // newer taps will schedule another
      patchWeek(data);
    } catch (_) { /* try again on next change */ }
    refreshChart();
  }, 900);
}

/* ---------- actions ---------- */
function setDot(habit, idx, value) {
  habit.values[idx] = value;
  habit.pct = Math.round((habit.values.reduce((a, b) => a + b, 0) / 7) * 100);
  const dot = document.querySelector(`.day-dot[data-habit="${habit.id}"][data-date="${weekData.days[idx]}"]`);
  if (dot) {
    dot.classList.toggle("done", !!value);
    dot.innerHTML = value ? CHECK : "";
  }
  const row = document.querySelector(`.sheet-row[data-row="${habit.id}"] .pct-cell`);
  if (row) row.textContent = habit.pct + "%";
  updateSummary(weekData.habits);
}

function onDotClick(dot) {
  if (!weekData || dot.classList.contains("pending")) return;
  const habit = weekData.habits.find((h) => String(h.id) === dot.dataset.habit);
  const date = dot.dataset.date;
  const idx = weekData.days.indexOf(date);
  if (!habit || idx < 0) return;

  const next = habit.values[idx] ? 0 : 1;
  version++;
  setDot(habit, idx, next);                          // instant

  const week = weekData;
  enqueue(() => postJson("/api/toggle", { habit_id: habit.id, date, status: next })).catch(() => {
    if (weekData === week) setDot(habit, idx, next ? 0 : 1);   // save failed: undo
    toast("Couldn't save that tap. Check your connection.");
  });
  scheduleRefresh();
}

function onDeleteClick(btn) {
  if (!weekData || btn.disabled) return;
  const id = btn.dataset.habit;
  if (!confirm("Delete this habit? This can't be undone.")) return;
  version++;
  weekData.habits = weekData.habits.filter((h) => String(h.id) !== id);
  const row = document.querySelector(`.sheet-row[data-row="${id}"]`);
  if (row) {
    row.classList.add("removing");
    setTimeout(() => row.remove(), 180);
  }
  updateSummary(weekData.habits);
  enqueue(() => api(`/api/habits/${id}`, { method: "DELETE" })).catch(() => {
    toast("Couldn't delete that habit.");
    weekCache.clear();
    showWeek(weekData.start);
  });
  scheduleRefresh();
}

$("sheetTable").addEventListener("click", (e) => {
  const dot = e.target.closest(".day-dot");
  if (dot) return onDotClick(dot);
  const del = e.target.closest(".delete-btn");
  if (del) onDeleteClick(del);
});

$("prevWeek").addEventListener("click", () => shownStart && showWeek(addDays(shownStart, -7)));
$("nextWeek").addEventListener("click", () => shownStart && showWeek(addDays(shownStart, 7)));
$("todayBtn").addEventListener("click", () => showWeek(todayIso || localTodayIso()));

$("addForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = $("newHabitName");
  const name = input.value.trim();
  if (!name || !weekData) return;
  input.value = "";

  const temp = { id: "tmp" + ++tmpCounter, name, icon: "⭐", category: "general", values: [0, 0, 0, 0, 0, 0, 0], pct: 0, streak: 0, pending: true };
  version++;
  weekData.habits.push(temp);
  renderWeek(weekData);                              // shows the new row instantly

  enqueue(() => postJson("/api/habits", { name, icon: "⭐" }))
    .then(() => scheduleRefresh())
    .catch(() => {
      weekData.habits = weekData.habits.filter((h) => h !== temp);
      renderWeek(weekData);
      input.value = name;
      toast("Couldn't add that habit.");
    });
});

/* ---------- start ---------- */
(function init() {
  // 1. Paint instantly from the last visit, if it is still this week.
  const cached = load("thread.week");
  const localToday = localTodayIso();
  if (cached && cached.habits && cached.start === mondayOf(localToday)) {
    weekData = cached;
    weekCache.set(cached.start, cached);
    noteToday(localToday);
    renderWeek(cached);
  } else {
    setHeaderDate(localToday);
    $("sheetTable").classList.add("loading");
  }
  const cachedChart = load("thread.chart");
  if (cachedChart) drawChart(cachedChart);

  // 2. Fetch fresh data (week and chart in parallel).
  showWeek(localToday);
  refreshChart();
})();
