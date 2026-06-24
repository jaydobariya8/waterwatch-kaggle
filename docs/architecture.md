# WaterWatch — Architecture

WaterWatch is a multi-agent system built around one non-negotiable principle:
**the agent may never assert a number or a health claim it cannot cite.** Everything below
serves that principle.

![Agent pipeline](agent-pipeline.svg)

## The six specialists

The root **Orchestrator** (`waterwatch/agents/orchestrator.py`) wires the specialists into a
`SequentialAgent` spine with the Verifier embedded as a `LoopAgent`:

```
Parser → Standards → Health → [Verifier loop] → Action → Watchdog
```

| # | Agent | File | Input → Output | Grounding |
|---|-------|------|----------------|-----------|
| 1 | **Parser** | `agents/parser.py` | report (PDF/photo/text) → typed params + per-field confidence | Gemini vision, else deterministic text/PDF parser |
| 2 | **Standards** | `agents/standards.py` | params → breach list w/ magnitude & severity | `evaluate_sample`, `get_area_readings` (MCP) |
| 3 | **Health** | `agents/health.py` | breaches → cited health impact each | `health_effect` (MCP) |
| 4 | **Verifier** | `agents/verifier.py` | assembled claims → verified report or re-loop | rejects any claim with no citation receipt |
| 5 | **Action** | `agents/action.py` | breaches → complaint draft + filter match | `match_filtration` (MCP); human-gated |
| 6 | **Watchdog** | `agents/watchdog.py` + `services.py` | complaint → tracked / escalated / RTI / collective | Firestore memory; A2A to Civic Aggregation |

## The grounded data layer (the heart)

`waterwatch/data_layer.py` is the single source of truth. It implements the five tools and
the verdict logic over three bundled JSON files in `waterwatch/data/`:

- **`bis_10500.json`** — the IS 10500:2012 acceptable/permissible limits, with a citation on
  every parameter and a `no_relaxation` / `health_critical` flag.
- **`treatment_kb.json`** — contaminant → cheapest *effective* treatment, with what *won't*
  work (boiling doesn't remove arsenic; it concentrates it).
- **`health_kb.json`** — contaminant → cited, plain-language health effect.

### Verdict logic
For each parameter:
- `value ≤ acceptable` → **safe**
- `acceptable < value ≤ permissible` → **concern** (above desirable, within permissible)
- `value > permissible`, bacteria present, pH out of range, or a `health_critical` toxic
  (e.g. arsenic) above its acceptable limit → **breach**

The overall verdict reduces these: any breach with **high/critical** severity (or bacteria)
→ **UNSAFE**; any other breach or concern → **CAUTION**; all safe → **SAFE**. Severity is
seeded from the health KB and escalated by breach magnitude.

## The MCP layer

`mcp_server/server.py` exposes the same five `data_layer` functions as a **Model Context
Protocol** server (`FastMCP`). Because the MCP tools and the in-process agents call the
*identical* functions, the grounding surface and the agents can never disagree. Run it
standalone with `python -m mcp_server.server`.

| Tool | Returns | Backed by |
|------|---------|-----------|
| `get_bis_limit(param)` | acceptable + permissible limit | bundled BIS 10500 |
| `evaluate_sample(params)` | breach list w/ magnitude & severity | bundled logic + BIS |
| `get_area_readings(pincode)` | recent official readings | data.gov.in / CPCB snapshot |
| `match_filtration(contaminants)` | cheapest treatment per contaminant | curated treatment KB |
| `health_effect(contaminant)` | cited health summary | WHO/BIS health KB |

## Citation receipts & the Verifier

Each specialist emits **claims** as `{text, citation, stage}`. The Verifier (`LoopAgent`
body) scans every claim; any claim whose citation is missing a `source` or `reference` is
**rejected, removed, and logged**, and the loop runs again until the report is clean. Because
the real data is cited by construction, a normal run passes in one pass — but the
`demo_inject_uncited` flag plants one fabricated, uncited claim so you can watch the Verifier
catch and strip it (loops = 2, rejected = 1). This is the AgentOps self-evaluation discipline
embedded into runtime.

## Memory, actuation & A2A

`services.py` owns the complaint lifecycle (`store.py` backs it with local JSON or Firestore):

- **File** — the human-gated step; the agent only ever drafts.
- **Track** — each complaint persists with events and status.
- **Escalate** — `check_escalations()` (the Cloud Scheduler target) drafts an **RTI** for any
  complaint unresolved past `ESCALATION_DAYS`.
- **Aggregate (A2A)** — `detect_cluster()` finds pincode-level contaminant clusters; when the
  threshold is met, the **Civic Aggregation** agent drafts a collective complaint.

## Resilience

The BIS limits and a last-known area snapshot ship **bundled**. A failed external fetch
degrades to "area comparison unavailable" — it never blocks the safety verdict. The LLM is
**optional**: with no `GEMINI_API_KEY`, deterministic engines run and the full pipeline still
works end-to-end.

![GCP topology](gcp-topology.svg)
