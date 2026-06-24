"""WaterWatch evaluation harness (Day 4 — Agent Quality).

Runs the full agent pipeline over a labelled set of reports with known-correct verdicts and
scores pass/fail per case. This is the AgentOps discipline most capstones skip: a repeatable,
asserting check that the safety verdict and the citation guarantee hold.

Usage:
    python -m eval.run_eval            # human-readable table
    python -m eval.run_eval --json     # machine-readable JSON
Exit code is non-zero if any case fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from waterwatch.agents import get_orchestrator  # noqa: E402
from waterwatch.config import DATA_DIR  # noqa: E402
from waterwatch.schemas import AnalyzeRequest, Status  # noqa: E402

DATASET_DIR = Path(__file__).resolve().parent / "dataset"


def _load_cases() -> list[dict]:
    cases: list[dict] = []
    with (DATA_DIR / "sample_reports.json").open(encoding="utf-8") as fh:
        for s in json.load(fh)["samples"]:
            cases.append(
                {"id": s["id"], "kind": "sample", "title": s["title"], "expected": s["expected"]}
            )
    extra = DATASET_DIR / "extra_cases.json"
    if extra.exists():
        with extra.open(encoding="utf-8") as fh:
            for c in json.load(fh)["cases"]:
                cases.append(
                    {
                        "id": c["id"],
                        "kind": "text",
                        "title": c["title"],
                        "text": c["text"],
                        "pincode": c.get("pincode"),
                        "expected": c["expected"],
                    }
                )
    return cases


def _run_case(orchestrator, case: dict) -> dict:
    if case["kind"] == "sample":
        request = AnalyzeRequest(sample_id=case["id"])
    else:
        request = AnalyzeRequest(text=case["text"], pincode=case.get("pincode"))
    response = orchestrator.analyze(request)

    breach_keys = {b.key for b in response.breaches if b.status == Status.BREACH}
    expected = case["expected"]
    checks: list[tuple[str, bool]] = []

    checks.append((f"verdict == {expected['verdict']}", response.verdict.value == expected["verdict"]))
    for key in expected.get("must_breach", []):
        checks.append((f"breaches {key}", key in breach_keys))
    for key in expected.get("must_not_breach", []):
        checks.append((f"does NOT breach {key}", key not in breach_keys))
    # The citation guarantee must always hold.
    checks.append(("verifier passed", response.verifier.passed))
    checks.append(("has citations", response.citations_count > 0))

    passed = all(ok for _, ok in checks)
    return {
        "id": case["id"],
        "title": case["title"],
        "verdict": response.verdict.value,
        "expected": expected["verdict"],
        "citations": response.citations_count,
        "verifier_loops": response.verifier.loops,
        "passed": passed,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="WaterWatch eval harness")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args()

    orchestrator = get_orchestrator()
    cases = _load_cases()
    results = [_run_case(orchestrator, c) for c in cases]
    n_pass = sum(1 for r in results if r["passed"])

    if args.json:
        print(json.dumps({"total": len(results), "passed": n_pass, "results": results}, indent=2))
    else:
        print("\n  WaterWatch — Evaluation Harness")
        print("  " + "=" * 64)
        for r in results:
            mark = "PASS" if r["passed"] else "FAIL"
            print(
                f"  [{mark}] {r['id']:<26} verdict={r['verdict']:<8} "
                f"(exp {r['expected']:<8}) cites={r['citations']:<2} loops={r['verifier_loops']}"
            )
            if not r["passed"]:
                for label, ok in r["checks"]:
                    if not ok:
                        print(f"         ✗ {label}")
        print("  " + "-" * 64)
        print(f"  {n_pass}/{len(results)} cases passed.\n")

    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
