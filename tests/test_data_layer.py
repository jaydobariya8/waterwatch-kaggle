"""Tests for the grounded data layer — the safety-critical core."""

from __future__ import annotations

import pytest

from waterwatch import data_layer as dl


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Nitrate (as NO3)", "nitrate"),
        ("Total Hardness (as CaCO3)", "total_hardness"),
        ("Fluoride (as F)", "fluoride"),
        ("E. coli", "e_coli"),
        ("pH value", "ph"),
        ("Residual Free Chlorine", "residual_chlorine"),
        ("TDS", "tds"),
        ("Arsenic", "arsenic"),
    ],
)
def test_normalize_handles_formulae_and_aliases(raw, expected):
    # The '3' in NO3 / CaCO3 and the short 'as' alias must not hijack normalization.
    assert dl.normalize_param(raw) == expected


def test_get_bis_limit_is_cited():
    limit = dl.get_bis_limit("fluoride")
    assert limit["acceptable"] == 1.0
    assert limit["permissible"] == 1.5
    assert limit["citation"]["source"] == "BIS"
    assert "10500" in limit["citation"]["reference"]


def test_get_bis_limit_unknown_raises():
    with pytest.raises(dl.DataLayerError):
        dl.get_bis_limit("unobtanium")


def test_arsenic_is_breach_above_acceptable_even_within_permissible():
    # Arsenic is health-critical: 0.032 is within the BIS permissible (0.05) but must
    # still be flagged a breach because the contaminant has no safe margin.
    results = {r["key"]: r for r in dl.evaluate_sample({"arsenic": 0.032})}
    assert results["arsenic"]["status"] == "breach"
    assert results["arsenic"]["severity"] == "critical"


def test_fluoride_concern_vs_breach():
    concern = {r["key"]: r for r in dl.evaluate_sample({"fluoride": 1.2})}
    breach = {r["key"]: r for r in dl.evaluate_sample({"fluoride": 2.1})}
    assert concern["fluoride"]["status"] == "concern"  # within permissible band
    assert breach["fluoride"]["status"] == "breach"  # above permissible


def test_bacteria_must_be_absent():
    res = {r["key"]: r for r in dl.evaluate_sample({"e_coli": 8})}
    assert res["e_coli"]["status"] == "breach"
    assert res["e_coli"]["severity"] == "critical"


def test_overall_verdict_levels():
    assert dl.overall_verdict(dl.evaluate_sample({"arsenic": 0.032})) == "UNSAFE"
    assert dl.overall_verdict(dl.evaluate_sample({"tds": 600})) == "CAUTION"
    assert dl.overall_verdict(dl.evaluate_sample({"fluoride": 0.5, "ph": 7.2})) == "SAFE"


def test_match_filtration_is_contaminant_specific_and_cited():
    recs = {r["contaminant_key"]: r for r in dl.match_filtration(["arsenic", "e_coli"])}
    assert recs["arsenic"]["recommendation"] == "Activated alumina filter"
    assert "Boiling" in recs["arsenic"]["avoid"]  # boiling does not remove arsenic
    assert recs["e_coli"]["recommendation"].startswith("Boiling")
    assert recs["arsenic"]["citation"]["source"] == "WHO"


def test_health_effect_is_cited():
    effect = dl.health_effect("lead")
    assert effect["severity"] == "critical"
    assert effect["citation"]["reference"]
    assert "no safe" in effect["summary"].lower()


def test_area_readings_degrade_gracefully():
    known = dl.get_area_readings("800001")
    unknown = dl.get_area_readings("999999")
    none = dl.get_area_readings(None)
    assert known["available"] is True and known["readings"]
    assert unknown["available"] is False
    assert none["available"] is False  # never blocks the verdict
