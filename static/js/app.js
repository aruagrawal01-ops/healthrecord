// MediRecord front-end behaviour: theme, sidebar, toasts, counters, table tools, slot picker, charts.
(function () {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  // ---------- Theme (persisted per browser) ----------
  const root = document.documentElement;
  const applyTheme = (t) => {
    root.setAttribute("data-bs-theme", t);
    $$("[data-theme-icon]").forEach((i) => (i.className = t === "dark" ? "bi bi-sun" : "bi bi-moon-stars"));
  };
  let saved = null;
  try { saved = localStorage.getItem("mr-theme"); } catch (e) { /* storage blocked */ }
  applyTheme(saved || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  document.addEventListener("click", (e) => {
    if (!e.target.closest("[data-theme-toggle]")) return;
    const next = root.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("mr-theme", next); } catch (err) { /* ignore */ }
    window.dispatchEvent(new Event("themechange"));
  });

  // ---------- Mobile sidebar ----------
  document.addEventListener("click", (e) => {
    const sb = $(".sidebar");
    if (!sb) return;
    if (e.target.closest("[data-sidebar-toggle]")) sb.classList.toggle("open");
    else if (e.target.closest(".sidebar-backdrop")) sb.classList.remove("open");
  });

  // ---------- Toasts (server flashes arrive as .toast-x) ----------
  const dismiss = (t) => { t.classList.add("hide"); setTimeout(() => t.remove(), 300); };
  $$(".toast-x").forEach((t, i) => setTimeout(() => dismiss(t), 4500 + i * 600));
  document.addEventListener("click", (e) => { const t = e.target.closest(".toast-x"); if (t) dismiss(t); });
  window.toast = (msg, kind = "info") => {
    const icons = { success: "check-lg", danger: "x-lg", warning: "exclamation-lg", info: "info-lg" };
    const stack = $(".toast-stack") || document.body.appendChild(Object.assign(document.createElement("div"), { className: "toast-stack" }));
    const t = document.createElement("div");
    t.className = "toast-x " + kind;
    t.innerHTML = `<div class="ti"><i class="bi bi-${icons[kind] || "info-lg"}"></i></div><div class="tm"></div>`;
    t.querySelector(".tm").textContent = msg;
    stack.appendChild(t);
    setTimeout(() => dismiss(t), 4500);
  };

  // ---------- Count-up numbers ----------
  const countUp = (el) => {
    const end = parseFloat(el.dataset.count);
    if (isNaN(end)) return;
    const dec = (el.dataset.count.split(".")[1] || "").length;
    const suffix = el.dataset.suffix || "";
    const start = performance.now(), dur = 900;
    const step = (now) => {
      const p = Math.min(1, (now - start) / dur), v = end * (1 - Math.pow(1 - p, 3));
      el.textContent = v.toLocaleString("en-IN", { minimumFractionDigits: dec, maximumFractionDigits: dec }) + suffix;
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  $$("[data-count]").forEach(countUp);

  // ---------- Table quick-filter and sorting ----------
  $$("[data-table-filter]").forEach((input) => {
    const table = $(input.dataset.tableFilter);
    if (!table) return;
    const counter = input.dataset.counter ? $(input.dataset.counter) : null;
    const run = () => {
      const q = input.value.trim().toLowerCase();
      let shown = 0;
      $$("tbody tr", table).forEach((tr) => {
        if (tr.dataset.empty !== undefined) return;
        const hit = !q || tr.textContent.toLowerCase().includes(q);
        tr.style.display = hit ? "" : "none";
        if (hit) shown++;
      });
      if (counter) counter.textContent = shown;
    };
    input.addEventListener("input", run);
  });
  $$("table th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const table = th.closest("table"), idx = Array.from(th.parentNode.children).indexOf(th);
      const asc = !th.classList.contains("asc");
      $$("th[data-sort]", table).forEach((h) => h.classList.remove("asc", "desc"));
      th.classList.add(asc ? "asc" : "desc");
      const body = table.tBodies[0];
      const rows = $$("tr", body).filter((r) => r.dataset.empty === undefined);
      const key = (r) => { const c = r.children[idx]; const v = (c.dataset.value ?? c.textContent).trim(); const n = parseFloat(v.replace(/,/g, "")); return th.dataset.sort === "num" && !isNaN(n) ? n : v.toLowerCase(); };
      rows.sort((a, b) => { const x = key(a), y = key(b); return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1); });
      rows.forEach((r) => body.appendChild(r));
    });
  });

  // ---------- Confirm before destructive actions ----------
  document.addEventListener("submit", (e) => {
    const msg = e.target.dataset.confirm;
    if (msg && !confirm(msg)) e.preventDefault();
  });

  // ---------- Live slot picker ----------
  // Markup: [data-slot-picker] with data-url, containing select[name=doctor_id] (or input), input[type=date], .slot-grid, input[name=appointment_time]
  $$("[data-slot-picker]").forEach((box) => {
    const doctor = $("[name=doctor_id]", box), date = $("[type=date]", box), grid = $(".slot-grid", box), hidden = $("[name=appointment_time]", box);
    const submit = $("[type=submit]", box), hint = $(".slot-hint", box);
    const today = new Date(); today.setMinutes(today.getMinutes() - today.getTimezoneOffset());
    if (date && !date.min) date.min = today.toISOString().slice(0, 10);
    const setSubmit = () => { if (submit) submit.disabled = !hidden.value; };
    const load = async () => {
      hidden.value = ""; setSubmit();
      if (!doctor.value || !date.value) { grid.innerHTML = ""; if (hint) hint.textContent = "Choose a doctor and a date to see free slots."; return; }
      grid.innerHTML = '<div class="text-muted small">Loading slots...</div>';
      try {
        const res = await fetch(`${box.dataset.url}?doctor_id=${encodeURIComponent(doctor.value)}&date=${encodeURIComponent(date.value)}`);
        const data = await res.json();
        grid.innerHTML = "";
        if (data.closed) { if (hint) hint.textContent = data.closed; return; }
        const free = data.slots.filter((s) => s.free).length;
        if (hint) hint.textContent = free ? `${free} of ${data.slots.length} slots free` : "Fully booked on this day. Try another date.";
        data.slots.forEach((s) => {
          const b = document.createElement("button");
          b.type = "button"; b.className = "slot"; b.textContent = s.time; b.disabled = !s.free;
          b.title = s.free ? "Available" : "Booked or past";
          b.addEventListener("click", () => { $$(".slot", grid).forEach((x) => x.classList.remove("selected")); b.classList.add("selected"); hidden.value = s.time; setSubmit(); });
          grid.appendChild(b);
        });
      } catch (err) { grid.innerHTML = '<div class="text-danger small">Could not load slots.</div>'; }
    };
    doctor.addEventListener("change", load); date.addEventListener("change", load);
    setSubmit();
    if (doctor.value && date.value) load();
  });

  // ---------- Charts (Chart.js) ----------
  // Usage in templates: mrChart("canvasId", { type, data, options })
  const palette = ["#14b8a6", "#6366f1", "#fb7185", "#f59e0b", "#8b5cf6", "#38bdf8", "#22c55e", "#f97316", "#ec4899", "#64748b", "#0ea5e9"];
  window.MR_COLORS = palette;
  const charts = [];
  const themeColors = () => {
    const dark = root.getAttribute("data-bs-theme") === "dark";
    return { text: dark ? "#94a3b8" : "#64748b", grid: dark ? "rgba(148,163,184,.12)" : "rgba(100,116,139,.12)" };
  };
  window.mrChart = (id, cfg) => {
    const el = document.getElementById(id);
    if (!el || !window.Chart) return null;
    const c = themeColors();
    Chart.defaults.font.family = '"Plus Jakarta Sans", system-ui, sans-serif';
    Chart.defaults.color = c.text;
    Chart.defaults.borderColor = c.grid;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxWidth = 8;
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 10;
    Chart.defaults.maintainAspectRatio = false;
    const chart = new Chart(el, cfg);
    charts.push(chart);
    return chart;
  };
  window.addEventListener("themechange", () => {
    const c = themeColors();
    charts.forEach((ch) => {
      Chart.defaults.color = c.text;
      Object.values(ch.options.scales || {}).forEach((s) => { if (s.grid) s.grid.color = c.grid; if (s.ticks) s.ticks.color = c.text; });
      if (ch.options.plugins && ch.options.plugins.legend) ch.options.plugins.legend.labels.color = c.text;
      ch.update();
    });
  });

  // ---------- Bootstrap tooltips ----------
  if (window.bootstrap) $$('[data-bs-toggle="tooltip"]').forEach((el) => new bootstrap.Tooltip(el));
})();
