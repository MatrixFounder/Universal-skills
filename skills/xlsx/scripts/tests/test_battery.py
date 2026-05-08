"""Battery-test driver for xlsx-7 (`xlsx_check_rules.py`) regression
fixtures.

Walks `tests/golden/manifests/*.yaml`, regenerates fixtures via
`tests/golden/inputs/_generate.py --check`, runs `xlsx_check_rules.py`
with manifest-supplied flags, and asserts (per SPEC §13 contract):

  - exit_code matches `expected.exit_code`.
  - `summary` keys are a superset of `expected.summary` keys.
  - `findings[].rule_id` set ⊇ `expected.required_rule_ids`.
  - `findings[].rule_id` set ∩ `expected.forbidden_rule_ids` == ∅.

This task (003.02) ships the **driver skeleton**:

  - `BatteryTestCase` enumerates manifests at class-collection time
    and synthesises one `test_<manifest_name>` method per manifest.
  - Every synthesised method is decorated with
    `@unittest.expectedFailure` because the implementation chain is
    in Phase-1 red state — `xlsx_check_rules.cli.main()` raises
    `NotImplementedError` until 003.14b ships the orchestrator.
  - Successive tasks (003.05–003.16) remove the `expectedFailure`
    decorator from fixtures they own.

Manifest schema (cf. 003.04a):

    id: 1
    name: clean-pass
    rules_format: json | yaml
    sheet: { ... }
    rules: |
      { "version": 1, "rules": [...] }
    expected:
      exit_code: 0
      summary: { errors: 0, warnings: 0 }
      required_rule_ids: []
      forbidden_rule_ids: []

If the manifests directory is empty (003.02 baseline, before 003.04a
populates it) the test class collects ZERO methods — `unittest`
discovery still imports the module cleanly and the suite passes
trivially.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

# Resolve directories without depending on cwd. Tests are typically
# invoked via `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest
# discover -s tests`, so __file__ is the source of truth.
_TESTS_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _TESTS_DIR.parent
_MANIFESTS_DIR = _TESTS_DIR / "golden" / "manifests"
_GENERATOR = _TESTS_DIR / "golden" / "inputs" / "_generate.py"
_CLI = _SCRIPTS_DIR / "xlsx_check_rules.py"


def _list_manifests() -> list[Path]:
    """Return the sorted list of *.yaml manifests in golden/manifests/.

    Empty list if the directory does not exist yet (pre-003.04a state)
    or contains no .yaml files. Hidden files / .gitkeep are skipped.
    """
    if not _MANIFESTS_DIR.is_dir():
        return []
    return sorted(
        p for p in _MANIFESTS_DIR.glob("*.yaml")
        if not p.name.startswith(".") and p.is_file()
    )


def _safe_method_name(stem: str) -> str:
    """Map a manifest stem (e.g. 'apostrophe-sheet') to a valid Python
    test-method identifier ('test_apostrophe_sheet'). Non-alphanumerics
    other than `_` collapse to `_`.
    """
    sanitized = "".join(c if (c.isalnum() or c == "_") else "_" for c in stem)
    return f"test_{sanitized}"


def _load_manifest(path: Path) -> dict[str, Any]:
    """Load a trusted manifest (our own files; no hardening required —
    003.09 hardens UNTRUSTED rules.yaml input). ruamel.yaml is already
    pinned in requirements.txt for the xlsx-7 work, so use it; if
    unavailable, fall back to PyYAML.
    """
    try:
        from ruamel.yaml import YAML
        return YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    except ImportError:  # pragma: no cover — ruamel is required by xlsx-7
        import yaml as _pyyaml  # type: ignore[import-not-found]
        return _pyyaml.safe_load(path.read_text(encoding="utf-8"))


def _run_battery_case(manifest: dict[str, Any], manifest_path: Path) -> tuple[int, dict[str, Any] | None, str]:
    """Regenerate the fixture for `manifest`, invoke xlsx_check_rules.py
    with manifest-supplied flags, return (exit_code, parsed_envelope, stderr).

    The parsed envelope is `None` if the CLI did not emit JSON (either
    because `--no-json` was selected or because the run aborted before
    F9 emit ran — common in the Phase-1 red state).
    """
    fixture_stem = manifest_path.stem
    inputs_dir = _TESTS_DIR / "golden" / "inputs"
    workbook = inputs_dir / f"{fixture_stem}.xlsx"
    rules_format = manifest.get("rules_format", "json")
    rules = inputs_dir / f"{fixture_stem}.rules.{rules_format}"

    # Regenerate stale fixtures (Q5 hybrid; small fixtures regen each run).
    # In 003.02 the generator is a stub from 003.03 — invoking it is OK
    # (it exits 0 on no-op). Once 003.04a ships, real fixtures appear.
    if _GENERATOR.exists():
        subprocess.run(
            [sys.executable, str(_GENERATOR), "--check"],
            cwd=_SCRIPTS_DIR, check=False, capture_output=True,
        )

    cli_argv = [sys.executable, str(_CLI), str(workbook), "--rules", str(rules)]
    extra_flags = list(manifest.get("flags") or [])
    # Default to --json so the driver can assert against the envelope
    # shape (matches production usage where xlsx-7 pipes into xlsx-6).
    if "--json" not in extra_flags and "--no-json" not in extra_flags:
        cli_argv.append("--json")
    cli_argv.extend(extra_flags)
    proc = subprocess.run(cli_argv, capture_output=True, text=True, cwd=_SCRIPTS_DIR)
    parsed: dict[str, Any] | None
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return proc.returncode, parsed, proc.stderr


def _assert_manifest_expectations(testcase: unittest.TestCase, manifest: dict[str, Any],
                                    exit_code: int, envelope: dict[str, Any] | None) -> None:
    """Apply the four assertions documented in the module docstring."""
    expected = manifest.get("expected") or {}
    if "exit_code" in expected:
        testcase.assertEqual(exit_code, expected["exit_code"],
                              msg=f"exit_code mismatch for {manifest.get('name')}")
    if envelope is None:
        if expected.get("requires_envelope", True):
            testcase.fail(
                f"manifest {manifest.get('name')} expected JSON envelope on stdout; "
                "got non-JSON output (likely Phase-1 NotImplementedError)"
            )
        return
    summary = envelope.get("summary") or {}
    expected_summary = expected.get("summary") or {}
    for k, v in expected_summary.items():
        testcase.assertEqual(summary.get(k), v,
                              msg=f"summary[{k!r}] mismatch for {manifest.get('name')}")
    found_ids = {f.get("rule_id") for f in (envelope.get("findings") or [])}
    required = set(expected.get("required_rule_ids") or [])
    forbidden = set(expected.get("forbidden_rule_ids") or [])
    testcase.assertGreaterEqual(found_ids, required,
                                 msg=f"missing required rule_ids: {required - found_ids}")
    testcase.assertEqual(found_ids & forbidden, set(),
                         msg=f"forbidden rule_ids appeared: {found_ids & forbidden}")


def _make_test_method(manifest_path: Path):
    """Factory: closes over manifest_path and returns the test method."""
    def test_method(self: unittest.TestCase) -> None:
        manifest = _load_manifest(manifest_path)
        exit_code, envelope, _stderr = _run_battery_case(manifest, manifest_path)
        _assert_manifest_expectations(self, manifest, exit_code, envelope)
    test_method.__doc__ = f"battery: {manifest_path.stem}"
    return test_method


class BatteryTestCaseMeta(type):
    """Metaclass that synthesises one `test_<manifest_name>` method per
    manifest at class-creation time.

    Default decoration: `unittest.expectedFailure` — Phase-1 red state
    does NOT pollute CI signal. Per-task xpass promotion: if a manifest
    sets `xfail: false`, its synthesised test runs without the
    decorator. The 003.16a final sweep removes the default xfail
    altogether after all F-regions have shipped.
    """
    def __new__(mcs, name, bases, namespace):
        for manifest_path in _list_manifests():
            method_name = _safe_method_name(manifest_path.stem)
            if method_name in namespace:  # don't shadow hand-written tests
                continue
            method = _make_test_method(manifest_path)
            try:
                manifest = _load_manifest(manifest_path)
                xfail = bool(manifest.get("xfail", True))
            except Exception:  # noqa: BLE001 — manifest invalid; default to xfail
                xfail = True
            if xfail:
                method = unittest.expectedFailure(method)
            namespace[method_name] = method
        return super().__new__(mcs, name, bases, namespace)


class BatteryTestCase(unittest.TestCase, metaclass=BatteryTestCaseMeta):
    """Driver harness for xlsx-7 regression battery (SPEC §13).

    Auto-populates one xfail test method per `tests/golden/manifests/*.yaml`.
    See module docstring for the manifest schema and assertion contract.
    """
    pass


class TestCanaryMeta(unittest.TestCase):
    """Meta-test wrapper: runs `canary_check.sh` and asserts exit 0.

    The canary script patches each `xlsx_check_rules` module and
    asserts the corresponding battery test FAILS — proving the
    battery actually exercises the patched code path. Skipped
    saboteurs (003.04b deps) don't fail the run, but the canary
    must report at least one ACTIVE saboteur so the meta-test
    isn't silently passing on an all-skip run.
    """

    def test_canary_check_sh_exits_zero(self) -> None:
        script = Path(__file__).parent / "canary_check.sh"
        self.assertTrue(script.exists(), f"missing canary script: {script}")
        result = subprocess.run(
            ["bash", str(script)], capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(
            result.returncode, 0,
            f"canary_check.sh exited {result.returncode}\n"
            f"--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}",
        )
        # Guard against the all-skip silent-pass mode: at least ONE
        # active saboteur must have run (otherwise nothing was verified).
        self.assertIn("PASS=", result.stdout)
        # Parse "PASS=N FAIL=M SKIP=K" line.
        for line in result.stdout.splitlines():
            if line.startswith("canary_check.sh: PASS="):
                # e.g. "canary_check.sh: PASS=1 FAIL=0 SKIP=9 (...)"
                parts = line.split()
                pass_n = int(parts[1].split("=")[1])
                self.assertGreaterEqual(
                    pass_n, 1,
                    "no active saboteurs ran — meta-test is vacuous",
                )
                break
        else:
            self.fail("canary_check.sh did not emit summary line")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
