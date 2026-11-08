#!/usr/bin/env python3
"""Offline tests for archive/skill-auto-improve-improvement-spec_20261108.md (R1-R17).

Each class names the requirement it locks. Everything runs on injected fakes:
no API key, no agentic CLI, no network. CLI-level tests call `main()` with the
provider preflight and the LLM factories stubbed; the git tests build a
throwaway repository in a temp dir.

    cd skills/skill-auto-improve/scripts
    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent
SKILL = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import auto_improve as ai  # noqa: E402
import check_immutability as ci  # noqa: E402
import common as c  # noqa: E402
import grade_dataset as gd  # noqa: E402
import llm_config  # noqa: E402

PROMPT = "# Prompt\n\n## Rules\nBe brief.\n\n## Style\nUse plain words.\n"


def _section_proposer(summaries=None, body=lambda i: f"Be brief. v{i}"):
    """Proposer that rewrites `## Rules` with a fresh line each call."""
    calls = {"n": 0}

    def proposer(ctx):
        calls["n"] += 1
        i = calls["n"]
        summary = summaries[i - 1] if summaries else f"edit {i}"
        return {"proposal": {"diff_format": "section-replace", "target_section": "## Rules",
                             "new_content": f"## Rules\n{body(i)}\n", "change_summary": summary},
                "usage": {}}
    proposer.calls = calls
    return proposer


def _seq_evaluator(scores):
    it = iter(scores)
    calls = {"n": 0}

    def evaluator(path):
        calls["n"] += 1
        return {"score": next(it), "secondary": None, "usage": {}}
    evaluator.calls = calls
    return evaluator


def _tsv_statuses(ws: Path) -> list[str]:
    rows = (ws / "improvement_history.tsv").read_text(encoding="utf-8").splitlines()[1:]
    return [r.split("\t")[3] for r in rows]


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.art = self.tmp / "prompt.md"
        self.art.write_text(PROMPT, encoding="utf-8")

    def loop(self, proposer, evaluator, ws="ws", artifact=None, artifact_type="prompt", **kw):
        cfg = kw.pop("config", None) or ai.LoopConfig(**kw.pop("cfg", {}))
        return ai.run_improvement_loop(artifact or self.art, artifact_type, self.tmp / ws,
                                       proposer=proposer, evaluator=evaluator, config=cfg, **kw)


# ---------------------------------------------------------------------------
# CLI harness
# ---------------------------------------------------------------------------
def _run_main(argv, **overrides):
    """Run ai.main(argv) with the preflight and the LLM factories stubbed.

    `overrides` replace attributes of the auto_improve module for the call.
    Returns (rc, stdout, stderr).
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(llm_config, "preflight_provider",
                                              lambda *a, **k: None))
        stack.enter_context(mock.patch.object(ai, "build_adversarial_reviewer",
                                              lambda *a, **k: None))
        for name, value in overrides.items():
            stack.enter_context(mock.patch.object(ai, name, value))
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        rc = ai.main(argv)
    return rc, out.getvalue(), err.getvalue()


def _capture_loop(store: dict):
    """A run_improvement_loop stand-in that records its arguments."""
    def fake(artifact_path, artifact_type, workspace, **kwargs):
        store.update(kwargs, artifact_type=artifact_type)
        return {"best_score": 0.5, "baseline_score": 0.5, "exit_reason": "budget_iterations",
                "iterations": [{"iter": 0, "score": 0.5, "status": "baseline"}], "kept": 0,
                "spent_tokens": 0, "warnings": []}
    return fake


def _fake_dataset_proposer(*_a, **_k):
    def proposer(ctx):
        i = ctx["iteration"]
        return {"proposal": {"diff_format": "dataset-op", "change_summary": f"add negative {i}",
                             "dataset_ops": [{"op": "add", "item": {
                                 "id": f"n{i}", "query": f"write a rust http server {i}",
                                 "should_trigger": False}}]},
                "usage": {}}
    return proposer


def _git(cwd, *args):
    return subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
                          cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)


# ---------------------------------------------------------------------------
# R1 — an evaluator / decider failure never crashes the loop or leaves an edit
# ---------------------------------------------------------------------------
class TestR1EvaluatorErrors(_Tmp):
    def test_evaluator_error_after_apply_restores_and_logs_error(self):
        calls = {"n": 0}

        def evaluator(path):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"score": 0.5, "secondary": None, "usage": {}}
            raise RuntimeError("simulated API error after retries")
        proposer = _section_proposer()
        res = self.loop(proposer, evaluator, cfg=dict(max_iterations=2, noise_sigma=0.05,
                                                       convergence_window=9))
        self.assertEqual(self.art.read_text(encoding="utf-8"), PROMPT)   # byte-identical
        self.assertEqual(_tsv_statuses(self.tmp / "ws"), ["baseline", "error", "error"])
        self.assertEqual(proposer.calls["n"], 2)                          # the loop went on
        self.assertEqual(res["kept"], 0)

    def test_decider_error_restores_and_logs_error(self):
        def decider(champ, cand):
            raise RuntimeError("judge unavailable")
        proposer = _section_proposer()
        res = self.loop(proposer, _seq_evaluator([0.5, 0.9, 0.9]), decider=decider,
                        cfg=dict(max_iterations=2, convergence_window=9))
        self.assertEqual(self.art.read_text(encoding="utf-8"), PROMPT)
        self.assertIn("error", _tsv_statuses(self.tmp / "ws"))
        self.assertEqual(res["kept"], 0)

    def test_baseline_error_raises_and_leaves_the_file(self):
        def evaluator(path):
            raise RuntimeError("no backend")
        with self.assertRaises(ai.BaselineError):
            self.loop(_section_proposer(), evaluator)
        self.assertEqual(self.art.read_text(encoding="utf-8"), PROMPT)

    def test_an_exception_escaping_after_apply_restores_first(self):
        calls = {"n": 0}

        def evaluator(path):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"score": 0.5, "secondary": None, "usage": {}}
            raise KeyboardInterrupt  # not an Exception: it must propagate
        with self.assertRaises(KeyboardInterrupt):
            self.loop(_section_proposer(), evaluator, cfg=dict(max_iterations=3))
        self.assertEqual(self.art.read_text(encoding="utf-8"), PROMPT)

    def test_cli_baseline_error_exits_2_and_file_is_unchanged(self):
        ds = self.tmp / "evals.json"
        shutil.copy(SKILL / "evals" / "fixtures" / "thin-dataset.json", ds)
        before = ds.read_bytes()

        def broken_evaluator_factory(*_a, **_k):
            def evaluator(path):
                raise RuntimeError("scorer exploded")
            return evaluator
        rc, _out, err = _run_main(
            ["--artifact-path", str(ds), "--artifact-type", "dataset",
             "--workspace", str(self.tmp / "ws")],
            build_default_proposer=_fake_dataset_proposer,
            build_default_evaluator=broken_evaluator_factory)
        self.assertEqual(rc, 2)
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertIn("baseline", err)
        self.assertEqual(ds.read_bytes(), before)


# ---------------------------------------------------------------------------
# R2 — --git-isolation is never silently dropped
# ---------------------------------------------------------------------------
@unittest.skipUnless(shutil.which("git"), "git is not installed")
class TestR2GitIsolation(_Tmp):
    def _repo(self):
        repo = self.tmp / "repo"
        repo.mkdir()
        shutil.copy(SKILL / "evals" / "fixtures" / "thin-dataset.json", repo / "evals.json")
        _git(repo, "init", "-q")
        _git(repo, "checkout", "-q", "-b", "main")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "init")
        return repo

    def _argv(self, repo):
        return ["--artifact-path", str(repo / "evals.json"), "--artifact-type", "dataset",
                "--workspace", str(self.tmp / "ws"), "--max-iterations", "2", "--git-isolation"]

    def test_existing_run_branch_gets_a_fresh_branch(self):
        repo = self._repo()
        _git(repo, "branch", "auto-improve/evals.json/run")
        rc, out, _err = _run_main(self._argv(repo), build_default_proposer=_fake_dataset_proposer)
        self.assertEqual(rc, 0)
        branch = _git(repo, "branch", "--show-current").stdout.strip()
        self.assertRegex(branch, r"^auto-improve/evals\.json/\d{8}T\d{6}Z$")
        self.assertEqual(json.loads(out)["summary"]["run"]["branch"], branch)
        # nothing landed on main
        self.assertEqual(_git(repo, "log", "--oneline", "main").stdout.count("\n"), 1)
        report = (self.tmp / "ws" / "improvement_report.md").read_text(encoding="utf-8")
        self.assertIn(branch, report)

    def test_branch_creation_failure_aborts_on_the_original_branch(self):
        repo = self._repo()
        rc, _out, err = _run_main(self._argv(repo), build_default_proposer=_fake_dataset_proposer,
                                  create_branch=lambda *a, **k: False)
        self.assertEqual(rc, 2)
        self.assertIn("could not create branch", err)
        self.assertEqual(_git(repo, "branch", "--show-current").stdout.strip(), "main")
        self.assertFalse((self.tmp / "ws").exists())

    def test_outside_git_aborts(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        shutil.copy(SKILL / "evals" / "fixtures" / "thin-dataset.json", plain / "evals.json")
        with mock.patch.object(ai, "is_git_repo", lambda *_a: False):
            rc, _out, err = _run_main(self._argv(plain),
                                      build_default_proposer=_fake_dataset_proposer)
        self.assertEqual(rc, 2)
        self.assertIn("not inside a git repository", err)


# ---------------------------------------------------------------------------
# R3 — no agentic backend: an honest exit 2, never a traceback or a silent swap
# ---------------------------------------------------------------------------
class TestR3NoAgenticBackend(_Tmp):
    def test_gemini_skill_run_exits_2_without_traceback(self):
        sk = self.tmp / "test-skill-broken"
        shutil.copytree(SKILL / "evals" / "fixtures" / "test-skill-broken", sk)
        env = {**os.environ, "AUTO_IMPROVE_VENDOR": "gemini", "DEFAULT_PROVIDER": "gemini"}
        res = subprocess.run(
            [sys.executable, str(SCRIPTS / "auto_improve.py"), "--artifact-path", str(sk),
             "--artifact-type", "skill", "--eval-set", str(sk / "evals" / "evals.json"),
             "--workspace", str(self.tmp / "ws"), "--max-iterations", "1"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
            timeout=120, check=False)
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertNotIn("Traceback", res.stderr)
        self.assertEqual(len(res.stderr.strip().splitlines()), 1, res.stderr)
        self.assertIn("agentic backend", res.stderr)

    def test_docs_do_not_promise_an_llm_grading_fallback(self):
        pattern = re.compile(r"(fall(?:s)? back|degrades?) to (?:llm|LLM)", re.IGNORECASE)
        files = [SKILL / "SKILL.md", SKILL / ".env.example",
                 *SKILL.joinpath("references").rglob("*.md"),
                 *SCRIPTS.glob("*.py"), *SCRIPTS.joinpath("backends").glob("*.py")]
        manual = SKILL.parents[1] / "docs" / "Manuals" / "skill-auto-improve_manual.md"
        if manual.is_file():
            files.append(manual)
        offenders = [f"{p.name}:{n}" for p in files if p.is_file()
                     for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                     if pattern.search(line)]
        self.assertEqual(offenders, [])


# ---------------------------------------------------------------------------
# R4 — every documented flag exists
# ---------------------------------------------------------------------------
class TestR4DocumentedFlags(unittest.TestCase):
    # Flags of OTHER tools that the docs quote on purpose.
    FOREIGN = {
        "--unsafe-paths",              # git apply (why raw diffs were removed)
        "--output-format",             # claude -p (how run_eval detects triggers)
        "--include-partial-messages",  # claude -p
        "--strict",                    # validate_skill.py
    }
    _FLAG = re.compile(r"(?<![\w-])--[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
    _ADD_ARG = re.compile(r"add_argument\(\s*((?:[\"']-{1,2}[a-z0-9-]+[\"']\s*,?\s*)+)")

    def _known(self) -> set[str]:
        known = {opt for a in ai.build_parser()._actions for opt in a.option_strings}
        for py in SCRIPTS.rglob("*.py"):
            if "tests" in py.parts or ".venv" in py.parts:
                continue
            for group in self._ADD_ARG.findall(py.read_text(encoding="utf-8")):
                known |= set(re.findall(r"--[a-z0-9-]+", group))
        return known

    def _documented(self) -> dict[str, list[str]]:
        docs = [SKILL / "SKILL.md", *SKILL.joinpath("references").rglob("*.md"),
                *SKILL.joinpath("examples").glob("*.md")]
        manual = SKILL.parents[1] / "docs" / "Manuals" / "skill-auto-improve_manual.md"
        if manual.is_file():
            docs.append(manual)
        found: dict[str, list[str]] = {}
        for path in docs:
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for flag in self._FLAG.findall(line):
                    found.setdefault(flag, []).append(f"{path.name}:{n}")
        return found

    def test_documented_flags_exist_in_a_cli(self):
        known = self._known() | self.FOREIGN
        missing = {f: where[:3] for f, where in self._documented().items() if f not in known}
        self.assertEqual(missing, {})

    def test_the_two_missing_flags_now_reach_the_loop(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        ds = tmp / "evals.json"
        shutil.copy(SKILL / "evals" / "fixtures" / "thin-dataset.json", ds)
        store: dict = {}
        rc, _o, _e = _run_main(
            ["--artifact-path", str(ds), "--artifact-type", "dataset", "--workspace",
             str(tmp / "ws"), "--min-improvement", "0.07", "--convergence-window", "5"],
            build_default_proposer=_fake_dataset_proposer, run_improvement_loop=_capture_loop(store))
        self.assertEqual(rc, 0)
        self.assertEqual(store["config"].min_improvement, 0.07)
        self.assertEqual(store["config"].convergence_window, 5)


# ---------------------------------------------------------------------------
# R5 — calibrated noise band, averaged champion, confirmed KEEPs
# ---------------------------------------------------------------------------
class TestR5NoiseBand(_Tmp):
    def test_calibration_derives_sigma_from_baseline_sd(self):
        res = self.loop(_section_proposer(), _seq_evaluator([0.5, 0.6, 0.7, 0.6, 0.6, 0.6]),
                        cfg=dict(max_iterations=1, calibrate_runs=3, convergence_window=9))
        noise = res["noise"]
        self.assertEqual(noise["calibration_runs"], 3)
        self.assertAlmostEqual(noise["sd"], 0.1, places=6)
        self.assertAlmostEqual(noise["sigma"], 1.64 * 2 ** 0.5 * 0.1, places=6)
        self.assertEqual(noise["sigma_source"], "calibrated")
        self.assertAlmostEqual(res["baseline_score"], 0.6)
        tsv = (self.tmp / "ws" / "improvement_history.tsv").read_text(encoding="utf-8")
        self.assertIn("sd=0.1000", tsv)                    # recorded in the TSV baseline row

    def test_explicit_noise_sigma_wins(self):
        res = self.loop(_section_proposer(), _seq_evaluator([0.5, 0.6, 0.7, 0.6]),
                        cfg=dict(max_iterations=1, calibrate_runs=3, noise_sigma=0.01,
                                 convergence_window=9))
        self.assertEqual(res["noise"]["sigma"], 0.01)
        self.assertEqual(res["noise"]["sigma_source"], "explicit")

    def test_keep_is_remeasured_and_the_champion_is_the_mean(self):
        # baseline x3 (mean .50), gate .70, re-measure x3 (mean .66)
        ev = _seq_evaluator([0.50, 0.52, 0.48, 0.70, 0.64, 0.66, 0.68])
        res = self.loop(_section_proposer(), ev,
                        cfg=dict(max_iterations=1, calibrate_runs=3, convergence_window=9))
        self.assertEqual(res["kept"], 1)
        self.assertAlmostEqual(res["best_score"], 0.66)
        self.assertEqual(ev.calls["n"], 7)

    def test_an_unconfirmed_keep_is_reverted(self):
        # gate .70 clears sigma, but the re-measured mean (.50) does not
        ev = _seq_evaluator([0.50, 0.52, 0.48, 0.70, 0.49, 0.50, 0.51])
        res = self.loop(_section_proposer(), ev,
                        cfg=dict(max_iterations=1, calibrate_runs=3, convergence_window=9))
        self.assertEqual(res["kept"], 0)
        self.assertAlmostEqual(res["best_score"], 0.50)
        self.assertEqual(self.art.read_text(encoding="utf-8"), PROMPT)
        self.assertEqual(_tsv_statuses(self.tmp / "ws")[-1], "no-signal")
        self.assertIn("not confirmed", res["iterations"][-1]["summary"])

    def test_zero_sigma_warns_only_for_a_nondeterministic_evaluator(self):
        res = self.loop(_section_proposer(), _seq_evaluator([0.5, 0.4]), cfg=dict(max_iterations=1))
        self.assertTrue(any("sigma is 0" in w for w in res["warnings"]))
        res = self.loop(_section_proposer(), _seq_evaluator([0.5, 0.4]), ws="ws2",
                        cfg=dict(max_iterations=1, deterministic=True))
        self.assertFalse(any("sigma is 0" in w for w in res["warnings"]))

    def test_null_edits_are_rarely_kept_with_calibration(self):
        """Probe E: no-effect edits under a noisy evaluator (sd 0.05)."""
        runs, with_keep = 120, 0
        for seed in range(runs):
            rng = random.Random(1000 + seed)
            ws = self.tmp / f"e{seed}"
            art = self.tmp / f"p{seed}.md"
            art.write_text(PROMPT, encoding="utf-8")
            res = ai.run_improvement_loop(
                art, "prompt", ws, proposer=_section_proposer(),
                evaluator=lambda p, r=rng: {"score": min(1, max(0, r.gauss(0.6, 0.05))),
                                            "secondary": None, "usage": {}},
                config=ai.LoopConfig(max_iterations=10, calibrate_runs=3))
            with_keep += res["kept"] > 0
        self.assertLessEqual(with_keep / runs, 0.10)

    def test_dataset_mode_stays_single_measurement(self):
        ds = self.tmp / "evals.json"
        shutil.copy(SKILL / "evals" / "fixtures" / "thin-dataset.json", ds)
        calls = {"n": 0}

        def evaluator(path):
            calls["n"] += 1
            return {"score": gd.score_dataset(Path(path))["score"], "secondary": None, "usage": {}}
        res = ai.run_improvement_loop(
            ds, "dataset", self.tmp / "wsd", proposer=_fake_dataset_proposer(), evaluator=evaluator,
            config=ai.LoopConfig(max_iterations=2, deterministic=True, convergence_window=9))
        self.assertEqual(calls["n"], 3)          # baseline + one per iteration, no re-measure
        self.assertEqual(res["noise"]["sigma"], 0.0)
        self.assertEqual(res["warnings"], [])


# ---------------------------------------------------------------------------
# R6 — holdout split
# ---------------------------------------------------------------------------
class TestR6Holdout(_Tmp):
    def test_split_is_stratified_reproducible_and_leaves_global_rng_alone(self):
        cases = ([{"id": f"p{i}", "query": f"p{i}", "should_trigger": True} for i in range(6)]
                 + [{"id": f"n{i}", "query": f"n{i}", "should_trigger": False} for i in range(4)])
        random.seed(123)
        expected_next = random.random()
        random.seed(123)
        train, hold = c.split_eval_set(cases, 0.4, seed=42)
        self.assertEqual(random.random(), expected_next)
        self.assertEqual(len(train) + len(hold), 10)
        self.assertEqual(sum(1 for x in hold if x["should_trigger"] is False), 1)
        self.assertEqual(sum(1 for x in hold if x["should_trigger"] is True), 2)
        self.assertEqual(c.split_eval_set(cases, 0.4, seed=42), (train, hold))

    def test_overfit_warning_when_train_rises_and_holdout_does_not(self):
        train = _seq_evaluator([0.5, 0.8, 0.8])
        res = self.loop(_section_proposer(), train,
                        holdout_evaluator=lambda p: {"score": 0.6, "secondary": None, "usage": {}},
                        cfg=dict(max_iterations=1, noise_sigma=0.05, convergence_window=9))
        final = res["final"]
        self.assertEqual(final["set"], "holdout")
        self.assertTrue(final["overfit_warning"])
        self.assertTrue(any(w.startswith("overfit_warning") for w in res["warnings"]))

    def _main_with_cases(self, n, extra=()):
        cases = [{"id": f"c{i}", "prompt": f"case {i}", "expectations": ["x"]} for i in range(n)]
        es = self.tmp / f"es{n}.json"
        es.write_text(json.dumps(cases), encoding="utf-8")
        seen: list[int] = []

        def evaluator_factory(artifact_type, *, eval_set, **_k):
            seen.append(len(eval_set))
            return lambda p: {"score": 0.5, "secondary": None, "usage": {}}
        store: dict = {}
        rc, _o, err = _run_main(
            ["--artifact-path", str(self.art), "--artifact-type", "prompt", "--eval-set", str(es),
             "--workspace", str(self.tmp / "ws"), *extra],
            build_default_proposer=lambda *a, **k: _section_proposer(),
            build_default_evaluator=evaluator_factory, run_improvement_loop=_capture_loop(store))
        return rc, seen, store, err

    def test_cli_default_holds_out_40_percent_from_10_cases(self):
        rc, seen, store, _err = self._main_with_cases(10)
        self.assertEqual(rc, 0)
        self.assertEqual(seen, [6, 4])                     # train evaluator, holdout evaluator
        self.assertIsNotNone(store["holdout_evaluator"])

    def test_cli_no_holdout_below_10_cases(self):
        rc, seen, store, _err = self._main_with_cases(9)
        self.assertEqual((rc, seen), (0, [9]))
        self.assertIsNone(store["holdout_evaluator"])

    def test_cli_holdout_is_refused_for_a_dataset(self):
        ds = self.tmp / "evals.json"
        shutil.copy(SKILL / "evals" / "fixtures" / "thin-dataset.json", ds)
        rc, _o, err = _run_main(["--artifact-path", str(ds), "--artifact-type", "dataset",
                                 "--workspace", str(self.tmp / "ws"), "--holdout", "0.3"],
                                build_default_proposer=_fake_dataset_proposer)
        self.assertEqual(rc, 2)
        self.assertIn("--holdout", err)


# ---------------------------------------------------------------------------
# R7 — final confirmation with a bootstrap CI
# ---------------------------------------------------------------------------
class TestR7FinalConfirmation(_Tmp):
    def _by_artifact(self, winner_scores, baseline_scores):
        """Evaluator that scores by WHICH file it reads (baseline snapshot vs live)."""
        w, b = iter(winner_scores), iter(baseline_scores)

        def evaluator(path):
            text = Path(path).read_text(encoding="utf-8")
            return {"score": next(w) if "v1" in text else next(b), "secondary": None, "usage": {}}
        return evaluator

    def test_real_effect_is_confirmed_with_a_ci(self):
        ev = self._by_artifact(winner_scores=[0.8, 0.79, 0.81, 0.8, 0.82, 0.78],
                               baseline_scores=[0.5, 0.49, 0.51, 0.5, 0.52, 0.48])
        res = self.loop(_section_proposer(), ev,
                        cfg=dict(max_iterations=1, noise_sigma=0.05, final_runs=5,
                                 convergence_window=9))
        final = res["final"]
        self.assertEqual(final["verdict"], "confirmed")
        self.assertEqual(final["runs"], 5)
        self.assertGreater(final["ci_low"], 0)
        report = ai.write_report(self.tmp / "ws", res, self.art, "prompt", "fallback", None)
        self.assertIn("Bootstrap 95% CI", report.read_text(encoding="utf-8"))

    def test_zero_effect_is_not_confirmed(self):
        ev = _seq_evaluator([0.5, 0.7] + [0.6] * 10)   # a lucky KEEP, then no real effect
        res = self.loop(_section_proposer(), ev,
                        cfg=dict(max_iterations=1, noise_sigma=0.05, final_runs=5,
                                 convergence_window=9))
        self.assertEqual(res["kept"], 1)
        self.assertEqual(res["final"]["verdict"], "not confirmed")

    def test_nothing_kept_means_no_confirmation(self):
        res = self.loop(_section_proposer(), _seq_evaluator([0.5, 0.4]),
                        cfg=dict(max_iterations=1, final_runs=5, convergence_window=9))
        self.assertIsNone(res["final"])

    def test_baseline_snapshot_survives_pruning(self):
        self.loop(_section_proposer(), _seq_evaluator([0.5] + [0.4] * 6),
                  cfg=dict(max_iterations=6, convergence_window=99))
        snap = self.tmp / "ws" / "snapshots" / "baseline" / "prompt.md"
        self.assertEqual(snap.read_text(encoding="utf-8"), PROMPT)
        self.assertEqual(len(list((self.tmp / "ws" / "snapshots").glob("iter-*"))), 2)


# ---------------------------------------------------------------------------
# R8 — winner's curse in best-of-N
# ---------------------------------------------------------------------------
class TestR8WinnersCurse(_Tmp):
    def test_threshold_is_not_reached_by_the_max_of_n(self):
        art = self.tmp / "email.txt"
        art.write_text("Hi. Buy my thing.", encoding="utf-8")

        def proposer(ctx):  # best-of-N winner reports its (selected-for-high) score
            return {"proposal": {"diff_format": "text-replace", "find": "Hi.",
                                 "replace": f"Hi there {ctx['iteration']}.",
                                 "change_summary": f"greet {ctx['iteration']}"},
                    "usage": {}, "score": 0.95}
        ev = _seq_evaluator([0.6, 0.62])                 # baseline, independent re-measure
        res = ai.run_improvement_loop(
            art, "text", self.tmp / "ws", proposer=proposer, evaluator=ev,
            config=ai.LoopConfig(max_iterations=1, score_threshold=0.9, convergence_window=9),
            decider=lambda champ, cand: "keep")
        self.assertEqual(res["kept"], 1)
        self.assertAlmostEqual(res["best_score"], 0.62)
        self.assertNotEqual(res["exit_reason"], "optimal")
        self.assertEqual(ev.calls["n"], 2)


# ---------------------------------------------------------------------------
# R9 — prompts are measured by running them
# ---------------------------------------------------------------------------
class _FakeMgr:
    """Stand-in LLMConfigManager. executor: answers without doing the job;
    grader: static → rewards an artifact that MENTIONS every expectation,
    executed → passes a case only if its RESPONSE does what it should."""

    created: list = []

    def __init__(self, profile, provider=None):
        self.profile, self.provider = profile, provider or "anthropic"
        self.model_name, self.fallback_models, self.model_candidates = f"{profile}-model", [], []
        _FakeMgr.created.append(self)

    def generate_content_with_meta(self, system, user, response_schema=None):
        if self.profile == "executor":
            return {"text": "We are looking into it.", "usage": {"total_tokens": 5}}
        payload = json.loads(user)
        if "artifact" in payload:                       # static
            text = payload["artifact"].lower()
            passed = sum(1 for case in payload["cases"]
                         if all(w in text for w in ("greets", "signature")))
            total = len(payload["cases"])
        else:                                           # executed
            passed = sum(1 for case in payload["cases"] if "-- Support Team" in case["response"])
            total = len(payload["cases"])
        return {"text": json.dumps({"passed": passed, "total": total}),
                "usage": {"total_tokens": 7}}


class TestR9ExecutedPromptEval(_Tmp):
    FIX = SKILL / "evals" / "fixtures"

    def setUp(self):
        super().setUp()
        _FakeMgr.created = []
        patcher = mock.patch.object(llm_config, "LLMConfigManager", _FakeMgr)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cases = json.loads((self.FIX / "reciting-prompt.evals.json").read_text(encoding="utf-8"))

    def _score(self, mode):
        ev = ai.build_default_evaluator("prompt", eval_set=self.cases, vendor="fallback",
                                        runs_per_query=1, model=None, prompt_eval=mode)
        return ev(self.FIX / "reciting-prompt.md")["score"]

    def test_reciting_prompt_scores_lower_when_executed(self):
        static, executed = self._score("static"), self._score("executed")
        self.assertEqual(static, 1.0)
        self.assertEqual(executed, 0.0)
        self.assertLess(executed, static)

    def test_the_executed_grader_never_sees_the_artifact(self):
        seen = []
        orig = _FakeMgr.generate_content_with_meta

        def spy(self, system, user, response_schema=None):
            if self.profile == "grader":
                seen.append(user)
            return orig(self, system, user, response_schema)
        with mock.patch.object(_FakeMgr, "generate_content_with_meta", spy):
            self._score("executed")
        prompt_text = (self.FIX / "reciting-prompt.md").read_text(encoding="utf-8")
        self.assertTrue(seen)
        self.assertNotIn("refund\ntimeline", seen[0])
        self.assertNotIn(prompt_text.splitlines()[3], seen[0])

    def test_cli_requires_an_input_per_case_and_names_the_mode(self):
        es = self.tmp / "no_input.json"
        es.write_text(json.dumps([{"id": "a", "expectations": ["x"]}]), encoding="utf-8")
        rc, _o, err = _run_main(["--artifact-path", str(self.art), "--artifact-type", "prompt",
                                 "--eval-set", str(es), "--workspace", str(self.tmp / "ws")])
        self.assertEqual(rc, 2)
        self.assertIn("--prompt-eval static", err)
        store: dict = {}
        rc, _o, _e = _run_main(
            ["--artifact-path", str(self.art), "--artifact-type", "prompt", "--eval-set",
             str(self.FIX / "reciting-prompt.evals.json"), "--workspace", str(self.tmp / "ws2")],
            build_default_proposer=lambda *a, **k: _section_proposer(),
            run_improvement_loop=_capture_loop(store))
        self.assertEqual(rc, 0)
        report = (self.tmp / "ws2" / "improvement_report.md").read_text(encoding="utf-8")
        self.assertIn("executed", report)


# ---------------------------------------------------------------------------
# R10 — a broken grader answer is an error, never a 0 score
# ---------------------------------------------------------------------------
class _ScriptedMgr:
    def __init__(self, replies):
        self.replies = list(replies)
        self.model_name, self.fallback_models, self.model_candidates = "m", [], []
        self.calls = 0

    def __call__(self, profile, **_k):
        return self

    def generate_content_with_meta(self, system, user, response_schema=None):
        self.calls += 1
        return {"text": self.replies.pop(0), "usage": {"total_tokens": 3}}


class TestR10BrokenGrader(_Tmp):
    def test_static_grader_retries_once_then_raises(self):
        mgr = _ScriptedMgr(["not json", "{oops"])
        with mock.patch.object(llm_config, "LLMConfigManager", mgr):
            ev = ai._build_llm_grader([{"id": 1}], None)
            with self.assertRaises(ai.GraderError):
                ev(self.art)
        self.assertEqual(mgr.calls, 2)

    def test_static_grader_recovers_on_the_retry(self):
        mgr = _ScriptedMgr(["garbage", json.dumps({"passed": 1, "total": 2})])
        with mock.patch.object(llm_config, "LLMConfigManager", mgr):
            self.assertEqual(ai._build_llm_grader([{"id": 1}, {"id": 2}], None)(self.art)["score"], 0.5)

    def test_verdict_total_must_match_the_cases(self):
        mgr = _ScriptedMgr([json.dumps({"passed": 1, "total": 1}), json.dumps({"passed": 5, "total": 3})])
        with mock.patch.object(llm_config, "LLMConfigManager", mgr):
            with self.assertRaises(ai.GraderError):
                ai._build_llm_grader([{"id": 1}, {"id": 2}], None)(self.art)

    def test_rubric_scorer_excludes_broken_runs(self):
        mgr = _ScriptedMgr([json.dumps({"total_score": 80}), "broken"])
        with mock.patch.object(llm_config, "LLMConfigManager", mgr):
            score, _bd, _t = ai._build_rubric_scorer("rubric", model=None, runs=2)("text")
        self.assertAlmostEqual(score, 0.8)            # not (80 + 0) / 2

    def test_rubric_scorer_raises_when_nothing_is_usable(self):
        mgr = _ScriptedMgr(["x", "y", "z"])
        with mock.patch.object(llm_config, "LLMConfigManager", mgr):
            with self.assertRaises(ai.GraderError):
                ai._build_rubric_scorer("rubric", model=None, runs=2)("text")

    def test_garbage_from_the_grader_is_an_error_row(self):
        mgr = _ScriptedMgr([json.dumps({"passed": 1, "total": 2}), "junk", "junk"])
        with mock.patch.object(llm_config, "LLMConfigManager", mgr):
            ev = ai._build_llm_grader([{"id": 1}, {"id": 2}], None)
            res = self.loop(_section_proposer(), ev, cfg=dict(max_iterations=1, convergence_window=9))
        self.assertEqual(_tsv_statuses(self.tmp / "ws"), ["baseline", "error"])
        self.assertEqual(res["kept"], 0)
        self.assertEqual(self.art.read_text(encoding="utf-8"), PROMPT)


# ---------------------------------------------------------------------------
# R11 — a separate grader model
# ---------------------------------------------------------------------------
class TestR11GraderModel(_Tmp):
    def test_grader_provider_and_model_reach_the_grading_roles(self):
        _FakeMgr.created = []
        roles: dict = {}
        with mock.patch.object(llm_config, "LLMConfigManager", _FakeMgr):
            ai.build_default_evaluator("prompt", eval_set=[{"prompt": "p"}], vendor="fallback",
                                       runs_per_query=1, model="prop-model",
                                       prompt_eval="executed", grader_model="judge-model",
                                       grader_provider="openai", roles=roles)
        self.assertEqual(roles["grader"], "openai:judge-model")
        self.assertEqual(roles["executor"], "anthropic:prop-model")

    def test_llm_config_accepts_a_per_role_provider(self):
        with mock.patch.dict(os.environ, {"DEFAULT_PROVIDER": "anthropic"}):
            self.assertEqual(llm_config.LLMConfigManager("grader", provider="openai",
                                                         warn_missing_key=False).provider, "openai")

    def test_report_lists_models_by_role(self):
        summary = {"best_score": 0.5, "exit_reason": "stagnation", "kept": 0, "spent_tokens": 0,
                   "iterations": [{"iter": 0, "score": 0.5, "status": "baseline"}]}
        report = ai.write_report(self.tmp, summary, self.art, "prompt", "fallback", None,
                                 run_info={"roles": {"proposer": "anthropic:a",
                                                     "grader": "openai:b"}})
        text = report.read_text(encoding="utf-8")
        self.assertIn("proposer: `anthropic:a`", text)
        self.assertIn("grader: `openai:b`", text)


# ---------------------------------------------------------------------------
# R12 — dataset grader: target 20, balance, near misses
# ---------------------------------------------------------------------------
class TestR12DatasetGrader(_Tmp):
    def _write(self, cases):
        p = self.tmp / "d.json"
        p.write_text(json.dumps(cases), encoding="utf-8")
        return p

    def test_four_positives_one_negative_scores_below_08(self):
        cases = [{"id": f"p{i}", "query": q, "should_trigger": True} for i, q in enumerate([
            "Pretty-print this minified JSON", "Format my package.json nicely",
            "Reindent this JSON with two spaces", "Sort keys in a JSON object"])]
        cases.append({"id": "n1", "query": "Write a Python web scraper", "should_trigger": False})
        self.assertLess(gd.score_dataset(self._write(cases))["score"], 0.8)

    def test_balanced_twenty_with_near_misses_scores_at_least_09(self):
        pos = ["Pretty-print this minified JSON config", "Format my package.json nicely",
               "Reindent this JSON file with two spaces", "Sort the keys of a JSON object",
               "Make this JSON response readable", "Beautify the JSON in my clipboard",
               "Fix the indentation of settings.json", "Turn this one-line JSON into a tree",
               "Normalize whitespace in a JSON fixture", "Pretty format the API JSON payload"]
        neg = ["Convert this JSON to YAML", "Validate JSON against a schema",
               "Write a Python web scraper", "Explain TCP congestion control",
               "Parse JSON in Rust with serde", "Minify this JSON for production",
               "Translate this paragraph into French", "Format my Python code with black",
               "Compress package.json dependencies list", "Summarize this PDF report"]
        cases = ([{"id": f"p{i}", "query": q, "should_trigger": True} for i, q in enumerate(pos)]
                 + [{"id": f"n{i}", "query": q, "should_trigger": False} for i, q in enumerate(neg)])
        res = gd.score_dataset(self._write(cases))
        self.assertGreaterEqual(res["score"], 0.9, res)
        self.assertGreater(res["components"]["near_miss"], 0.4)

    def test_target_n_is_a_parameter(self):
        cases = [{"id": "a", "query": "q a", "should_trigger": True},
                 {"id": "b", "query": "q b", "should_trigger": False}]
        p = self._write(cases)
        self.assertEqual(gd.score_dataset(p, target_n=2)["components"]["count"], 1.0)
        self.assertEqual(gd.score_dataset(p)["components"]["count"], 0.1)

    def test_functional_sets_have_no_near_miss_component(self):
        cases = [{"id": "a", "prompt": "do x", "expectations": ["x"], "forbidden_expectations": ["y"]}]
        res = gd.score_dataset(self._write(cases))
        self.assertIsNone(res["components"]["near_miss"])
        self.assertTrue(0.0 <= res["score"] <= 1.0)


# ---------------------------------------------------------------------------
# R13 — protected sections and the deletion guard
# ---------------------------------------------------------------------------
class TestR13Protection(_Tmp):
    def test_section_replace_into_a_protected_section_is_rejected_before_apply(self):
        ev = _seq_evaluator([0.5, 0.9])
        res = self.loop(_section_proposer(), ev,
                        cfg=dict(max_iterations=1, protected_sections=("## Rules",),
                                 convergence_window=9))
        self.assertEqual(_tsv_statuses(self.tmp / "ws"), ["baseline", "immutability-violation"])
        self.assertEqual(ev.calls["n"], 1)
        self.assertEqual(res["kept"], 0)

    def test_text_replace_into_a_protected_section_is_caught_after_apply(self):
        def proposer(ctx):
            return {"proposal": {"diff_format": "text-replace", "find": "Use plain words.",
                                 "replace": "Use fancy words.", "change_summary": "style"},
                    "usage": {}}
        res = self.loop(proposer, _seq_evaluator([0.5, 0.9]), artifact_type="text",
                        decider=lambda a, b: "keep",
                        cfg=dict(max_iterations=1, protected_sections=("## Style",),
                                 convergence_window=9))
        self.assertEqual(res["kept"], 0)
        self.assertEqual(self.art.read_text(encoding="utf-8"), PROMPT)

    def test_big_deletion_is_rejected_unless_allowed(self):
        long = "# P\n\n## Rules\n" + "".join(f"rule {i}\n" for i in range(10)) + "\n## Style\nx\n"
        self.art.write_text(long, encoding="utf-8")
        proposer = _section_proposer(body=lambda i: "only one rule")
        res = self.loop(proposer, _seq_evaluator([0.5, 0.9]),
                        cfg=dict(max_iterations=1, convergence_window=9))
        self.assertEqual(_tsv_statuses(self.tmp / "ws")[-1], "shrink-guard")
        self.assertEqual(self.art.read_text(encoding="utf-8"), long)
        res = self.loop(_section_proposer(body=lambda i: "only one rule"),
                        _seq_evaluator([0.5, 0.9]), ws="ws2",
                        cfg=dict(max_iterations=1, allow_deletions=True, convergence_window=9))
        self.assertEqual(res["kept"], 1)

    def test_dropping_a_must_line_is_rejected(self):
        self.assertIsNotNone(ci.shrink_violation("## A\nYou MUST log.\nok\n", "## A\nYou should log.\nok\n"))
        self.assertIsNone(ci.shrink_violation("## A\nYou MUST log.\nok\n", "## A\nYou MUST log it.\nok\n"))

    def test_a_description_rewrite_is_not_a_deletion(self):
        old = "---\nname: x\ndescription: You MUST use this for JSON.\n---\n# X\n\n## A\nok\n"
        new = "---\nname: x\ndescription: Use for formatting JSON files.\n---\n# X\n\n## A\nok\n"
        self.assertIsNone(ci.shrink_violation(old, new))

    def test_cli_rejects_an_unknown_protected_header(self):
        es = self.tmp / "es.json"
        es.write_text(json.dumps([{"prompt": "p", "expectations": ["x"]}]), encoding="utf-8")
        rc, _o, err = _run_main(["--artifact-path", str(self.art), "--artifact-type", "prompt",
                                 "--eval-set", str(es), "--workspace", str(self.tmp / "ws"),
                                 "--protect", "## Nope"])
        self.assertEqual(rc, 2)
        self.assertIn("Nope", err)


# ---------------------------------------------------------------------------
# R14 — guard (secondary) metric
# ---------------------------------------------------------------------------
class TestR14Guard(_Tmp):
    def test_guard_regression_reverts_a_better_score(self):
        guard_values = iter([1.0, 0.0])
        res = self.loop(_section_proposer(), _seq_evaluator([0.5, 0.9]),
                        guard=lambda p: next(guard_values),
                        cfg=dict(max_iterations=1, noise_sigma=0.05, convergence_window=9))
        self.assertEqual(res["kept"], 0)
        self.assertEqual(self.art.read_text(encoding="utf-8"), PROMPT)
        rows = (self.tmp / "ws" / "improvement_history.tsv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(rows[0].split("\t")[-1], "secondary")
        self.assertEqual(rows[-1].split("\t")[-1], "0.000")
        self.assertIn("guard regressed", rows[-1])

    def test_skill_guard_runs_the_validator(self):
        fake = self.tmp / "fake_validate.py"
        fake.write_text("import sys, pathlib\n"
                        "t = (pathlib.Path(sys.argv[1]) / 'SKILL.md').read_text()\n"
                        "sys.exit(1 if 'BROKEN' in t else 0)\n", encoding="utf-8")
        sk = self.tmp / "sk"
        sk.mkdir()
        (sk / "SKILL.md").write_text("---\nname: sk\ntier: 2\n---\n# sk\n\n## Rules\nok\n",
                                     encoding="utf-8")
        guard = ai.build_skill_guard(fake)
        self.assertEqual(guard(sk), 1.0)

        def proposer(ctx):
            return {"proposal": {"diff_format": "section-replace", "target_section": "## Rules",
                                 "new_content": "## Rules\nok BROKEN\n", "change_summary": "x"},
                    "usage": {}}
        res = ai.run_improvement_loop(sk, "skill", self.tmp / "wsk", proposer=proposer,
                                      evaluator=_seq_evaluator([0.5, 0.9]), guard=guard,
                                      config=ai.LoopConfig(max_iterations=1, convergence_window=9))
        self.assertEqual(res["kept"], 0)
        self.assertNotIn("BROKEN", (sk / "SKILL.md").read_text(encoding="utf-8"))
        long = self.tmp / "long"
        long.mkdir()
        (long / "SKILL.md").write_text("x\n" * 600, encoding="utf-8")
        self.assertEqual(guard(long), 0.0)            # over the SKILL.md length budget

    def test_length_guard_holds_on_the_pairwise_path(self):
        art = self.tmp / "t.txt"
        art.write_text("A sentence that is long enough to matter here.", encoding="utf-8")
        guard = ai.build_length_guard(art.read_text(encoding="utf-8"), 0.5)

        def proposer(ctx):
            return {"proposal": {"diff_format": "text-replace",
                                 "find": "A sentence that is long enough to matter here.",
                                 "replace": "Short.", "change_summary": "cut"}, "usage": {}}
        res = ai.run_improvement_loop(art, "text", self.tmp / "wst", proposer=proposer,
                                      evaluator=_seq_evaluator([0.5, 0.9]), guard=guard,
                                      decider=lambda a, b: "keep",
                                      config=ai.LoopConfig(max_iterations=1, allow_deletions=True,
                                                           convergence_window=9))
        self.assertEqual(res["kept"], 0)
        self.assertIn("long enough", art.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# R15 — skill runs get a wall-clock budget by default
# ---------------------------------------------------------------------------
class TestR15SkillBudget(_Tmp):
    def test_skill_run_defaults_to_60_minutes(self):
        sk = self.tmp / "test-skill-broken"
        shutil.copytree(SKILL / "evals" / "fixtures" / "test-skill-broken", sk)

        class Avail:
            available = True
        store: dict = {}
        rc, _o, _e = _run_main(
            ["--artifact-path", str(sk), "--artifact-type", "skill",
             "--eval-set", str(sk / "evals" / "evals.json"), "--workspace", str(self.tmp / "ws")],
            get_backend=lambda *a: Avail(), detect_vendor=lambda *a: "claude",
            build_default_proposer=lambda *a, **k: _section_proposer(),
            run_improvement_loop=_capture_loop(store))
        self.assertEqual(rc, 0)
        self.assertEqual(store["config"].max_duration_s, 3600)
        report = (self.tmp / "ws" / "improvement_report.md").read_text(encoding="utf-8")
        self.assertIn("NOT counted", report)


# ---------------------------------------------------------------------------
# R16 — misconfiguration is a non-zero exit
# ---------------------------------------------------------------------------
class TestR16Preflight(_Tmp):
    def test_missing_key_exits_2_before_the_baseline(self):
        ds = self.tmp / "evals.json"
        shutil.copy(SKILL / "evals" / "fixtures" / "thin-dataset.json", ds)
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env["DEFAULT_PROVIDER"] = "anthropic"
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(llm_config, "anthropic", object()), \
                mock.patch.object(llm_config, "load_dotenv", lambda *a, **k: False), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = ai.main(["--artifact-path", str(ds), "--artifact-type", "dataset",
                          "--workspace", str(self.tmp / "ws")])
        self.assertEqual(rc, 2)
        self.assertIn("ANTHROPIC_API_KEY", err.getvalue())
        self.assertFalse((self.tmp / "ws").exists())

    def test_preflight_reports_a_missing_sdk(self):
        with mock.patch.object(llm_config, "openai", None), \
                mock.patch.object(llm_config, "load_dotenv", lambda *a, **k: False):
            self.assertIn("openai", llm_config.preflight_provider("openai"))

    def test_a_window_of_errors_is_exit_reason_errors(self):
        def proposer(ctx):
            raise RuntimeError("401 unauthorized")
        res = self.loop(proposer, _seq_evaluator([0.5]), cfg=dict(max_iterations=10))
        self.assertEqual(res["exit_reason"], "errors")
        res = self.loop(proposer, _seq_evaluator([0.5]), ws="ws2",
                        cfg=dict(max_iterations=2, convergence_window=3))
        self.assertEqual(res["exit_reason"], "errors")  # every iteration failed

    def test_cli_exit_code_is_1_on_errors(self):
        ds = self.tmp / "evals.json"
        shutil.copy(SKILL / "evals" / "fixtures" / "thin-dataset.json", ds)

        def failing_proposer_factory(*_a, **_k):
            def proposer(ctx):
                raise RuntimeError("401 unauthorized")
            return proposer
        rc, out, _e = _run_main(["--artifact-path", str(ds), "--artifact-type", "dataset",
                                 "--workspace", str(self.tmp / "ws")],
                                build_default_proposer=failing_proposer_factory)
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["summary"]["exit_reason"], "errors")

    def test_missing_eval_set_for_a_prompt_exits_2(self):
        rc, _o, err = _run_main(["--artifact-path", str(self.art), "--artifact-type", "prompt",
                                 "--workspace", str(self.tmp / "ws")])
        self.assertEqual(rc, 2)
        self.assertIn("--eval-set", err)


# ---------------------------------------------------------------------------
# R17 — full rejection memory for the Proposer
# ---------------------------------------------------------------------------
class TestR17RejectedIdeas(_Tmp):
    def test_a_repeated_rejected_summary_costs_no_evaluation(self):
        proposer = _section_proposer(summaries=["tighten rules", "Tighten   RULES", "other"])
        ev = _seq_evaluator([0.5, 0.4, 0.4])
        self.loop(proposer, ev, cfg=dict(max_iterations=3, convergence_window=9))
        self.assertEqual(_tsv_statuses(self.tmp / "ws"),
                         ["baseline", "revert", "duplicate", "revert"])
        self.assertEqual(ev.calls["n"], 3)           # baseline + iterations 1 and 3 only

    def test_a_repeated_rejected_edit_is_caught_whatever_its_summary(self):
        proposer = _section_proposer(summaries=["a", "b"], body=lambda i: "same edit")
        ev = _seq_evaluator([0.5, 0.4])
        self.loop(proposer, ev, cfg=dict(max_iterations=2, convergence_window=9))
        self.assertEqual(_tsv_statuses(self.tmp / "ws")[-1], "duplicate")

    def test_the_proposer_sees_every_rejected_idea(self):
        contexts = []
        inner = _section_proposer()

        def proposer(ctx):
            contexts.append(ctx)
            return inner(ctx)
        self.loop(proposer, _seq_evaluator([0.5] + [0.4] * 8),
                  cfg=dict(max_iterations=8, convergence_window=99))
        last = contexts[-1]
        self.assertEqual(len(last["history"]), 5)    # detailed: last five
        self.assertEqual(len(last["rejected"]), 7)   # compact: all seven rejections so far


if __name__ == "__main__":
    unittest.main()
