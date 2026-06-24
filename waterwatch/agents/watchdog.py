"""Agent 6 — Watchdog (+ Civic Aggregation via A2A).

In the analysis pipeline the Watchdog surfaces the civic signal: it checks memory for other
reports in the same pincode that share a contaminant, talking to the Civic Aggregation
agent over an A2A-style call. The complaint lifecycle itself (filing, follow-up, RTI
escalation) lives in :mod:`waterwatch.services` and is driven by the API + Cloud Scheduler.
"""

from __future__ import annotations

from .. import services
from .base import Agent, AgentContext


class WatchdogAgent(Agent):
    name = "watchdog"
    title = "Checking the civic signal"

    def run(self, ctx: AgentContext) -> None:
        def _do() -> str:
            parsed = ctx.state["parsed"]
            breaches = ctx.state.get("breaches", [])
            contaminant_keys = [b["key"] for b in breaches]

            cluster = services.detect_cluster(parsed.pincode, contaminant_keys)
            ctx.state["civic"] = cluster

            if not parsed.pincode:
                return "No pincode — civic clustering skipped."
            if cluster["cluster_detected"]:
                return (
                    f"Civic Aggregation (A2A): {cluster['count']} report(s) in {parsed.pincode} share "
                    f"'{cluster['shared_contaminant_label']}' — a collective complaint is warranted."
                )
            return (
                f"Logged the civic signal for {parsed.pincode}; "
                f"{cluster['count']} prior matching report(s) on record."
            )

        self._timed(ctx, _do)
