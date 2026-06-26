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
  activeView: "analyzer",
  map: null,
  markers: [],
  complaints: [],
  clusterThreshold: 3,
  parameterLabels: {},
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
  wireViewTabs();
  wireDropzone();
  $("#analyzeBtn").addEventListener("click", runAnalysis);

  // Wire collective petition modal
  $("#closeModalBtn").addEventListener("click", closeCollectiveModal);
  $("#closeModalBtn2").addEventListener("click", closeCollectiveModal);
  $("#copyCollectiveBtn").addEventListener("click", () => {
    if (state.currentModalDraft) {
      navigator.clipboard?.writeText(state.currentModalDraft);
      toast("Collective petition copied", "ok");
    }
  });

  try {
    const meta = await api("/api/v1/meta");
    const live = meta.llm_enabled;
    state.clusterThreshold = meta.cluster_threshold || 3;
    $("#statusDot").className = "dot " + (live ? "live" : "offline");
    $("#statusText").textContent = live ? "Gemini live" : "offline engine";
    if (!live) $("#dzSub").innerHTML = 'Best with <code>GEMINI_API_KEY</code> · paste text or use a sample offline';
  } catch (_) {
    $("#statusText").textContent = "api unreachable";
  }

  // Load parameter labels for map/dashboard summaries
  try {
    const paramsData = await api("/api/v1/parameters");
    state.parameterLabels = {};
    paramsData.parameters.forEach((p) => {
      state.parameterLabels[p.key] = p.label;
    });
  } catch (_) {
    state.parameterLabels = {
      arsenic: "Arsenic",
      fluoride: "Fluoride",
      nitrate: "Nitrate",
      lead: "Lead",
      e_coli: "E. coli",
      total_coliform: "Total Coliform",
      turbidity: "Turbidity"
    };
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
    let title = "";
    let desc = "";
    let btnText = "";
    let subject = "";
    let body = "";

    if (d.verdict === "SAFE") {
      title = "Water is Safe";
      desc = "Every parameter is within BIS limits. Share this result to update your neighborhood's water safety status on the map!";
      btnText = "Share Safe Status on Map";
      subject = "Verified Safe Water Report";
      body = "This is a verified test report showing drinking water meets all Indian Standard IS 10500:2012 specifications. All checked parameters are within safe acceptable ranges.";
    } else if (d.verdict === "CAUTION") {
      title = "Water Needs Caution";
      desc = "Parameters are above desirable limits but within permissible limits. Log this report to the community map to track local water conditions.";
      btnText = "Share Status on Map";
      subject = "Caution: Minor exceedance reported";
      body = "This is a verified test report showing minor parameter warnings under IS 10500:2012. Hardness, TDS or other aesthetic limits are slightly elevated, but no severe health contaminants breached permissible limits.";
    } else {
      zone.innerHTML = "";
      return;
    }

    zone.innerHTML = `
      <div class="action-card">
        <div class="action-head">
          <span class="action-title">${title}</span>
          <span class="gate-tag">🔒 save report to map</span>
        </div>
        <p class="vc-body" style="margin-bottom: 16px;">${desc}</p>
        <div class="action-buttons">
          <button class="btn btn-primary" id="fileBtn">${btnText}</button>
        </div>
        <div id="postFile"></div>
      </div>`;

    $("#fileBtn").addEventListener("click", () => fileSafeOrCautionReport(d, subject, body));
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

async function fileSafeOrCautionReport(d, subject, body) {
  const btn = $("#fileBtn");
  btn.disabled = true;
  btn.textContent = "Saving…";
  try {
    const res = await api("/api/v1/complaints", {
      method: "POST",
      body: JSON.stringify({
        request_id: d.request_id,
        pincode: d.parsed.pincode,
        location: d.parsed.location,
        sample_id: d.parsed.sample_id,
        verdict: d.verdict,
        breached_parameters: d.breaches.map((b) => b.key),
        subject: subject,
        body: body,
      }),
    });
    state.filed = res.complaint;
    toast("Report logged to map · " + res.complaint.id, "ok");
    loadDashboard(); // Refresh map data in background
    const post = $("#postFile");
    post.innerHTML = `
      <div class="filed-banner">✅ Report logged as <span class="fid">${res.complaint.id}</span> · status <b>${res.complaint.status}</b> · mapped on the Community Map</div>
      <div class="action-buttons">
        <a class="btn btn-ghost" id="shareTweetBtn" target="_blank" rel="noopener">🐦 Share on X</a>
        <a class="btn btn-ghost" id="shareWaBtn" target="_blank" rel="noopener">💬 Share on WhatsApp</a>
      </div>
    `;
    const { tweetUrl, whatsappUrl } = generateSocialMessages(d);
    $("#shareTweetBtn").href = tweetUrl;
    $("#shareWaBtn").href = whatsappUrl;
  } catch (err) {
    toast(err.message, "err");
    btn.disabled = false;
    btn.textContent = "Share Status on Map";
  }
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
    loadDashboard(); // Refresh map data in background
    const post = $("#postFile");
    const civic = res.civic;
    post.innerHTML = `
      <div class="filed-banner">✅ Filed as <span class="fid">${res.complaint.id}</span> · status <b>${res.complaint.status}</b> · tracked by the Watchdog agent</div>
      ${civic && civic.cluster_detected
        ? `<div class="civic-note">🏘️ <b>Civic signal:</b> ${civic.count + 1} reports in ${esc(d.parsed.pincode)} share <b>${esc(civic.shared_contaminant_label)}</b> — the Civic Aggregation agent (A2A) can file a <b>collective complaint</b>.</div>`
        : `<div class="civic-note">The Watchdog will follow up. If unresolved past the threshold, it drafts an <b>RTI escalation</b> automatically.</div>`}
      <div class="action-buttons">
        <button class="btn btn-gold" id="escalateBtn">Escalate now → draft RTI</button>
        <a class="btn btn-ghost" id="shareTweetBtn" target="_blank" rel="noopener">🐦 Share on X</a>
        <a class="btn btn-ghost" id="shareWaBtn" target="_blank" rel="noopener">💬 Share on WhatsApp</a>
      </div>
      <div id="rtiBox"></div>`;
    $("#escalateBtn").addEventListener("click", () => escalate(res.complaint.id));
    const { tweetUrl, whatsappUrl } = generateSocialMessages(d);
    $("#shareTweetBtn").href = tweetUrl;
    $("#shareWaBtn").href = whatsappUrl;
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

function generateSocialMessages(d) {
  const pin = d.parsed.pincode || "______";
  const breaches = d.breaches.filter((b) => b.status === "breach");
  const names = breaches.map((b) => b.label).join(" & ");
  const breachDetail = names ? `(${names} exceed permissible limits)` : "due to parameter breaches";
  
  const isDelhi = pin.startsWith("11");
  const boardTag = isDelhi ? " @DelhiJalBoard" : "";
  
  let tweetText = "";
  let whatsappText = "";
  
  if (d.verdict === "SAFE") {
    tweetText = `My drinking water in pincode ${pin} is verified SAFE under BIS 10500 standards. Check your water safety at #WaterWatch!`;
    whatsappText = `💧 Good news! Drinking water at pincode ${pin} has been verified SAFE (all checked parameters are within safe limits under IS 10500). Verify your water test report with citation receipts on WaterWatch.`;
  } else if (d.verdict === "CAUTION") {
    tweetText = `My drinking water in pincode ${pin} is verified under CAUTION (minor aesthetic limits exceeded). Check details at #WaterWatch.`;
    whatsappText = `⚠️ WATER CAUTION: Drinking water at pincode ${pin} is verified under CAUTION (minor desirable limits exceeded, but no acute health hazards found). Review details and filtration advice on WaterWatch.`;
  } else {
    tweetText = `My drinking water in pincode ${pin} is verified UNSAFE ${breachDetail}. Requesting action!${boardTag} @CPCB_OFFICIAL #WaterWatch`;
    whatsappText = `🚨 WATER QUALITY ALERT for pincode ${pin}! A drinking water sample has been verified UNSAFE ${breachDetail}. Residents are advised to check filters and avoid drinking untreated water. Review health limits and treatment receipts on WaterWatch.`;
  }

  return {
    tweetUrl: `https://twitter.com/intent/tweet?text=${encodeURIComponent(tweetText)}`,
    whatsappUrl: `https://api.whatsapp.com/send?text=${encodeURIComponent(whatsappText)}`,
  };
}

/* ── view switching and dashboard mapping ───────────────────────────────── */
const PINCODE_MAP = {
  "110001": [28.6304, 77.2177],
  "110059": [28.6214, 77.0601], // Uttam Nagar, Delhi
  "122001": [28.4595, 77.0266], // Gurugram, Haryana
  "342001": [26.2389, 73.0243], // Jodhpur
  "360001": [22.3039, 70.8022], // Rajkot, Gujarat
  "800001": [25.5941, 85.1376],
  "400001": [18.9220, 72.8347],
  "560001": [12.9716, 77.5946],
  "600001": [13.0827, 80.2707],
  "700001": [22.5726, 88.3639],
};

function getCoordinates(pincode) {
  if (PINCODE_MAP[pincode]) {
    return PINCODE_MAP[pincode];
  }
  const code = parseInt(pincode, 10) || 110001;
  const lat = 16 + ((code % 97) / 97) * 14;
  const lon = 72 + ((code % 89) / 89) * 16;
  return [lat, lon];
}

function getPincodeStatus(pincodeComplaints) {
  const active = pincodeComplaints.filter((c) => c.status !== "resolved");
  if (active.length === 0) return "safe";

  const unsafeCount = active.filter((c) => c.verdict === "UNSAFE").length;
  if (unsafeCount >= state.clusterThreshold) {
    return "cluster";
  }
  if (active.some((c) => c.verdict === "UNSAFE")) {
    return "unsafe";
  }
  if (active.some((c) => c.verdict === "CAUTION")) {
    return "caution";
  }
  return "safe";
}

function wireViewTabs() {
  $$(".nav-tab").forEach((tab) => {
    tab.addEventListener("click", async () => {
      $$(".nav-tab").forEach((t) => t.classList.remove("is-active"));
      tab.classList.add("is-active");
      const viewName = tab.dataset.view;
      state.activeView = viewName;

      if (viewName === "analyzer") {
        $("#analyzerView").classList.add("active");
        $("#dashboardView").style.display = "none";
      } else {
        $("#analyzerView").classList.remove("active");
        $("#dashboardView").style.display = "block";
        await loadDashboard();
      }
    });
  });
}

async function loadDashboard() {
  try {
    const { complaints } = await api("/api/v1/complaints");
    state.complaints = complaints || [];

    const groups = {};
    state.complaints.forEach((c) => {
      if (c.pincode) {
        groups[c.pincode] = groups[c.pincode] || [];
        groups[c.pincode].push(c);
      }
    });

    const activeComplaints = state.complaints.filter((c) => c.status !== "resolved");
    const uniquePincodes = Object.keys(groups);

    let activeClusters = 0;
    for (const pin in groups) {
      const activePinComplaints = groups[pin].filter((c) => c.status !== "resolved");
      if (activePinComplaints.length >= state.clusterThreshold) {
        activeClusters++;
      }
    }

    $("#db-total-complaints").textContent = activeComplaints.length;
    $("#db-total-pincodes").textContent = uniquePincodes.length;
    $("#db-total-clusters").textContent = activeClusters;

    renderDashboardList(groups);

    // Initialize map if not yet done
    if (!state.map) {
      state.map = L.map("map").setView([20.5937, 78.9629], 5);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 18,
      }).addTo(state.map);
    }

    // Force Leaflet map recalculation once displayed
    setTimeout(() => {
      state.map.invalidateSize();
      renderMapMarkers(groups);
    }, 50);

  } catch (err) {
    toast("Failed to load dashboard data: " + err.message, "err");
  }
}

function renderDashboardList(groups) {
  const container = $("#complaintsList");
  if (state.complaints.length === 0) {
    container.innerHTML = '<p class="pane-hint">No active complaints filed yet. File a complaint under the Analyzer tab to populate the dashboard.</p>';
    return;
  }

  let html = "";
  const sortedPincodes = Object.keys(groups).sort((a, b) => {
    const statusA = getPincodeStatus(groups[a]);
    const statusB = getPincodeStatus(groups[b]);
    const rank = { cluster: 4, unsafe: 3, caution: 2, safe: 1 };
    return rank[statusB] - rank[statusA];
  });

  sortedPincodes.forEach((pin) => {
    const list = groups[pin];
    const status = getPincodeStatus(list);

    list.forEach((c) => {
      const isCluster = status === "cluster" && c.status !== "resolved";

      html += `
        <div class="complaint-card">
          <div class="cc-top">
            <span class="cc-id">${esc(c.id)}</span>
            <span class="cc-verdict ${c.verdict}">${esc(c.verdict)}</span>
          </div>
          <div class="cc-loc">${esc(c.location || "Pincode " + pin)}</div>
          <div class="cc-meta">
            <span>Status: <b>${esc(c.status)}</b></span>
            <span>PIN: ${esc(pin)}</span>
          </div>
          ${isCluster ? `<button class="cc-btn" onclick="window.viewCollectivePetition('${pin}')">🏘️ View Collective Petition</button>` : ""}
        </div>
      `;
    });
  });

  container.innerHTML = html;
}

function renderMapMarkers(groups) {
  if (!state.map) return;

  state.markers.forEach((m) => m.remove());
  state.markers = [];

  const colorMap = {
    safe: "#35d39a",
    caution: "#f5b73d",
    unsafe: "#ff5d5d",
    cluster: "#d91e1e",
  };

  for (const pin in groups) {
    const list = groups[pin];
    const status = getPincodeStatus(list);
    const active = list.filter((c) => c.status !== "resolved");
    if (active.length === 0) continue;

    const coords = getCoordinates(pin);
    const radius = status === "cluster" ? 12 : 7;

    const marker = L.circleMarker(coords, {
      radius: radius,
      fillColor: colorMap[status],
      color: status === "cluster" ? "#ffffff" : colorMap[status],
      weight: status === "cluster" ? 2 : 1,
      opacity: 0.9,
      fillOpacity: 0.85,
      className: status === "cluster" ? "pulse-marker" : "",
    }).addTo(state.map);

    const worstVerdictLabel = status.toUpperCase();
    const countText = `${active.length} active case${active.length > 1 ? "s" : ""}`;
    const contaminants = new Set();
    active.forEach((c) => (c.breached_parameters || []).forEach((p) => contaminants.add(p)));
    const contNames = [...contaminants].map((p) => state.parameterLabels?.[p] || p).join(", ");

    let popupHtml = `
      <div class="mp-popup">
        <div class="mp-title">Pincode ${esc(pin)}</div>
        <div class="mp-badge ${status}">${worstVerdictLabel}</div>
        <div class="mp-loc">${countText}</div>
        ${contNames ? `<div class="mp-desc">Contaminants: <b>${esc(contNames)}</b></div>` : ""}
        ${status === "cluster" ? `<button class="mp-btn" onclick="window.viewCollectivePetition('${pin}')">🏘️ Collective Petition</button>` : ""}
      </div>
    `;

    marker.bindPopup(popupHtml);
    state.markers.push(marker);
  }
}

function showCollectiveModal(pincode) {
  const pinComplaints = state.complaints.filter((c) => c.pincode === pincode && c.status !== "resolved");
  const draftText = generateCollectiveDraft(pincode, pinComplaints);
  $("#collectiveDraftText").textContent = draftText;
  $("#collectiveModal").style.display = "flex";
  state.currentModalPincode = pincode;
  state.currentModalDraft = draftText;
}

function closeCollectiveModal() {
  $("#collectiveModal").style.display = "none";
}

function generateCollectiveDraft(pincode, pinComplaints) {
  const counts = {};
  pinComplaints.forEach((c) => {
    (c.breached_parameters || []).forEach((param) => {
      counts[param] = (counts[param] || 0) + 1;
    });
  });
  let sharedContaminant = "contamination";
  let maxCount = 0;
  for (const param in counts) {
    if (counts[param] > maxCount) {
      maxCount = counts[param];
      sharedContaminant = param;
    }
  }
  const label = state.parameterLabels?.[sharedContaminant] || sharedContaminant;

  return `To,
The Municipal Commissioner / District Magistrate,
${pincode}.

Subject: Collective complaint — ${label} contamination affecting multiple households in ${pincode}

Respected Sir/Madam,

${pinComplaints.length} households in pincode ${pincode} have independently reported drinking water exceeding the IS 10500:2012 limit for ${label}. This is no longer an isolated case but a public-health pattern in the area, and warrants municipal-level investigation and remediation.

We jointly request an area-wide water-quality survey and corrective action.

Yours faithfully,
Residents of ${pincode}`;
}

window.viewCollectivePetition = (pincode) => {
  showCollectiveModal(pincode);
};

init();
