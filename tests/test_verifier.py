"""Tests for the Verifier — the citation-receipt guarantee."""

from __future__ import annotations

from waterwatch.schemas import AnalyzeRequest


def test_clean_report_passes_first_try(orchestrator):
    resp = orchestrator.analyze(AnalyzeRequest(sample_id="arsenic_bihar"))
    assert resp.verifier.passed is True
    assert resp.verifier.loops == 1
    assert resp.verifier.rejected_claims == []


def test_uncited_claim_is_caught_and_looped(orchestrator):
    # The demo seam injects one uncited claim; the Verifier must reject it and re-loop.
    resp = orchestrator.analyze(
        AnalyzeRequest(sample_id="arsenic_bihar", demo_inject_uncited=True)
    )
    assert resp.verifier.loops == 2  # corrected, then re-verified clean
    assert resp.verifier.passed is True
    assert len(resp.verifier.rejected_claims) == 1
    rejected = resp.verifier.rejected_claims[0]
    assert "kidney stones" in rejected.text
    assert "citation" in rejected.reason.lower()


def test_every_health_impact_is_cited(orchestrator):
    resp = orchestrator.analyze(AnalyzeRequest(sample_id="fluoride_rajasthan"))
    assert resp.health_impacts
    for impact in resp.health_impacts:
        assert impact.citation.source
        assert impact.citation.reference
