// ============================================================
// EMAILJS SETUP — complete these steps after deployment:
//   1. Go to https://dashboard.emailjs.com/admin/templates
//   2. Create a template with these variables in the body:
//        Guest: {{guest_name}}
//        Date:  {{dinner_date}}
//        Time:  {{dinner_time}}
//        Menu:  {{food_choices}}
//        Link:  {{calendar_link}}
//   3. Copy the Template ID and replace YOUR_TEMPLATE_ID below
//   4. Commit & push — notifications will work immediately
//
// NOTE: Only the public key goes here. NEVER put the private key
//       in client-side JavaScript.
// ============================================================
const EMAILJS_PUBLIC_KEY  = "fDaCZxeZnJVonXtOM";
const EMAILJS_SERVICE_ID  = "service_o27ixzb";
const EMAILJS_TEMPLATE_ID = "YOUR_TEMPLATE_ID";

const HOST_EMAIL = "dara.1440p@gmail.com";

// ============================================================
// FOODS
// ============================================================
const FOODS = [
  { name: "Steak",     emoji: "🥩" },
  { name: "Pasta",     emoji: "🍝" },
  { name: "Gizzdodo",  emoji: "🍗" },
  { name: "Spaghetti", emoji: "🍜" },
  { name: "Ice Cream", emoji: "🍦" },
  { name: "Plantains", emoji: "🌿" },
];

// ============================================================
// APP STATE
// ============================================================
const state = {
  selectedDate:   null,
  selectedHour:   "7",
  selectedMinute: "00",
  selectedAmPm:   "PM",
  selectedFoods:  [],
  guestName:      "Chinelo",
  guestEmail:     "",
  calendarURL:    "",
};

const calView = {
  year:  new Date().getFullYear(),
  month: new Date().getMonth(),
};

// ============================================================
// INIT
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
  emailjs.init({ publicKey: EMAILJS_PUBLIC_KEY });
  spawnEmojis();
  initScreen1();
  initScreen2();
  initScreen3();
  initScreen4();
});

// ============================================================
// FLOATING EMOJIS
// ============================================================
function spawnEmojis() {
  const pool  = ["❤️","🌹","💕","💗","💖","✨","🌸","💌","🥀","💝","🌺","💐","🫶","💋","🍓"];
  const layer = document.getElementById("emoji-layer");
  for (let i = 0; i < 24; i++) {
    const s = document.createElement("span");
    s.textContent = pool[i % pool.length];
    s.style.setProperty("--x",     (Math.random() * 96)        + "vw");
    s.style.setProperty("--delay", (Math.random() * 12)        + "s");
    s.style.setProperty("--dur",   (7 + Math.random() * 10)    + "s");
    s.style.setProperty("--size",  (1.1 + Math.random() * 1.4) + "rem");
    layer.appendChild(s);
  }
}

// ============================================================
// SCREEN TRANSITIONS
// ============================================================
function goToScreen(toId) {
  const current = document.querySelector(".screen.active");
  const next    = document.getElementById(toId);
  if (!next || next === current) return;

  if (current) {
    current.style.opacity   = "0";
    current.style.transform = "translateY(-28px)";
    setTimeout(() => {
      current.classList.remove("active");
      current.style.opacity   = "";
      current.style.transform = "";
    }, 460);
  }

  setTimeout(() => {
    next.classList.add("active");
    next.scrollTop = 0;
  }, 220);
}

// ============================================================
// SCREEN 1 — INVITATION (NO button flees)
// ============================================================
function initScreen1() {
  document.getElementById("btn-yes").addEventListener("click", () => goToScreen("screen-datetime"));
  initNoButton();
}

function initNoButton() {
  const btn = document.getElementById("btn-no");
  let misses   = 0;
  let detached = false;

  function flee(e) {
    e.preventDefault();
    e.stopPropagation();
    misses++;

    if (!detached) {
      const r = btn.getBoundingClientRect();
      btn.style.cssText = `
        position: fixed;
        left: ${r.left}px;
        top: ${r.top}px;
        width: ${r.width}px;
        margin: 0;
        z-index: 999;
      `;
      document.body.appendChild(btn);
      detached = true;
    }

    const bw = btn.offsetWidth  || 60;
    const bh = btn.offsetHeight || 36;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    const newX = 12 + Math.random() * Math.max(1, vw - bw - 24);
    const newY = 12 + Math.random() * Math.max(1, vh - bh - 24);

    btn.style.transition = "left 0.2s ease, top 0.2s ease, transform 0.2s ease, opacity 0.4s ease";
    btn.style.left = newX + "px";
    btn.style.top  = newY + "px";

    if (misses >= 5) {
      const scale = Math.max(0.2, 1 - (misses - 5) * 0.13);
      btn.style.transform = `scale(${scale})`;
    }
    if (misses >= 10) {
      btn.style.opacity       = "0";
      btn.style.pointerEvents = "none";
    }
  }

  btn.addEventListener("mouseenter", flee);
  btn.addEventListener("touchstart",  flee, { passive: false });
  btn.addEventListener("click",       flee);
}

// ============================================================
// SCREEN 2 — DATE & TIME
// ============================================================
function initScreen2() {
  const hourSel = document.getElementById("pick-hour");
  for (let h = 1; h <= 12; h++) {
    const o = document.createElement("option");
    o.value = String(h);
    o.textContent = String(h);
    if (h === 7) o.selected = true;
    hourSel.appendChild(o);
  }

  renderCalendar();

  ["pick-hour", "pick-minute", "pick-ampm"].forEach(id => {
    document.getElementById(id).addEventListener("change", syncTime);
  });

  document.getElementById("btn-confirm-date").addEventListener("click", () => {
    syncTime();
    goToScreen("screen-food");
  });
}

function syncTime() {
  state.selectedHour   = document.getElementById("pick-hour").value;
  state.selectedMinute = document.getElementById("pick-minute").value;
  state.selectedAmPm   = document.getElementById("pick-ampm").value;
}

function renderCalendar() {
  const { year, month } = calView;
  const today    = new Date(); today.setHours(0, 0, 0, 0);
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMo = new Date(year, month + 1, 0).getDate();
  const MONTHS   = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
  ];

  const container = document.getElementById("calendar");
  container.innerHTML = `
    <div class="cal-header">
      <button class="cal-nav" id="cal-prev" aria-label="Previous month">&#8249;</button>
      <span class="cal-title">${MONTHS[month]} ${year}</span>
      <button class="cal-nav" id="cal-next" aria-label="Next month">&#8250;</button>
    </div>
    <div class="cal-weekdays">
      ${["Su","Mo","Tu","We","Th","Fr","Sa"].map(d => `<div class="cal-weekday">${d}</div>`).join("")}
    </div>
    <div class="cal-grid" id="cal-grid"></div>
  `;

  document.getElementById("cal-prev").addEventListener("click", () => {
    calView.month--;
    if (calView.month < 0) { calView.month = 11; calView.year--; }
    renderCalendar();
  });
  document.getElementById("cal-next").addEventListener("click", () => {
    calView.month++;
    if (calView.month > 11) { calView.month = 0; calView.year++; }
    renderCalendar();
  });

  const grid = document.getElementById("cal-grid");

  for (let i = 0; i < firstDay; i++) {
    const cell = document.createElement("button");
    cell.className = "cal-day empty";
    cell.disabled  = true;
    grid.appendChild(cell);
  }

  for (let d = 1; d <= daysInMo; d++) {
    const dayDate = new Date(year, month, d);
    const isPast  = dayDate < today;
    const isToday = dayDate.getTime() === today.getTime();
    const isSel   = state.selectedDate &&
      state.selectedDate.getFullYear() === year &&
      state.selectedDate.getMonth()    === month &&
      state.selectedDate.getDate()     === d;

    const btn = document.createElement("button");
    btn.textContent = d;
    btn.className   = "cal-day"
      + (isPast           ? " disabled" : "")
      + (isToday && !isSel ? " today"   : "")
      + (isSel            ? " selected" : "");
    btn.disabled = isPast;

    if (!isPast) {
      btn.addEventListener("click", () => {
        state.selectedDate = new Date(year, month, d);
        renderCalendar();
        document.getElementById("btn-confirm-date").disabled = false;
      });
    }
    grid.appendChild(btn);
  }
}

// ============================================================
// SCREEN 3 — FOOD SELECTION
// ============================================================
function initScreen3() {
  const grid = document.getElementById("food-grid");
  FOODS.forEach(food => {
    const label = document.createElement("label");
    label.className = "food-card";
    label.innerHTML = `
      <input type="checkbox" name="food" value="${food.name}">
      <span class="food-emoji">${food.emoji}</span>
      <span class="food-name">${food.name}</span>
    `;
    label.querySelector("input").addEventListener("change", () => {
      const any = document.querySelector("#food-grid input:checked");
      document.getElementById("btn-confirm-food").disabled = !any;
    });
    grid.appendChild(label);
  });

  document.getElementById("btn-confirm-food").addEventListener("click", () => {
    state.selectedFoods = [...document.querySelectorAll("#food-grid input:checked")].map(cb => cb.value);
    state.guestName     = document.getElementById("guest-name").value.trim() || "Baby";
    state.guestEmail    = document.getElementById("guest-email").value.trim();

    state.calendarURL = buildCalendarURL();
    buildSummary();
    sendNotification();
    goToScreen("screen-confirm");
    setTimeout(triggerConfetti, 350);
  });
}

// ============================================================
// SCREEN 4 — CONFIRMATION
// ============================================================
function initScreen4() {
  document.getElementById("btn-copy").addEventListener("click", copySummary);
}

function buildSummary() {
  const { selectedDate, selectedHour, selectedMinute, selectedAmPm, selectedFoods, guestName, calendarURL } = state;
  const dateStr = selectedDate.toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric"
  });

  document.getElementById("summary-box").innerHTML = `
    <strong>Guest:</strong> ${escHtml(guestName)} 💕<br>
    <strong>Date:</strong> ${dateStr}<br>
    <strong>Time:</strong> ${selectedHour}:${selectedMinute} ${selectedAmPm}<br>
    <strong>Menu:</strong> ${selectedFoods.map(escHtml).join(", ")}
  `;

  document.getElementById("btn-gcal").onclick = () => window.open(calendarURL, "_blank");
  document.getElementById("btn-ics").onclick  = downloadICS;
}

function triggerConfetti() {
  const container = document.getElementById("confetti");
  container.innerHTML = "";
  const pool = ["❤️","🌹","💕","✨","🌸","💖","🎉","🌺","💝","💐"];
  for (let i = 0; i < 22; i++) {
    const s = document.createElement("span");
    s.textContent = pool[i % pool.length];
    s.style.setProperty("--x",     (Math.random() * 90 + 5)    + "%");
    s.style.setProperty("--delay", (Math.random() * 0.7)       + "s");
    s.style.setProperty("--dur",   (1.2 + Math.random() * 1.2) + "s");
    s.style.setProperty("--size",  (1.0 + Math.random() * 1.0) + "rem");
    container.appendChild(s);
  }
}

async function copySummary() {
  const { selectedDate, selectedHour, selectedMinute, selectedAmPm, selectedFoods, guestName } = state;
  const dateStr = selectedDate.toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric"
  });
  const text = `💕 Dinner Date Confirmed! 💕\nGuest: ${guestName}\n📅 ${dateStr}\n⏰ ${selectedHour}:${selectedMinute} ${selectedAmPm}\n🍽️ Menu: ${selectedFoods.join(", ")}\n\nCan't wait! ❤️`;
  const btn  = document.getElementById("btn-copy");

  try {
    await navigator.clipboard.writeText(text);
    btn.textContent = "Copied! ✓";
  } catch {
    prompt("Copy this summary:", text);
  }
  setTimeout(() => { btn.textContent = "Copy Summary 📋"; }, 2500);
}

// ============================================================
// GOOGLE CALENDAR URL
// ============================================================
function buildCalendarURL() {
  const { selectedDate, selectedHour, selectedMinute, selectedAmPm, selectedFoods } = state;
  const [h, m] = resolveHourMin(selectedHour, selectedMinute, selectedAmPm);

  const start = new Date(selectedDate);
  start.setHours(h, m, 0, 0);
  const end = new Date(start.getTime() + 2 * 3600 * 1000);

  return "https://calendar.google.com/calendar/render?" + new URLSearchParams({
    action:   "TEMPLATE",
    text:     "Romantic Home Cooked Dinner ❤️",
    dates:    `${gcalDate(start)}/${gcalDate(end)}`,
    details:  `A special home cooked dinner just for us 💕\n\nMenu: ${selectedFoods.join(", ")}\n\nCan't wait! ❤️`,
    location: "Home Sweet Home 🏠",
  }).toString();
}

function gcalDate(d) {
  return d.getFullYear()
    + String(d.getMonth() + 1).padStart(2, "0")
    + String(d.getDate()).padStart(2, "0")
    + "T"
    + String(d.getHours()).padStart(2, "0")
    + String(d.getMinutes()).padStart(2, "0")
    + "00";
}

// ============================================================
// ICS DOWNLOAD
// ============================================================
function downloadICS() {
  const { selectedDate, selectedHour, selectedMinute, selectedAmPm, selectedFoods } = state;
  const [h, m] = resolveHourMin(selectedHour, selectedMinute, selectedAmPm);

  const start = new Date(selectedDate);
  start.setHours(h, m, 0, 0);
  const end = new Date(start.getTime() + 2 * 3600 * 1000);

  const ics = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Romantic Dinner Invitation//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "BEGIN:VEVENT",
    `DTSTART:${gcalDate(start)}`,
    `DTEND:${gcalDate(end)}`,
    "SUMMARY:Romantic Home Cooked Dinner ❤️",
    `DESCRIPTION:A special home cooked dinner just for us 💕\\nMenu: ${selectedFoods.join(", ")}\\n\\nCan't wait! ❤️`,
    "LOCATION:Home Sweet Home",
    `UID:dinner-${Date.now()}@invitation`,
    "STATUS:CONFIRMED",
    "END:VEVENT",
    "END:VCALENDAR",
  ].join("\r\n");

  const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
  const url  = URL.createObjectURL(blob);
  const a    = Object.assign(document.createElement("a"), { href: url, download: "dinner-date.ics" });
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ============================================================
// EMAILJS NOTIFICATION
// ============================================================
async function sendNotification() {
  if (EMAILJS_TEMPLATE_ID === "YOUR_TEMPLATE_ID") {
    console.warn("EmailJS: add your Template ID to script.js to enable notifications.");
    return;
  }

  const { selectedDate, selectedHour, selectedMinute, selectedAmPm, selectedFoods, guestName, calendarURL } = state;
  const dateStr = selectedDate.toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric"
  });

  try {
    await emailjs.send(EMAILJS_SERVICE_ID, EMAILJS_TEMPLATE_ID, {
      to_email:      HOST_EMAIL,
      guest_name:    guestName,
      dinner_date:   dateStr,
      dinner_time:   `${selectedHour}:${selectedMinute} ${selectedAmPm}`,
      food_choices:  selectedFoods.join(", "),
      calendar_link: calendarURL,
    });
  } catch (err) {
    console.error("EmailJS send failed:", err);
  }
}

// ============================================================
// HELPERS
// ============================================================
function resolveHourMin(hourStr, minStr, ampm) {
  let h = parseInt(hourStr, 10);
  const m = parseInt(minStr, 10);
  if (ampm === "PM" && h !== 12) h += 12;
  if (ampm === "AM" && h === 12) h  = 0;
  return [h, m];
}

function escHtml(str) {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
