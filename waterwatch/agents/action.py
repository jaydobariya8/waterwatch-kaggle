"""Agent 5 — Action.

Drafts a complete, correctly-addressed municipal complaint citing the breached parameters
and their BIS references, and matches the cheapest effective filtration to the SPECIFIC
contaminants found. Nothing is dispatched here — the draft is returned behind an explicit
human-approval gate (the API only files it on a separate, confirmed request).
"""

from __future__ import annotations

from ..data_layer import match_filtration
from ..schemas import ComplaintDraft, FiltrationRec
from .base import Agent, AgentContext, AgentTool

# Contaminants that justify a complaint to the water authority (health-relevant breaches).
_COMPLAINT_WORTHY = {"arsenic", "lead", "fluoride", "nitrate", "e_coli", "total_coliform", "turbidity"}


class ActionAgent(Agent):
    name = "action"
    title = "Drafting action (complaint + filter)"

    def __init__(self) -> None:
        self._filtration = AgentTool("match_filtration", match_filtration)

    def run(self, ctx: AgentContext) -> None:
        def _do() -> str:
            breaches = ctx.state.get("breaches", [])
            parsed = ctx.state["parsed"]
            verdict = ctx.state.get("verdict", "SAFE")

            # Filtration matched to the actual contaminants found.
            contaminant_keys = [b["key"] for b in breaches]
            recs = self._filtration(ctx, contaminants=contaminant_keys) if contaminant_keys else []
            ctx.state["filtration"] = [
                FiltrationRec(
                    contaminant_key=r["contaminant_key"],
                    contaminant_label=r["contaminant_label"],
                    recommendation=r["recommendation"],
                    options=r["options"],
                    avoid=r["avoid"],
                    note=r["note"],
                    citation=r["citation"],
                )
                for r in recs
            ]

            # Complaint draft — only when there is a health-relevant breach.
            complaint_keys = [b for b in breaches if b["key"] in _COMPLAINT_WORTHY]
            if complaint_keys and verdict != "SAFE":
                ctx.state["complaint_draft"] = _build_complaint(parsed, complaint_keys)
                drafted = True
            else:
                ctx.state["complaint_draft"] = None
                drafted = False

            return (
                f"Matched {len(recs)} filtration recommendation(s); "
                f"complaint draft {'prepared (awaiting human approval)' if drafted else 'not required'}."
            )

        self._timed(ctx, _do)


def _build_complaint(parsed, breaches: list[dict]) -> ComplaintDraft:
    location = parsed.location or "the sampled location"
    pincode = parsed.pincode or "______"
    sample_id = parsed.sample_id or "______"
    collected = parsed.collected_on or "______"

    lines = []
    for b in breaches:
        cit = b["citation"]
        lines.append(
            f"  • {b['label']}: measured {b['value']:g} {b['unit']} "
            f"(BIS limit {b.get('limit_used')} {b['unit']}; {cit['reference']})."
        )
    breach_block = "\n".join(lines)
    breached_names = [b["label"] for b in breaches]

    body = (
        f"To,\n"
        f"The Engineer-in-charge / Officer (Water Quality),\n"
        f"Municipal Water Authority / Jal Board,\n"
        f"{location} ({pincode}).\n\n"
        f"Subject: Drinking-water quality failure at {location} — request for testing and corrective action\n\n"
        f"Respected Sir/Madam,\n\n"
        f"A laboratory analysis of drinking water at {location} (Sample ID: {sample_id}, "
        f"collected on {collected}) shows the following parameters exceeding the limits of the "
        f"Indian Standard IS 10500:2012 for drinking water:\n\n"
        f"{breach_block}\n\n"
        f"These exceedances pose a health risk to residents. I request the authority to:\n"
        f"  1. Re-test the supply at this location at the earliest;\n"
        f"  2. Identify and rectify the source of contamination;\n"
        f"  3. Communicate the corrective action taken and the date of resolution.\n\n"
        f"If no response is received within a reasonable period, this matter will be pursued "
        f"through a formal application under the Right to Information Act, 2005.\n\n"
        f"Yours faithfully,\n"
        f"A concerned resident\n"
    )
    subject = f"Drinking-water quality failure at {location} ({pincode}) — corrective action requested"
    return ComplaintDraft(
        to="Municipal Water Authority / Jal Board",
        subject=subject,
        body=body,
        pincode=parsed.pincode,
        sample_id=parsed.sample_id,
        breached_parameters=breached_names,
    )
