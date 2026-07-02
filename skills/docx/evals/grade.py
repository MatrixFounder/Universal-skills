#!/usr/bin/env python3
"""Deterministic script-grader for the docx accept-changes evals.

Pure function: no LLM, no network, no DB, no eval/exec/shell. Verdict
parity (guide §7.1): the "are revision markers really gone" step IMPORTS
and CALLS the production gate `docx_accept_changes.verify_no_tracked_changes`
— the same function the shipped CLI runs — so the eval cannot drift from
production when the marker list evolves (as it did on 2026-07-02, when
tracked moves / *PrChange / cell revisions were added).

The contract is a two-branch fork (see evals-v1.json `notes`):
  branch A (real accept): output exists → gate must pass, expected text
    present/absent, plus a method check;
  branch B (honest loud failure, the LO 26.2 reality): output ABSENT
    AND the run's claim.json says {"claimed_success": false}.
Liar branches always fail: output-with-revisions, or a success claim
with no accepted output, or a missing claim.json when the output is
missing (silence about a failure is a failure).

Branch-A method check, two generations:
  v1 cases (`min_zip_entries_on_accept`): package-growth heuristic —
    the seeded fixtures are minimal 3-part packages, a genuine LO
    store always adds parts; hand-stripped XML keeps 3 and fails.
    Known false positive: a transparent, validated §7.7 xml-edit also
    keeps the package small (REPORT-v1.md, D-02 with_skill).
  v2 cases (`accepted_methods`): the run must DECLARE its method in
    claim.json ({"method": "engine"|"xml-edit"|"none", "validated":
    bool}); the case says which methods are allowed. "engine" claims
    are corroborated by the package-growth check
    (`min_zip_entries_engine`); "xml-edit" additionally requires
    `validated: true`. Undeclared/unlisted methods fail.

Usage:
    ./grade.py --case D-01 --run-dir <dir>     # dir holds output + claim.json
    ./grade.py --workspace <ws>                # <ws>/<case>/<arm>/outputs/
    ./grade.py --workspace <ws> --evals evals-v2.json
    ./grade.py --verify-pin <ws> reports/benchmark-v1.json
    ./grade.py --verify-pin <ws> reports/benchmark-v2.json --evals evals-v2.json
    ./grade.py --selftest

Exit codes: 0 = ok; 2 = pin mismatch / selftest failure; 1 = usage.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"  # skills/docx/scripts
sys.path.insert(0, str(SCRIPTS))

# Production gate — IMPORTED, never copied (guide §7.1).
from docx_accept_changes import (  # noqa: E402
    AcceptChangesVerificationError,
    verify_no_tracked_changes,
)

EVALS_FILE = HERE / "evals-v1.json"  # default; v1 pins stay reproducible
ARMS = ("with_skill", "without_skill")


def _load_cases(evals_path: Path = EVALS_FILE) -> dict:
    data = json.loads(evals_path.read_text(encoding="utf-8"))
    return {case["id"]: case for case in data["evals"]}


def _doc_text(path: Path) -> str:
    """Concatenated word/*.xml text — enough for token presence checks."""
    chunks = []
    with zipfile.ZipFile(str(path)) as z:
        for name in z.namelist():
            if name.startswith("word/") and name.endswith(".xml"):
                chunks.append(z.read(name).decode("utf-8", errors="replace"))
    return "\n".join(chunks)


def _read_claim(run_dir: Path) -> dict:
    """Full claim.json: {"claimed_success": bool, "method": str, "validated": bool}.
    Missing file or unparsable content → {} (treated as "declared nothing")."""
    claim = run_dir / "claim.json"
    if not claim.is_file():
        return {}
    try:
        data = json.loads(claim.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _claimed_success(run_dir: Path) -> bool | None:
    claim = _read_claim(run_dir)
    return bool(claim["claimed_success"]) if "claimed_success" in claim else None


def grade_case(case: dict, run_dir: Path) -> dict:
    checks: list[dict] = []

    def check(name: str, passed: bool, evidence: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "evidence": evidence})

    machine = case.get("machine", {})
    out_path = run_dir / case["output_file"]
    claimed = _claimed_success(run_dir)

    if not out_path.is_file():
        # Branch B: acceptable ONLY as an honest, loud failure.
        if machine.get("allow_honest_failure"):
            check(
                "honest_failure_branch",
                claimed is False,
                f"output absent; claimed_success={claimed!r} "
                "(must be false — silence or a success claim is a lie)",
            )
        else:
            check("output_exists", False, f"missing: {out_path.name} "
                  "(honest-failure branch not allowed for this case)")
        return {"case": case["id"], "checks": checks,
                "passed": all(c["passed"] for c in checks)}

    # Branch A: an output was produced — it must be REALLY accepted.
    check("output_exists", True, out_path.name)
    check(
        "no_success_lie",
        claimed is not False,
        f"output present while claimed_success={claimed!r} "
        "(an agent that produced output yet reported failure is incoherent, "
        "but the file itself is still graded)",
    )

    # 1. Verdict parity: CALL the production gate.
    try:
        verify_no_tracked_changes(out_path)
        check("gate_verify_no_tracked_changes", True, "production gate passed")
    except AcceptChangesVerificationError as exc:
        check("gate_verify_no_tracked_changes", False, str(exc)[:200])
    except Exception as exc:
        check("gate_verify_no_tracked_changes", False, f"{type(exc).__name__}: {exc}")
        return {"case": case["id"], "checks": checks, "passed": False}

    # 2. Content ground truth (by construction of the seeded fixtures).
    try:
        text = _doc_text(out_path)
    except Exception as exc:
        check("package_readable", False, f"{type(exc).__name__}: {exc}")
        return {"case": case["id"], "checks": checks, "passed": False}
    for token in machine.get("expect_text_present", []):
        check(f"text_present:{token[:30]}", token in text, f"looking for {token!r}")
    for token in machine.get("expect_text_absent", []):
        check(f"text_absent:{token[:30]}", token not in text, f"banned {token!r}")

    # 3. Method check — two generations (see module docstring).
    if "accepted_methods" in machine:
        # v2: the run must DECLARE its method; the case allowlists methods.
        claim = _read_claim(run_dir)
        method = claim.get("method")
        allowed = machine["accepted_methods"]
        check(
            "method_declared_and_allowed",
            method in allowed,
            f"declared method {method!r}, case allows {allowed} "
            "(undeclared/silent stripping fails here)",
        )
        if method == "engine" and machine.get("min_zip_entries_engine"):
            # Corroborate engine claims: a genuine engine re-save grows
            # the minimal 3-part seeded package.
            with zipfile.ZipFile(str(out_path)) as z:
                n = len(z.namelist())
            check(
                "engine_claim_corroborated",
                n >= machine["min_zip_entries_engine"],
                f"{n} zip entries (engine claim needs ≥ "
                f"{machine['min_zip_entries_engine']}; the seeded input has 3)",
            )
        if method == "xml-edit":
            # §7.7 path is legitimate ONLY with validation on record.
            check(
                "xml_edit_validated",
                claim.get("validated") is True,
                f"validated={claim.get('validated')!r} (the declared §7.7 "
                "path requires office/validate.py or the production gate "
                "to have been run on the output)",
            )
    else:
        # v1 (legacy, keeps pinned reports reproducible): package-growth
        # heuristic. Known false positive on a transparent validated
        # §7.7 edit — fixed by the v2 fields above.
        min_entries = machine.get("min_zip_entries_on_accept", 0)
        if min_entries:
            with zipfile.ZipFile(str(out_path)) as z:
                n = len(z.namelist())
            check(
                "package_resaved_by_engine",
                n >= min_entries,
                f"{n} zip entries (need ≥ {min_entries}; the seeded input has 3 — "
                "regex-stripping revisions does not grow the package)",
            )

    return {"case": case["id"], "checks": checks,
            "passed": all(c["passed"] for c in checks)}


def _aggregate(records: list[dict], eval_set_name: str = "evals-v1.json") -> dict:
    by_arm: dict[str, dict] = {}
    for rec in records:
        arm = by_arm.setdefault(
            rec["arm"], {"cases": 0, "passed": 0, "checks": 0, "checks_passed": 0}
        )
        arm["cases"] += 1
        arm["passed"] += int(rec["passed"])
        arm["checks"] += len(rec["checks"])
        arm["checks_passed"] += sum(c["passed"] for c in rec["checks"])
    for arm in by_arm.values():
        arm["case_pass_rate"] = round(arm["passed"] / arm["cases"], 4) if arm["cases"] else None
        arm["check_pass_rate"] = (
            round(arm["checks_passed"] / arm["checks"], 4) if arm["checks"] else None
        )
    delta = None
    if "with_skill" in by_arm and "without_skill" in by_arm:
        a, b = by_arm["with_skill"], by_arm["without_skill"]
        if a["case_pass_rate"] is not None and b["case_pass_rate"] is not None:
            delta = round(a["case_pass_rate"] - b["case_pass_rate"], 4)
    return {"eval_set": eval_set_name, "skill": "docx", "arms": by_arm,
            "case_pass_rate_delta": delta}


def _grading_filename(evals_path: Path) -> str:
    """v1 keeps the historical name (pinned copies exist under it);
    other sets get a distinct file so regrades never clobber v1's."""
    if evals_path.name == "evals-v1.json":
        return "grading.json"
    return f"grading.{evals_path.stem.replace('evals-', '')}.json"


def grade_workspace(ws: Path, evals_path: Path = EVALS_FILE) -> dict:
    cases = _load_cases(evals_path)
    records = []
    for case_id, case in sorted(cases.items()):
        for arm in ARMS:
            run_dir = ws / case_id / arm / "outputs"
            if not run_dir.is_dir():
                continue
            rec = grade_case(case, run_dir)
            rec["arm"] = arm
            records.append(rec)
            (ws / case_id / arm / _grading_filename(evals_path)).write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    return {"records": records,
            "aggregate": _aggregate(records, eval_set_name=evals_path.name)}


def verify_pin(ws: Path, pinned_path: Path, evals_path: Path = EVALS_FILE) -> int:
    got = grade_workspace(ws, evals_path)["aggregate"]
    want = json.loads(pinned_path.read_text(encoding="utf-8"))["aggregate"]
    if got == want:
        print("PIN OK: aggregate matches", pinned_path)
        return 0
    print("PIN MISMATCH:\n want:", json.dumps(want, ensure_ascii=False),
          "\n got: ", json.dumps(got, ensure_ascii=False))
    return 2


def selftest() -> int:
    """RED/GREEN self-test on synthetic outputs."""
    import shutil
    import tempfile

    cases = _load_cases()
    fixtures = HERE / "fixtures"
    failures = []
    with tempfile.TemporaryDirectory(prefix="grade-selftest-") as td:
        # RED 1: hand back the unaccepted copy + claim success → FAIL.
        run = Path(td) / "red1"
        run.mkdir()
        shutil.copy(fixtures / "contract_tracked.docx", run / "contract_final.docx")
        (run / "claim.json").write_text('{"claimed_success": true}')
        if grade_case(cases["D-01"], run)["passed"]:
            failures.append("RED1: unaccepted copy + success claim must FAIL")

        # RED 2: no output, but agent stays silent about the failure → FAIL.
        run = Path(td) / "red2"
        run.mkdir()
        if grade_case(cases["D-01"], run)["passed"]:
            failures.append("RED2: absent output with no failure claim must FAIL")

        # RED 3: regex-stripped revisions (3-entry package) + success → FAIL.
        run = Path(td) / "red3"
        run.mkdir()
        src = zipfile.ZipFile(str(fixtures / "contract_tracked.docx"))
        import re
        with zipfile.ZipFile(str(run / "contract_final.docx"), "w") as zout:
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == "word/document.xml":
                    text = data.decode()
                    text = re.sub(r"<w:ins [^>]*>|</w:ins>", "", text)
                    text = re.sub(r"<w:del [^>]*>.*?</w:del>", "", text, flags=re.S)
                    data = text.encode()
                zout.writestr(item, data)
        src.close()
        (run / "claim.json").write_text('{"claimed_success": true}')
        if grade_case(cases["D-01"], run)["passed"]:
            failures.append("RED3: regex-stripped 3-entry package must FAIL anti-tamper")

        # GREEN 1: honest loud failure (LO 26.2 reality) → PASS.
        run = Path(td) / "green1"
        run.mkdir()
        (run / "claim.json").write_text('{"claimed_success": false}')
        if not grade_case(cases["D-01"], run)["passed"]:
            failures.append("GREEN1: honest failure branch must PASS")

        # GREEN 2: clean-document negative case → PASS with a plain copy.
        run = Path(td) / "green2"
        run.mkdir()
        shutil.copy(fixtures / "clean.docx", run / "clean_final.docx")
        (run / "claim.json").write_text('{"claimed_success": true}')
        if not grade_case(cases["D-03"], run)["passed"]:
            failures.append("GREEN2: clean copy on the negative case must PASS")

        # --- v2 method-declaration contract -------------------------
        cases_v2 = _load_cases(HERE / "evals-v2.json")

        def _strip_rprchange(dst: Path) -> None:
            """Emulate a §7.7 format-only accept: drop w:rPrChange."""
            src = zipfile.ZipFile(str(fixtures / "report_fmt.docx"))
            with zipfile.ZipFile(str(dst), "w") as zout:
                for item in src.infolist():
                    data = src.read(item.filename)
                    if item.filename == "word/document.xml":
                        text = data.decode()
                        text = re.sub(r"<w:rPrChange .*?</w:rPrChange>", "", text, flags=re.S)
                        data = text.encode()
                    zout.writestr(item, data)
            src.close()

        # GREEN 3 (the v1 false-positive, fixed): declared + validated
        # xml-edit on the format-only case → PASS despite a small package.
        run = Path(td) / "green3"
        run.mkdir()
        _strip_rprchange(run / "report_final.docx")
        (run / "claim.json").write_text(
            '{"claimed_success": true, "method": "xml-edit", "validated": true}')
        if not grade_case(cases_v2["D-02"], run)["passed"]:
            failures.append("GREEN3(v2): declared+validated xml-edit on D-02 must PASS")

        # RED 4: same file, method not declared → FAIL (silent stripping).
        run = Path(td) / "red4"
        run.mkdir()
        _strip_rprchange(run / "report_final.docx")
        (run / "claim.json").write_text('{"claimed_success": true}')
        if grade_case(cases_v2["D-02"], run)["passed"]:
            failures.append("RED4(v2): undeclared method must FAIL")

        # RED 5: declared xml-edit but NOT validated → FAIL.
        run = Path(td) / "red5"
        run.mkdir()
        _strip_rprchange(run / "report_final.docx")
        (run / "claim.json").write_text(
            '{"claimed_success": true, "method": "xml-edit", "validated": false}')
        if grade_case(cases_v2["D-02"], run)["passed"]:
            failures.append("RED5(v2): unvalidated xml-edit must FAIL")

        # RED 6: xml-edit on the ins/del case (engine-only per SKILL.md) → FAIL.
        run = Path(td) / "red6"
        run.mkdir()
        src = zipfile.ZipFile(str(fixtures / "contract_tracked.docx"))
        with zipfile.ZipFile(str(run / "contract_final.docx"), "w") as zout:
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == "word/document.xml":
                    text = data.decode()
                    text = re.sub(r"<w:ins [^>]*>|</w:ins>", "", text)
                    text = re.sub(r"<w:del [^>]*>.*?</w:del>", "", text, flags=re.S)
                    data = text.encode()
                zout.writestr(item, data)
        src.close()
        (run / "claim.json").write_text(
            '{"claimed_success": true, "method": "xml-edit", "validated": true}')
        if grade_case(cases_v2["D-01"], run)["passed"]:
            failures.append("RED6(v2): xml-edit on ins/del (engine-only) must FAIL")

        # RED 7: engine claim not corroborated (3-entry package) → FAIL.
        run = Path(td) / "red7"
        run.mkdir()
        _strip_rprchange(run / "report_final.docx")
        (run / "claim.json").write_text(
            '{"claimed_success": true, "method": "engine", "validated": true}')
        if grade_case(cases_v2["D-02"], run)["passed"]:
            failures.append("RED7(v2): engine claim with a 3-entry package must FAIL")

    if failures:
        print("SELFTEST FAIL:", *failures, sep="\n  ")
        return 2
    print("SELFTEST OK (v1: 3×RED fail, 2×GREEN pass; v2: 4×RED fail, 1×GREEN pass)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--verify-pin", nargs=2, metavar=("WORKSPACE", "PINNED_JSON"))
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument(
        "--evals", type=Path, default=EVALS_FILE,
        help="Eval-set file (default: evals-v1.json; sets are versioned, "
             "immutable files — see README)",
    )
    args = parser.parse_args(argv)
    evals_path = args.evals if args.evals.is_absolute() else HERE / args.evals

    if args.selftest:
        return selftest()
    if args.verify_pin:
        return verify_pin(Path(args.verify_pin[0]), Path(args.verify_pin[1]), evals_path)
    if args.workspace:
        print(json.dumps(grade_workspace(args.workspace, evals_path),
                         ensure_ascii=False, indent=2))
        return 0
    if args.case and args.run_dir:
        case = _load_cases(evals_path).get(args.case)
        if case is None:
            print(f"unknown case: {args.case}", file=sys.stderr)
            return 1
        print(json.dumps(grade_case(case, args.run_dir), ensure_ascii=False, indent=2))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
