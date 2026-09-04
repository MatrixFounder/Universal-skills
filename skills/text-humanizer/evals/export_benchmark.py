#!/usr/bin/env python3
"""Re-emit a graded campaign in the house benchmark layout. Spends no token.

Why this exists
---------------
`docs/Manuals/skill-evals_guide.md` section 4 defines the shape the shared tools
read, and `skill-creator/scripts/` ships three that read it:
`aggregate_benchmark.py` (mean / stddev / min / max per arm, plus a seeded
bootstrap CI), `verify_pin.py` (re-aggregate and compare against a committed
`benchmark.json`) and `generate_report.py`.

This harness grades a *document* against a key rather than a prompt against a
judge, so it keeps its own `humanizer-evals-report/v1` shape. That was a
deliberate divergence and it had a cost, recorded in README.md: none of those
three tools could read anything here. This script pays the cost off by
translating rather than by rewriting the harness -- the native report stays the
source of truth, and the house layout is a derived view of it.

Layout produced (the "workspace layout" of aggregate_benchmark.py):

    <out>/
      eval-1/
        eval_metadata.json          {"eval_id": "E1", ...}
        with_skill/run-1/grading.json
        without_skill/run-1/grading.json
      eval-2/ ...

`baseline` is renamed to `without_skill` on the way out: aggregate_benchmark.py
recognises both, but only `without_skill` is in its `_BASELINE_CONFIGS`, and the
sign of the reported delta depends on that.

One honest limit, restated in the emitted files: a `pass_rate` here is the
fraction of that run's deterministic checks that passed, not an LLM judge's
verdict. Comparing this number against a judged skill's `pass_rate` compares two
different measurements that share a name.

Usage
    python3 export_benchmark.py                          # the pinned campaign
    python3 export_benchmark.py --report runs/X-report.json --out runs/X-benchmark
    python3 export_benchmark.py --verify                 # export, aggregate, pin

Exit codes
  0  written (and, with --verify, the pin holds)
  1  --verify was asked for and the pin does not hold
  3  the invocation is wrong: a missing report, an unwritable destination
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
HOUSE = os.path.join(REPO, ".claude", "skills", "skill-creator", "scripts")

DEFAULT_REPORT = os.path.join(HERE, "runs", "2026-09-04-full-report.json")
DEFAULT_OUT = os.path.join(HERE, "runs", "2026-09-04-full-benchmark")

# aggregate_benchmark.py's _BASELINE_CONFIGS; `baseline` is not in it.
ARM_NAMES = {"with_skill": "with_skill", "baseline": "without_skill"}


def grading_for(case, run):
    """One run's native grade, restated in the house `grading.json` shape."""
    checks = run.get("checks") or []
    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    return {
        "summary": {
            "pass_rate": round(passed / total, 6) if total else 0.0,
            "passed": passed,
            "failed": total - passed,
            "total": total,
        },
        # `text` and `passed` are what the viewer requires; `evidence` is the
        # grader's own detail string, so a reader can see WHY without opening
        # the corpus. A check that passed vacuously would say so here.
        "expectations": [
            {"text": c["name"], "passed": c["passed"], "evidence": c["detail"]}
            for c in checks
        ],
        "execution_metrics": {
            "output_chars": run.get("chars", 0),
            "total_tool_calls": 0,
            "errors_encountered": 0 if run.get("measured") else 1,
        },
        "notes": {
            "case": case["id"],
            "genre": case["genre"],
            "measured": run.get("measured"),
            "unmeasured_reason": run.get("unmeasured_reason"),
            "markers_before": run.get("markers_before"),
            "markers_after": run.get("markers_after"),
            "facts_kept": run.get("facts_kept"),
            "facts_total": run.get("facts_total"),
            "similarity": run.get("similarity"),
            "growth": run.get("growth"),
        },
        "grader": "text-humanizer/evals/grade_run.py — deterministic, no model judge",
        "pass_rate_means": "fraction of this run's deterministic checks that passed; "
                           "NOT an LLM judge verdict, and not comparable to one",
    }


def export(report_path, out_root, paired_only=False):
    with open(report_path, encoding="utf-8") as fh:
        report = json.load(fh)
    cases = report["cases"]
    if paired_only:
        cases = [c for c in cases if len(c["arms"]) > 1]
    if os.path.isdir(out_root):
        shutil.rmtree(out_root)
    written = 0
    for index, case in enumerate(cases, start=1):
        eval_dir = os.path.join(out_root, f"eval-{index}")
        os.makedirs(eval_dir, exist_ok=True)
        with open(os.path.join(eval_dir, "eval_metadata.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"eval_id": case["id"], "name": case.get("name"),
                       "genre": case.get("genre"),
                       "measures": case.get("measures")}, fh, indent=2)
            fh.write("\n")
        for arm, runs in case["arms"].items():
            config = ARM_NAMES.get(arm, arm)
            for rep, run in enumerate(runs, start=1):
                run_dir = os.path.join(eval_dir, config, f"run-{rep}")
                os.makedirs(run_dir, exist_ok=True)
                with open(os.path.join(run_dir, "grading.json"), "w",
                          encoding="utf-8") as fh:
                    json.dump(grading_for(case, run), fh, indent=2,
                              ensure_ascii=False)
                    fh.write("\n")
                written += 1
    return report, written, cases


def bootstrap_ci(out_root, metric="pass_rate"):
    """The seeded bootstrap interval on the arm delta, from the house function.

    `aggregate_benchmark.py` computes this but does not put it in benchmark.json,
    so it is called directly. It is pure stdlib and seeded, which is what makes
    the interval reproducible rather than a fresh random number each read.
    """
    sys.path.insert(0, HOUSE)
    from aggregate_benchmark import (load_run_results,               # noqa: PLC0415
                                     bootstrap_delta_ci)
    from pathlib import Path                                          # noqa: PLC0415
    results = load_run_results(Path(out_root))
    per_arm = {k: len(v) for k, v in results.items()}
    ci = bootstrap_delta_ci(results, "with_skill", "without_skill",
                            metric=metric, n=5000, seed=0)
    if ci is None:
        return {"error": "one arm has no runs", "runs": per_arm}
    if min(per_arm.values()) < 4:
        ci["caveat"] = (f"only {min(per_arm.values())} runs in the smaller arm; "
                        f"an interval this thin is decoration, not evidence")
    return ci


def house(script, *args):
    return subprocess.run([sys.executable, os.path.join(HOUSE, script), *args],
                          capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--report", default=DEFAULT_REPORT)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--paired-only", action="store_true",
                    help="export only cases carrying BOTH arms, so the delta "
                         "aggregate_benchmark.py prints is arm-vs-arm on one "
                         "population rather than a comparison of two")
    ap.add_argument("--verify", action="store_true",
                    help="also aggregate and check the pin with the house tools")
    ap.add_argument("--ci", action="store_true",
                    help="print the seeded bootstrap CI on the pass_rate delta "
                         "(guide section 7.5). Needs several reps per arm: a "
                         "single draw per arm gives an interval of width zero "
                         "and says nothing")
    args = ap.parse_args()

    if not os.path.isfile(args.report):
        print(f"usage error: no report at {args.report}", file=sys.stderr)
        return 3

    report, written, cases = export(args.report, args.out, args.paired_only)
    print(f"exported {written} runs from {len(cases)} cases -> {args.out}")

    # An unbalanced export makes aggregate_benchmark.py print a delta between
    # two DIFFERENT case sets. In this harness the coverage cases run
    # `with_skill` only, so the default export is 15 treatment cases against 4
    # baseline ones and the delta compares populations, not arms. Say so where
    # the number is printed rather than in a file nobody opens.
    per_arm = {}
    for c in cases:
        for arm, runs in c["arms"].items():
            per_arm.setdefault(arm, set()).add(c["id"])
    if len(per_arm) > 1 and len({frozenset(v) for v in per_arm.values()}) > 1:
        sizes = ", ".join(f"{a}={len(v)}" for a, v in sorted(per_arm.items()))
        print(f"WARNING: the arms cover different case sets ({sizes}). Any delta "
              f"below compares populations, not arms. Re-run with --paired-only "
              f"for a delta between the same cases.", file=sys.stderr)

    if not args.verify:
        return 0

    agg = house("aggregate_benchmark.py", args.out)
    print(agg.stdout.rstrip() or agg.stderr.rstrip())
    if agg.returncode != 0:
        return 1

    benchmark = os.path.join(args.out, "benchmark.json")
    if not os.path.isfile(benchmark):
        print(f"aggregate_benchmark.py wrote no {benchmark}", file=sys.stderr)
        return 1

    pin = house("verify_pin.py", args.out, benchmark)
    print(pin.stdout.rstrip() or pin.stderr.rstrip())
    if pin.returncode != 0:
        return 1

    if args.ci:
        print(json.dumps(bootstrap_ci(args.out), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
