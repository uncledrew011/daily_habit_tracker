let currentAnchor = null;
let chartInstance = null;

const dayLetters = ["M","Tu","W","Th","F","Sa","Su"];

function fmtHeaderDate(iso){
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined,{weekday:"long"});
}

function fmtFullDate(iso){
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined,{month:"long",day:"numeric",year:"numeric"});
}

async function loadToday(){
  const res = await fetch("/api/today");
  const data = await res.json();
  currentAnchor = data.today;
  document.getElementById("weekday").textContent = fmtHeaderDate(data.today);
  document.getElementById("fulldate").textContent = fmtFullDate(data.today);
}

async function loadWeek(anchor){
  const res = await fetch(`/api/week?date=${anchor}`);
  const data = await res.json();
  renderWeek(data);
}

function renderWeek(data){
  const start = new Date(data.start + "T00:00:00");
  const end = new Date(data.end + "T00:00:00");
  document.getElementById("weekLabel").textContent =
    `${start.toLocaleDateString(undefined,{month:"short",day:"numeric"})} – ${end.toLocaleDateString(undefined,{month:"short",day:"numeric"})}`;

  const table = document.getElementById("sheetTable");
  table.innerHTML = "";

  // day header row
  const header = document.createElement("div");
  header.className = "day-headers";
  header.innerHTML = `
    <span></span>
    <div class="dh-days">${dayLetters.map(l=>`<span>${l}</span>`).join("")}</div>
    <span></span><span></span><span></span>`;
  table.appendChild(header);

  data.habits.forEach(h=>{
    const row = document.createElement("div");
    row.className = "sheet-row";

    const dots = h.values.map((v,i)=>{
      const isToday = data.days[i] === data.today;
      return `<div class="day-dot ${v?"done":""} ${isToday?"today":""}" data-habit="${h.id}" data-date="${data.days[i]}">${v?'<i class="ti ti-check"></i>':''}</div>`;
    }).join("");

    const streak = h.streak > 0
      ? `<span class="streak-cell"><i class="ti ti-flame"></i>${h.streak}</span>`
      : `<span class="streak-cell zero">–</span>`;

    row.innerHTML = `
      <div class="habit-name"><span class="habit-emoji">${h.icon}</span><span>${h.name}</span></div>
      <div class="thread-row">
        <div class="thread-line"></div>
        <div class="thread-dots">${dots}</div>
      </div>
      <div class="pct-cell">${h.pct}%</div>
      <div class="streak-cell-wrap" style="display:flex;justify-content:flex-end;">${streak}</div>
      <button class="delete-btn" data-habit="${h.id}" title="Delete habit"><i class="ti ti-x"></i></button>
    `;
    table.appendChild(row);
  });

  table.querySelectorAll(".day-dot").forEach(dot=>{
    dot.addEventListener("click", onToggle);
  });

  table.querySelectorAll(".delete-btn").forEach(btn=>{
    btn.addEventListener("click", onDelete);
  });

  updateSummary(data.habits);
}

async function onToggle(e){
  const el = e.currentTarget;
  const habitId = el.dataset.habit;
  const date = el.dataset.date;
  const res = await fetch("/api/toggle", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({habit_id: habitId, date: date})
  });
  const result = await res.json();
  el.classList.toggle("done", result.status === 1);
  el.innerHTML = result.status === 1 ? '<i class="ti ti-check"></i>' : '';
  loadWeek(currentAnchor);
  loadChart();
}

async function onDelete(e){
  const habitId = e.currentTarget.dataset.habit;
  if(!confirm("Delete this habit? This can't be undone.")) return;
  await fetch(`/api/habits/${habitId}`, { method:"DELETE" });
  loadWeek(currentAnchor);
  loadChart();
}

function updateSummary(habits){
  if(!habits.length){
    document.getElementById("topStreak").textContent = "—";
    document.getElementById("weekAvg").textContent = "—";
    return;
  }
  const topStreak = Math.max(...habits.map(h=>h.streak));
  const avg = Math.round(habits.reduce((a,h)=>a+h.pct,0) / habits.length);
  document.getElementById("topStreak").textContent = topStreak + (topStreak===1?" day":" days");
  document.getElementById("weekAvg").textContent = avg + "%";
}

async function loadChart(){
  const res = await fetch("/api/weekly-stats?weeks=8");
  const stats = await res.json();
  const ctx = document.getElementById("weeksChart");

  if(chartInstance) chartInstance.destroy();
  chartInstance = new Chart(ctx, {
    type:"line",
    data:{
      labels: stats.map(s=>s.label),
      datasets:[{
        data: stats.map(s=>s.pct),
        borderColor:"#6fa287",
        backgroundColor:"rgba(111,162,135,0.08)",
        fill:true,
        tension:0.4,
        pointRadius:0,
        borderWidth:2
      }]
    },
    options:{
      plugins:{legend:{display:false}},
      scales:{
        y:{min:0,max:100,ticks:{callback:v=>v+"%",color:"#635f57",font:{family:"IBM Plex Mono",size:10}},grid:{color:"rgba(255,255,255,0.05)"}},
        x:{ticks:{color:"#635f57",font:{family:"IBM Plex Mono",size:10}},grid:{display:false}}
      }
    }
  });
}

function shiftWeek(days){
  const d = new Date(currentAnchor + "T00:00:00");
  d.setDate(d.getDate() + days);
  currentAnchor = d.toISOString().slice(0,10);
  loadWeek(currentAnchor);
}

document.getElementById("prevWeek").addEventListener("click", ()=>shiftWeek(-7));
document.getElementById("nextWeek").addEventListener("click", ()=>shiftWeek(7));
document.getElementById("todayBtn").addEventListener("click", async ()=>{
  await loadToday();
  loadWeek(currentAnchor);
});

document.getElementById("addForm").addEventListener("submit", async (e)=>{
  e.preventDefault();
  const input = document.getElementById("newHabitName");
  const name = input.value.trim();
  if(!name) return;
  await fetch("/api/habits", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({name, icon:"⭐"})
  });
  input.value = "";
  loadWeek(currentAnchor);
});

(async function init(){
  await loadToday();
  await loadWeek(currentAnchor);
  await loadChart();
})();
