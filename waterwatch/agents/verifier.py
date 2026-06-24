"""Agent 4 — Verifier (the differentiator).

Re-reads the assembled report and rejects any claim that asserts a number or a health
effect without a citation receipt, removing it and looping until the output is clean. This
is the AgentOps / self-evaluation discipline embedded into runtime. Runs as the body of a
``LoopAgent``: each pass corrects the report, then re-checks.
"""

from __future__ import annotations

from ..schemas import RejectedClaim, VerifierAudit
from .base import Agent, AgentContext


def _is_cited(claim: dict) -> bool:
    citation = claim.get("citation")
    if not citation:
        return False
    # A valid receipt must name a source and a reference.
    return bool(citation.get("source")) and bool(citation.get("reference"))


class VerifierAgent(Agent):
    name = "verifier"
    title = "Verifying every claim is cited"

    def run(self, ctx: AgentContext) -> None:
        def _do() -> str:
            claims = ctx.state.setdefault("claims", [])
            audit = ctx.state.get("verifier_audit")
            if audit is None:
                audit = {
                    "passed": False,
                    "loops": 0,
                    "claims_checked": 0,
                    "rejected_claims": [],
                    "notes": "",
                }
                ctx.state["verifier_audit"] = audit

            audit["loops"] += 1

            kept: list[dict] = []
            rejected_this_pass = 0
            for claim in claims:
                audit["claims_checked"] += 1
                if _is_cited(claim):
                    kept.append(claim)
                else:
                    rejected_this_pass += 1
                    audit["rejected_claims"].append(
                        RejectedClaim(
                            text=claim.get("text", ""),
                            reason="No citation receipt — claim asserts a fact without a source.",
                            stage=claim.get("stage", "unknown"),
                        ).model_dump()
                    )

            ctx.state["claims"] = kept
            passed = rejected_this_pass == 0
            ctx.state["verifier_passed"] = passed
            audit["passed"] = passed

            if rejected_this_pass:
                status = "warn"
                detail = (
                    f"Pass {audit['loops']}: rejected {rejected_this_pass} uncited claim(s), "
                    f"sent back for correction."
                )
            else:
                status = "ok"
                detail = (
                    f"Pass {audit['loops']}: all {len(kept)} claims carry a citation receipt — report is clean."
                )
            audit["notes"] = detail
            return detail

        # Status reflects whether this pass found problems.
        self._timed(ctx, _do, status="ok")

    @staticmethod
    def is_done(ctx: AgentContext) -> bool:
        return bool(ctx.state.get("verifier_passed", False))

    @staticmethod
    def build_audit(ctx: AgentContext) -> VerifierAudit:
        audit = ctx.state.get(
            "verifier_audit",
            {"passed": True, "loops": 0, "claims_checked": 0, "rejected_claims": [], "notes": ""},
        )
        return VerifierAudit(
            passed=audit["passed"],
            loops=audit["loops"],
            claims_checked=audit["claims_checked"],
            rejected_claims=[RejectedClaim(**rc) for rc in audit["rejected_claims"]],
            notes=audit["notes"],
        )
