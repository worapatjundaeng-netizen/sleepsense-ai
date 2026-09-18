const API_BASE = ""; // same origin as the backend that serves this page

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const fileChip = document.getElementById("file-chip");
const fileNameEl = document.getElementById("file-name");
const fileSizeEl = document.getElementById("file-size");
const clearFileBtn = document.getElementById("clear-file");
const analyzeBtn = document.getElementById("analyze-btn");
const loadingEl = document.getElementById("loading");
const errorBox = document.getElementById("error-box");
const resultsEl = document.getElementById("results");
const resetBtn = document.getElementById("reset-btn");

let selectedFile = null;

function formatBytes(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function setFile(file) {
  if (!file) return;
  const ext = file.name.split(".").pop().toLowerCase();
  if (!["wav", "flac"].includes(ext)) {
    showError("รองรับเฉพาะไฟล์ .wav หรือ .flac เท่านั้น");
    return;
  }
  selectedFile = file;
  fileNameEl.textContent = file.name;
  fileSizeEl.textContent = formatBytes(file.size);
  fileChip.classList.add("show");
  analyzeBtn.disabled = false;
  hideError();
}

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) setFile(fileInput.files[0]);
});
clearFileBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  selectedFile = null;
  fileInput.value = "";
  fileChip.classList.remove("show");
  analyzeBtn.disabled = true;
});

function showError(msg) {
  errorBox.textContent = msg;
  errorBox.classList.add("show");
}
function hideError() {
  errorBox.classList.remove("show");
}

analyzeBtn.addEventListener("click", async () => {
  if (!selectedFile) return;
  hideError();
  resultsEl.classList.remove("show");
  loadingEl.classList.add("show");
  analyzeBtn.disabled = true;

  const formData = new FormData();
  formData.append("file", selectedFile);

  try {
    const res = await fetch(`${API_BASE}/analyze`, { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `เกิดข้อผิดพลาด (HTTP ${res.status})`);
    }
    const data = await res.json();
    renderResults(data);
  } catch (err) {
    showError(err.message || "ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์ได้ กรุณาตรวจสอบว่า backend กำลังทำงานอยู่");
  } finally {
    loadingEl.classList.remove("show");
    analyzeBtn.disabled = false;
  }
});

resetBtn.addEventListener("click", () => {
  resultsEl.classList.remove("show");
  clearFileBtn.click();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

function severityFor(eventsPerHour) {
  if (eventsPerHour < 5) return { key: "good", label: "ปกติ", icon: "✓", color: "var(--good)" };
  if (eventsPerHour < 15) return { key: "warning", label: "ระดับเล็กน้อย", icon: "!", color: "var(--warning)" };
  if (eventsPerHour < 30) return { key: "serious", label: "ระดับปานกลาง", icon: "!", color: "var(--serious)" };
  return { key: "critical", label: "ระดับรุนแรง", icon: "‼", color: "var(--critical)" };
}

function formatClock(totalSec) {
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = Math.floor(totalSec % 60);
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}

function renderResults(data) {
  const { summary, events } = data;

  const sev = severityFor(summary.events_per_hour);
  const banner = document.getElementById("severity-banner");
  banner.style.background = `color-mix(in srgb, ${sev.color} 12%, var(--surface))`;
  banner.style.borderColor = `color-mix(in srgb, ${sev.color} 35%, transparent)`;
  document.getElementById("severity-icon").textContent = sev.icon;
  const badge = document.getElementById("severity-badge");
  badge.style.color = sev.color;
  badge.classList.toggle("pulse", sev.key === "critical");
  document.getElementById("severity-label").textContent = sev.label;
  document.getElementById("severity-sub").textContent =
    `พบเหตุการณ์เฉลี่ย ${summary.events_per_hour.toFixed(1)} ครั้ง/ชั่วโมง จากการวิเคราะห์เสียง`;

  document.getElementById("stat-duration").textContent = summary.duration_hms;
  document.getElementById("stat-events").textContent = summary.num_events;
  document.getElementById("stat-rate").textContent = summary.events_per_hour.toFixed(1);
  document.getElementById("stat-ratio").textContent = `${(summary.apnea_time_ratio * 100).toFixed(1)}%`;

  renderTimeline(summary.duration_sec, data.windows);
  renderEventTable(events);

  resultsEl.classList.add("show");
  resultsEl.scrollIntoView({ behavior: "smooth", block: "start" });
}

const CHART_W = 1000;
const CHART_H = 200;
const CHART_TOP_PAD = 10;
const CHART_PLOT_H = CHART_H - CHART_TOP_PAD * 2;
const THRESHOLD = 0.5;

function yFrac(prob) {
  // fraction of chart height from the top, 0..1
  return (CHART_TOP_PAD + (1 - prob) * CHART_PLOT_H) / CHART_H;
}

function svgEl(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}

function renderTimeline(durationSec, windows) {
  const svg = document.getElementById("chart-svg");
  const axis = document.getElementById("timeline-axis");
  const tooltip = document.getElementById("chart-tooltip");
  const wrap = document.getElementById("chart-wrap");
  svg.innerHTML = "";
  axis.innerHTML = "";
  svg.setAttribute("viewBox", `0 0 ${CHART_W} ${CHART_H}`);

  const n = windows.length;
  const points = windows.map((w, i) => ({
    x: n > 1 ? (i / (n - 1)) * CHART_W : CHART_W / 2,
    y: yFrac(w.probability) * CHART_H,
    prob: w.probability,
    start: w.start_sec,
  }));

  // faint area fill under the curve (neutral, just for visual weight)
  if (n > 0) {
    const areaPath = [`M ${points[0].x} ${CHART_H}`, ...points.map((p) => `L ${p.x} ${p.y}`), `L ${points[n - 1].x} ${CHART_H}`, "Z"].join(" ");
    svg.appendChild(svgEl("path", { d: areaPath, fill: "var(--accent)", opacity: "0.08", stroke: "none" }));
  }

  // threshold reference line
  const thresholdY = yFrac(THRESHOLD) * CHART_H;
  svg.appendChild(svgEl("line", {
    x1: 0, x2: CHART_W, y1: thresholdY, y2: thresholdY,
    stroke: "var(--muted)", "stroke-width": 1, "stroke-dasharray": "4 4", "vector-effect": "non-scaling-stroke",
  }));
  const thresholdLabel = svgEl("text", { x: 4, y: thresholdY - 6, fill: "var(--muted)", "font-size": 11 });
  thresholdLabel.textContent = "เกณฑ์ 50%";
  svg.appendChild(thresholdLabel);

  // line, colored per-segment by threshold
  for (let i = 0; i < n - 1; i++) {
    const a = points[i], b = points[i + 1];
    const risky = a.prob >= THRESHOLD || b.prob >= THRESHOLD;
    svg.appendChild(svgEl("line", {
      x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      stroke: risky ? "var(--critical)" : "var(--accent)",
      "stroke-width": 2, "stroke-linecap": "round", "vector-effect": "non-scaling-stroke",
    }));
  }

  // hover crosshair + marker (created once, moved on mousemove)
  const crosshair = svgEl("line", {
    x1: 0, x2: 0, y1: 0, y2: CHART_H, stroke: "var(--ink-2)", "stroke-width": 1,
    "vector-effect": "non-scaling-stroke", opacity: 0,
  });
  const marker = svgEl("circle", { r: 4, fill: "var(--ink)", stroke: "var(--page)", "stroke-width": 2, opacity: 0 });
  svg.appendChild(crosshair);
  svg.appendChild(marker);

  wrap.onmousemove = (e) => {
    if (n === 0) return;
    const rect = wrap.getBoundingClientRect();
    const xFraction = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1);
    const idx = Math.round(xFraction * (n - 1));
    const p = points[idx];

    crosshair.setAttribute("x1", p.x); crosshair.setAttribute("x2", p.x); crosshair.setAttribute("opacity", 1);
    marker.setAttribute("cx", p.x); marker.setAttribute("cy", p.y); marker.setAttribute("opacity", 1);

    tooltip.textContent = `${formatClock(p.start)} · ${(p.prob * 100).toFixed(0)}%`;
    tooltip.style.left = `${(p.x / CHART_W) * 100}%`;
    tooltip.style.top = `${(p.y / CHART_H) * rect.height}px`;
    tooltip.classList.add("show");
  };
  wrap.onmouseleave = () => {
    crosshair.setAttribute("opacity", 0);
    marker.setAttribute("opacity", 0);
    tooltip.classList.remove("show");
  };

  const hours = Math.ceil(durationSec / 3600);
  for (let h = 0; h <= hours; h++) {
    const span = document.createElement("span");
    span.textContent = `${h} ชม.`;
    axis.appendChild(span);
  }
}

function renderEventTable(events) {
  const tbody = document.getElementById("event-tbody");
  const noEvents = document.getElementById("no-events");
  const wrap = document.getElementById("event-table");
  tbody.innerHTML = "";

  if (!events.length) {
    wrap.style.display = "none";
    noEvents.style.display = "block";
    return;
  }
  wrap.style.display = "table";
  noEvents.style.display = "none";

  events.forEach((ev) => {
    const tr = document.createElement("tr");
    const pct = Math.round(ev.avg_probability * 100);
    tr.innerHTML = `
      <td>${formatClock(ev.start_sec)}</td>
      <td>${ev.duration_sec.toFixed(0)} วินาที</td>
      <td>
        <div class="prob-bar-wrap">
          <div class="prob-bar"><div class="prob-bar-fill" style="width:${pct}%"></div></div>
          <span>${pct}%</span>
        </div>
      </td>`;
    tbody.appendChild(tr);
  });
}
