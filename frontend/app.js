/* ============================================================================
   WaterWatch — frontend logic
   Talks to the FastAPI backend, animates the agent pipeline from the live trace,
   and renders the lab-receipt results.
   ========================================================================== */
"use strict";

const API = ""; // same origin
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = {
  activeTab: "sample",
  selectedSample: null,
  file: null,
  lastResult: null,
  filed: null,
};

/* ── icons for the six agents ───────────────────────────────────────────── */
const ICON = {
  parser: '<path d="M7 3h7l4 4v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M13 3v5h5M9 13h6M9 17h6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
  standards: '<path d="M12 3 5 6v6c0 4 3 6.5 7 9 4-2.5 7-5 7-9V6l-7-3Z" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M9 12l2 2 4-4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  health: '<path d="M3 12h4l2 5 4-12 2 7h6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  verifier: '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8.5 12l2.4 2.4 4.6-5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  action: '<path d="M4 12 20 4l-4 16-4-7-8-1Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
  watchdog: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="12" r="2.8" fill="none" stroke="currentColor" stroke-width="1.6"/>',
};
const AGENTS = [
  { key: "parser", name: "Parser" },
  { key: "standards", name: "Standards" },
  { key: "health", name: "Health" },
  { key: "verifier", name: "Verifier" },
  { key: "action", name: "Action" },
  { key: "watchdog", name: "Watchdog" },
];

const DAYS = [
  { n: "Day 1", t: "Agents / ADK", d: "Orchestrator + six-specialist design; Gemini parsing." },
  { n: "Day 2", t: "Tools / MCP", d: "MCP server for BIS limits, area data, treatment KB." },
  { n: "Day 3", t: "Memory", d: "Firestore complaint tracking + pincode aggregation." },
  { n: "Day 4", t: "Agent quality", d: "Verifier loop + eval harness + traces." },
  { n: "Day 5", t: "Production", d: "Cloud Run / Vertex deploy + Scheduler watchdog + A2A." },
];

/* ── fetch helper ───────────────────────────────────────────────────────── */
async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data?.detail?.message || data?.error?.message || `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

/* ── init ───────────────────────────────────────────────────────────────── */
async function init() {
  renderDays();
  wireTabs();
  wireDropzone();
  $("#analyzeBtn").addEventListener("click", runAnalysis);
  try {
    const meta = await api("/api/v1/meta");
    const live = meta.llm_enabled;
    $("#statusDot").className = "dot " + (live ? "live" : "offline");
    $("#statusText").textContent = live ? "Gemini live" : "offline engine";
    if (!live) $("#dzSub").innerHTML = 'Best with <code>GEMINI_API_KEY</code> · paste text or use a sample offline';
  } catch (_) {
    $("#statusText").textContent = "api unreachable";
  }
  loadSamples();
}

function renderDays() {
  $("#daysStrip").innerHTML = DAYS.map(
    (d) => `<div class="day"><div class="day-n">${d.n}</div><div class="day-t">${d.t}</div><div class="day-d">${d.d}</div></div>`
  ).join("");
}

function wireTabs() {
  $$(".tab").forEach((tab) =>
    tab.addEventListener("click", () => {
      $$(".tab").forEach((t) => t.classList.remove("is-active"));
      $$(".tabpane").forEach((p) => p.classList.remove("is-active"));
      tab.classList.add("is-active");
      const name = tab.dataset.tab;
      $(`.tabpane[data-pane="${name}"]`).classList.add("is-active");
      state.activeTab = name;
    })
  );
}

function wireDropzone() {
  const dz = $("#dropzone");
  const input = $("#fileInput");
  input.addEventListener("change", () => setFile(input.files[0]));
  ["dragover", "dragenter"].forEach((e) =>
    dz.addEventListener(e, (ev) => { ev.preventDefault(); dz.classList.add("dragover"); })
  );
  ["dragleave", "drop"].forEach((e) =>
    dz.addEventListener(e, () => dz.classList.remove("dragover"))
  );
  dz.addEventListener("drop", (ev) => {
    ev.preventDefault();
    if (ev.dataTransfer.files[0]) setFile(ev.dataTransfer.files[0]);
  });
}
function setFile(file) {
  if (!file) return;
  state.file = file;
  const sub = $("#dzSub");
  sub.textContent = `${file.name} · ready`;
  sub.classList.add("has-file");
}

async function loadSamples() {
  try {
    const { samples } = await api("/api/v1/samples");
    $("#sampleGrid").innerHTML = samples
      .map(
        (s) => `<button class="sample-chip" data-id="${s.id}">
          <span class="sc-verdict ${s.expected_verdict}">${s.expected_verdict}</span>
          <span class="sc-title">${s.title}</span>
          <span class="sc-sub">${s.subtitle || s.location || ""}</span>
        </button>`
      )
      .join("");
    $$(".sample-chip").forEach((chip) =>
      chip.addEventListener("click", () => {
        $$(".sample-chip").forEach((c) => c.classList.remove("is-selected"));
        chip.classList.add("is-selected");
        state.selectedSample = chip.dataset.id;
      })
    );
  } catch (_) {
    $("#sampleGrid").innerHTML = '<p class="pane-hint">Could not load samples — is the server running?</p>';
  }
}

/* ── run analysis ───────────────────────────────────────────────────────── */
async function runAnalysis() {
  const btn = $("#analyzeBtn");
  const foot = $("#consoleFoot");
  foot.textContent = "";
  const demo = $("#demoToggle").checked;

  let result;
  btn.disabled = true;
  btn.classList.add("loading");
  $(".btn-label", btn).textContent = "Running agents…";

  try {
    if (state.activeTab === "upload" && state.file) {
      const fd = new FormData();
      fd.append("file", state.file);
      const pin = $("#uploadPincode").value.trim();
      if (pin) fd.append("pincode", pin);
      fd.append("demo_inject_uncited", demo ? "true" : "false");
      const res = await fetch(API + "/api/v1/analyze/upload", { method: "POST", body: fd });
      result = await res.json();
      if (!res.ok) throw new Error(result?.detail?.message || "Upload analysis failed");
    } else if (state.activeTab === "paste") {
      const text = $("#reportText").value.trim();
      if (!text) throw new Error("Paste your report parameters first.");
      result = await api("/api/v1/analyze", {
        method: "POST",
        body: JSON.stringify({ text, pincode: $("#pastePincode").value.trim() || null, demo_inject_uncited: demo }),
      });
    } else {
      if (!state.selectedSample) throw new Error("Pick a sample report to analyze.");
      result = await api("/api/v1/analyze", {
        method: "POST",
        body: JSON.stringify({ sample_id: state.selectedSample, demo_inject_uncited: demo }),
      });
    }
  } catch (err) {
    foot.textContent = err.message;
    resetBtn();
    return;
  }

  state.lastResult = result;
  state.filed = null;
  resetBtn();
  await animatePipeline(result.trace);
  renderResults(result);
  $("#results").scrollIntoView({ behavior: "smooth", block: "start" });

  function resetBtn() {
    btn.disabled = false;
    btn.classList.remove("loading");
    $(".btn-label", btn).textContent = "Analyze water";
  }
}

/* ── pipeline animation (the orchestrated moment) ───────────────────────── */
function animatePipeline(trace) {
  const wrap = $("#pipelineWrap");
  const rail = $("#pipeline");
  wrap.hidden = false;

  // Collapse the trace by agent; capture the last detail + loop count + worst status.
  const byAgent = {};
  trace.forEach((step) => {
    const a = (byAgent[step.agent] ||= { detail: "", count: 0, warn: false });
    a.detail = step.detail;
    a.count += 1;
    if (step.status === "warn") a.warn = true;
  });

  rail.innerHTML = AGENTS.map(
    (ag, i) => `
    <li class="node" data-agent="${ag.key}">
      <div class="node-orb">
        <span class="node-num">${i + 1}</span>
        <svg viewBox="0 0 24 24">${ICON[ag.key]}</svg>
        <span class="loop-badge" data-loop="${ag.key}">loop ×<span></span></span>
      </div>
      <div class="node-name">${ag.name}</div>
      <div class="node-detail" data-detail="${ag.key}"></div>
    </li>`
  ).join("");

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const step = reduced ? 0 : 300;

  return new Promise((resolve) => {
    AGENTS.forEach((ag, i) => {
      setTimeout(() => {
        const node = $(`.node[data-agent="${ag.key}"]`, rail);
        const info = byAgent[ag.key];
        node.classList.add("active");
        if (info?.warn) node.classList.add("warn");
        $(`[data-detail="${ag.key}"]`, rail).textContent = info?.detail || "";
        if (ag.key === "verifier" && info && info.count > 1) {
          const badge = $(`[data-loop="${ag.key}"]`, rail);
          $("span", badge).textContent = info.count;
          badge.classList.add("show");
        }
        if (i === AGENTS.length - 1) setTimeout(resolve, reduced ? 0 : 260);
      }, i * step);
    });
  });
}

/* ── render results ─────────────────────────────────────────────────────── */
function renderResults(d) {
  $("#results").hidden = false;
  renderVerdict(d);
  renderReceipt(d);
  renderVerifier(d);
  renderHealth(d);
  renderArea(d);
  renderFiltration(d);
  renderAction(d);
}

function renderVerdict(d) {
  const el = $("#verdict");
  el.className = "verdict " + d.verdict;
  const nBreach = d.breaches.filter((b) => b.status === "breach").length;
  el.innerHTML = `
    <div class="verdict-top">
      <span class="verdict-badge">${d.verdict}</span>
      <span class="verdict-headline">${esc(d.headline)}</span>
    </div>
    <p class="verdict-summary">${esc(d.summary)}</p>
    <div class="verdict-stats">
      <div class="vstat"><b data-count="${nBreach}">0</b><span>parameters breaching</span></div>
      <div class="vstat"><b data-count="${d.citations_count}">0</b><span>citation receipts</span></div>
      <div class="vstat"><b data-count="${d.verifier.loops}">0</b><span>verifier passes</span></div>
      <div class="vstat"><b>${d.parsed.readings.length}</b><span>parameters read</span></div>
    </div>`;
  countUp(el);
}

function renderReceipt(d) {
  const el = $("#receipt");
  const p = d.parsed;
  const rows = d.readings_evaluated
    .map((r) => {
      const limit = limitText(r);
      const cit = r.citation || {};
      return `<div class="r-row" tabindex="0">
        <div class="r-main">
          <span class="r-name">${esc(r.label)}</span>
          <span class="r-val">${fmt(r.value)} ${esc(r.unit)}</span>
          <span class="r-status ${r.status}">${statusLabel(r.status)}</span>
        </div>
        <div class="r-receipt">
          <span class="clip">📎 RECEIPT</span>
          BIS limit: ${limit}. ${esc(r.message)}
          <br/><b>${esc(cit.source || "BIS")}</b> — ${esc(cit.reference || "")}
          ${cit.url ? ` · <a href="${esc(cit.url)}" target="_blank" rel="noopener">source</a>` : ""}
        </div>
      </div>`;
    })
    .join("");
  const cited = d.readings_evaluated.length;
  el.innerHTML = `
    <div class="receipt-head">
      <div class="receipt-title">WATER SAFETY RECEIPT</div>
      <div class="receipt-meta">
        ${p.location ? `<b>${esc(p.location)}</b><br/>` : ""}
        ${p.pincode ? `PIN ${esc(p.pincode)} · ` : ""}${p.sample_id ? `Sample ${esc(p.sample_id)} · ` : ""}${p.collected_on ? esc(p.collected_on) : ""}
        <br/>Standard: IS 10500:2012 · Source: ${esc(p.source)}
      </div>
    </div>
    <div class="receipt-col-head"><span>Parameter</span><span>Result</span><span>Status</span></div>
    ${rows}
    <div class="receipt-foot">${cited} of ${cited} parameters carry a <b>BIS 10500 citation</b> · tap any row for the receipt</div>
    <div class="receipt-perf"></div>`;

  $$(".r-row", el).forEach((row) => {
    const toggle = () => row.classList.toggle("open");
    row.addEventListener("click", toggle);
    row.addEventListener("keydown", (e) => { if (e.key === "Enter") toggle(); });
  });
}

function renderVerifier(d) {
  const v = d.verifier;
  const el = $("#verifierCard");
  el.classList.toggle("clean", v.passed);
  const rejected = v.rejected_claims.length
    ? `<div class="rejected">
         <div class="rejected-head">Blocked ${v.rejected_claims.length} uncited claim${v.rejected_claims.length > 1 ? "s" : ""}</div>
         ${v.rejected_claims.map((rc) => `<div class="rejected-item"><span class="struck">"${esc(rc.text)}"</span><span class="why">↳ ${esc(rc.reason)}</span></div>`).join("")}
       </div>`
    : "";
  el.innerHTML = `
    <div class="vc-head">
      <span class="vc-stamp">${v.passed ? "✓ CLEAN" : "✗ BLOCKED"}</span>
      <span class="vc-title">Verifier self-check</span>
    </div>
    <p class="vc-body">${esc(v.notes)}</p>
    <div class="vc-stats">
      <div class="vc-stat"><b>${v.loops}</b><span>passes</span></div>
      <div class="vc-stat"><b>${v.claims_checked}</b><span>claims checked</span></div>
      <div class="vc-stat"><b>${v.rejected_claims.length}</b><span>rejected</span></div>
    </div>
    ${rejected}`;
}

function renderHealth(d) {
  const el = $("#healthPanel");
  if (!d.health_impacts.length) {
    el.innerHTML = panelHead("health", "Health impact") + '<p class="panel-empty">No health-relevant breaches — nothing to flag.</p>';
    return;
  }
  el.innerHTML =
    panelHead("health", "Health impact") +
    d.health_impacts
      .map(
        (h) => `<div class="health-item">
          <div class="hi-top"><span class="hi-name">${esc(h.label)}</span><span class="sev ${h.severity}">${h.severity}</span></div>
          <p class="hi-summary">${esc(h.summary)}</p>
          <div class="hi-cite">📎 ${esc(h.citation.source)} — ${esc(h.citation.reference)}${h.citation.url ? ` · <a href="${esc(h.citation.url)}" target="_blank" rel="noopener">source</a>` : ""}</div>
        </div>`
      )
      .join("");
}

function renderArea(d) {
  const el = $("#areaPanel");
  const a = d.area_comparison;
  if (!a.available) {
    el.innerHTML = panelHead("watchdog", "Area comparison") + `<p class="panel-empty">${esc(a.note || "No official area readings available.")}</p>`;
    return;
  }
  el.innerHTML =
    panelHead("watchdog", "Area comparison") +
    `<table class="area-table">${a.readings.map((r) => `<tr><td>${esc(r.parameter)}</td><td>${fmt(r.value)} ${esc(r.unit)}</td></tr>`).join("")}</table>
     <p class="area-src">📎 ${esc(a.source)}${a.as_of ? ` · ${esc(a.as_of)}` : ""}</p>`;
}

function renderFiltration(d) {
  const el = $("#filtrationPanel");
  if (!d.filtration.length) {
    el.innerHTML = panelHead("standards", "Filtration match") + '<p class="panel-empty">No treatment needed — water is within limits.</p>';
    return;
  }
  el.innerHTML =
    panelHead("standards", "Cheapest effective filtration") +
    d.filtration
      .map(
        (f) => `<div class="filter-item">
          <div class="fi-top"><span class="fi-cont">${esc(f.contaminant_label)}</span><span class="fi-rec">${esc(f.recommendation)}</span></div>
          <p class="fi-note">${esc(f.note)}</p>
          ${f.avoid.length ? `<p class="fi-avoid">✗ Won't work: ${f.avoid.map(esc).join(", ")}</p>` : ""}
          <div class="fi-cite">📎 ${esc(f.citation.source)} — ${esc(f.citation.reference)}</div>
        </div>`
      )
      .join("");
}

function renderAction(d) {
  const zone = $("#actionZone");
  if (!d.complaint_draft) {
    if (d.verdict === "SAFE") {
      zone.innerHTML = `<div class="action-card"><div class="action-title">No action needed</div>
        <p class="vc-body" style="margin-top:8px">Every parameter is within BIS limits. Keep this receipt for your records and re-test periodically.</p></div>`;
    } else {
      zone.innerHTML = "";
    }
    return;
  }
  const c = d.complaint_draft;
  zone.innerHTML = `
    <div class="action-card">
      <div class="action-head">
        <span class="action-title">Drafted municipal complaint</span>
        <span class="gate-tag">🔒 human approval required before it sends</span>
      </div>
      <pre class="draft">${esc(c.body)}</pre>
      <div class="action-buttons">
        <button class="btn btn-primary" id="fileBtn">Approve &amp; file complaint</button>
        <button class="btn btn-ghost" id="copyBtn">Copy text</button>
      </div>
      <div id="postFile"></div>
    </div>`;
  $("#fileBtn").addEventListener("click", () => fileComplaint(d));
  $("#copyBtn").addEventListener("click", () => {
    navigator.clipboard?.writeText(c.body);
    toast("Complaint text copied", "ok");
  });
}

async function fileComplaint(d) {
  const btn = $("#fileBtn");
  btn.disabled = true;
  btn.textContent = "Filing…";
  const breachKeys = d.breaches.filter((b) => b.status === "breach").map((b) => b.key);
  try {
    const res = await api("/api/v1/complaints", {
      method: "POST",
      body: JSON.stringify({
        request_id: d.request_id,
        pincode: d.parsed.pincode,
        location: d.parsed.location,
        sample_id: d.parsed.sample_id,
        verdict: d.verdict,
        breached_parameters: breachKeys,
        subject: d.complaint_draft.subject,
        body: d.complaint_draft.body,
      }),
    });
    state.filed = res.complaint;
    toast("Complaint filed · " + res.complaint.id, "ok");
    const post = $("#postFile");
    const civic = res.civic;
    post.innerHTML = `
      <div class="filed-banner">✅ Filed as <span class="fid">${res.complaint.id}</span> · status <b>${res.complaint.status}</b> · tracked by the Watchdog agent</div>
      ${civic && civic.cluster_detected
        ? `<div class="civic-note">🏘️ <b>Civic signal:</b> ${civic.count + 1} reports in ${esc(d.parsed.pincode)} share <b>${esc(civic.shared_contaminant_label)}</b> — the Civic Aggregation agent (A2A) can file a <b>collective complaint</b>.</div>`
        : `<div class="civic-note">The Watchdog will follow up. If unresolved past the threshold, it drafts an <b>RTI escalation</b> automatically.</div>`}
      <div class="action-buttons">
        <button class="btn btn-gold" id="escalateBtn">Escalate now → draft RTI</button>
      </div>
      <div id="rtiBox"></div>`;
    $("#escalateBtn").addEventListener("click", () => escalate(res.complaint.id));
  } catch (err) {
    toast(err.message, "err");
    btn.disabled = false;
    btn.textContent = "Approve & file complaint";
  }
}

async function escalate(id) {
  const btn = $("#escalateBtn");
  btn.disabled = true;
  btn.textContent = "Drafting RTI…";
  try {
    const res = await api(`/api/v1/complaints/${id}/escalate`, { method: "POST" });
    toast("RTI application drafted", "ok");
    $("#rtiBox").innerHTML = `
      <div class="filed-banner" style="margin-top:16px">⚖️ Escalated · status <b>${res.complaint.status}</b> — Right to Information application drafted</div>
      <pre class="draft">${esc(res.complaint.rti_draft || "")}</pre>`;
  } catch (err) {
    toast(err.message, "err");
    btn.disabled = false;
    btn.textContent = "Escalate now → draft RTI";
  }
}

/* ── helpers ────────────────────────────────────────────────────────────── */
function panelHead(icon, title) {
  return `<div class="panel-head"><span class="panel-icon"><svg viewBox="0 0 24 24">${ICON[icon]}</svg></span><span class="panel-title">${title}</span></div>`;
}
function limitText(r) {
  if (r.status === "safe" || r.acceptable != null) {
    const acc = r.acceptable != null ? `acceptable ${fmt(r.acceptable)}` : "";
    const perm = r.permissible != null && r.permissible !== r.acceptable ? `, permissible ${fmt(r.permissible)}` : "";
    return `${acc}${perm} ${esc(r.unit)}`.trim();
  }
  return r.limit_used != null ? `${fmt(r.limit_used)} ${esc(r.unit)}` : "—";
}
function statusLabel(s) {
  return s === "breach" ? "BREACH" : s === "concern" ? "ABOVE DESIRABLE" : "WITHIN LIMIT";
}
function fmt(n) {
  if (n == null) return "—";
  return Number.isInteger(n) ? String(n) : String(parseFloat(n.toFixed(4)));
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function countUp(root) {
  $$("[data-count]", root).forEach((el) => {
    const target = parseInt(el.dataset.count, 10) || 0;
    if (target === 0) { el.textContent = "0"; return; }
    const dur = 700;
    const start = performance.now();
    const tick = (t) => {
      const p = Math.min(1, (t - start) / dur);
      el.textContent = Math.round(p * target);
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}
function toast(msg, kind = "ok") {
  const t = document.createElement("div");
  t.className = "toast " + kind;
  t.innerHTML = `<span class="tdot"></span>${esc(msg)}`;
  $("#toastHost").appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; setTimeout(() => t.remove(), 300); }, 3200);
}

init();
