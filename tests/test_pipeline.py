"""End-to-end agent-pipeline tests over the bundled samples."""

from __future__ import annotations

import pytest

from waterwatch.schemas import AnalyzeRequest, Status


@pytest.mark.parametrize(
    "sample_id,expected",
    [
        ("arsenic_bihar", "UNSAFE"),
        ("fluoride_rajasthan", "UNSAFE"),
        ("bacterial_urban", "UNSAFE"),
        ("safe_supply", "SAFE"),
        ("hard_water_caution", "CAUTION"),
    ],
)
def test_sample_verdicts(orchestrator, sample_id, expected):
    resp = orchestrator.analyze(AnalyzeRequest(sample_id=sample_id))
    assert resp.verdict.value == expected
    assert resp.verifier.passed is True
    assert resp.citations_count > 0
    # Every breach carries a citation receipt.
    for breach in resp.breaches:
        assert breach.citation.source and breach.citation.reference


def test_arsenic_sample_breaches_arsenic_with_treatment(orchestrator):
    resp = orchestrator.analyze(AnalyzeRequest(sample_id="arsenic_bihar"))
    breach_keys = {b.key for b in resp.breaches if b.status == Status.BREACH}
    assert "arsenic" in breach_keys
    treatments = {f.contaminant_key: f.recommendation for f in resp.filtration}
    assert "arsenic" in treatments
    assert "alumina" in treatments["arsenic"].lower()


def test_unsafe_drafts_complaint_safe_does_not(orchestrator):
    unsafe = orchestrator.analyze(AnalyzeRequest(sample_id="fluoride_rajasthan"))
    safe = orchestrator.analyze(AnalyzeRequest(sample_id="safe_supply"))
    assert unsafe.complaint_draft is not None
    assert "IS 10500" in unsafe.complaint_draft.body
    assert safe.complaint_draft is None


def test_pasted_text_parses_formulae(orchestrator):
    text = "pH 7.9\nFluoride (as F) 2.1 mg/L\nNitrate (as NO3) 52 mg/L"
    resp = orchestrator.analyze(AnalyzeRequest(text=text, pincode="342001"))
    keys = {b.key for b in resp.breaches if b.status == Status.BREACH}
    assert {"fluoride", "nitrate"} <= keys  # values read correctly, not the formula digits


def test_trace_contains_all_agents(orchestrator):
    resp = orchestrator.analyze(AnalyzeRequest(sample_id="bacterial_urban"))
    agents = {t.agent for t in resp.trace}
    assert {"parser", "standards", "health", "verifier", "action", "watchdog"} <= agents
