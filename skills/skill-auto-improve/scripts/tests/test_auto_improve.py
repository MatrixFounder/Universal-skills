#!/usr/bin/env python3
"""Offline unit tests for skill-auto-improve.

These need no API keys and no agentic CLI: deterministic utilities are tested
directly, and the orchestrator's decision logic is tested with injected fake
proposer/evaluator callables. Run:

    cd skills/skill-auto-improve/scripts
    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import auto_improve as ai  # noqa: E402
import apply_proposal as ap  # noqa: E402
import check_immutability as ci  # noqa: E402
import common as c  # noqa: E402
import detect_artifact_type as dt  # noqa: E402
import grade_dataset as gd  # noqa: E402
import measure_change_size as mc  # noqa: E402
import snapshot as snap  # noqa: E402
import log_iteration as li  # noqa: E402

SKILL_MD = (
    "---\nname: x\ndescription: old desc\ntier: 2\nversion: 1.0\n---\n"
    "# X\n\n## Instructions\nold\n\n## Red Flags\n- a\n"
)


def _mk_skill(tmp: Path) -> Path:
    sk = tmp / "sk"
    sk.mkdir()
    (sk / "SKILL.md").write_text(SKILL_MD)
    return sk


class TestCommon(unittest.TestCase):
    def test_sections_and_replace(self):
        secs = c.find_sections(SKILL_MD)
        self.assertEqual([s["title"] for s in secs], ["Instructions", "Red Flags"])
        body = c.split_frontmatter(SKILL_MD)[1]
        out = c.replace_section(body, "## Instructions", "## Instructions\nNEW\n")
        self.assertIn("NEW", out)
        self.assertIn("Red Flags", out)
        self.assertNotIn("old", out)

    def test_replace_section_not_found(self):
        body = c.split_frontmatter(SKILL_MD)[1]
        with self.assertRaises(KeyError):
            c.replace_section(body, "## Nonexistent", "## Nonexistent\n")

    def test_frontmatter_parse_and_set(self):
        fm = c.parse_frontmatter(SKILL_MD)
        self.assertEqual(fm["name"], "x")
        self.assertEqual(fm["tier"], "2")
        out = c.set_frontmatter_field(SKILL_MD, "description", "brand new")
        self.assertEqual(c.parse_frontmatter(out)["description"], "brand new")
        self.assertEqual(c.parse_frontmatter(out)["name"], "x")  # untouched

    def test_set_frontmatter_missing_field(self):
        with self.assertRaises(ValueError):
            c.set_frontmatter_field(SKILL_MD, "nonexistent", "v")

    def test_frontmatter_quote_roundtrip(self):
        # set->parse must round-trip embedded quotes and backslashes (issue #9).
        for val in ['has "quotes" inside', "back\\slash", 'mix \\ and "q"']:
            out = c.set_frontmatter_field(SKILL_MD, "description", val)
            self.assertEqual(c.parse_frontmatter(out)["description"], val)

    def test_resolve_dataset_items_cases_key(self):
        items, key = c.resolve_dataset_items({"cases": [{"id": "a"}]})
        self.assertEqual(key, "cases")
        self.assertEqual(len(items), 1)
        items, key = c.resolve_dataset_items({"nothing": 1})
        self.assertEqual((items, key), ([], None))


class TestMeasureTier(unittest.TestCase):
    def test_tiers(self):
        small = {"diff_format": "section-replace", "target_section": "## I", "new_content": "## I\nx\n"}
        self.assertEqual(mc.measure_tier(small), "trivial")
        medium = {"diff_format": "section-replace", "target_section": "## I", "new_content": "## I\n" + "x\n" * 25}
        self.assertEqual(mc.measure_tier(medium), "medium")
        # large single-section rewrite (>=50 lines)
        large = {"diff_format": "section-replace", "target_section": "## I", "new_content": "## I\n" + "x\n" * 60}
        self.assertEqual(mc.measure_tier(large), "large")
        # large via >=2 dataset ops
        ds_large = {"diff_format": "dataset-op", "dataset_ops": [{"op": "add"}, {"op": "add"}]}
        self.assertEqual(mc.measure_tier(ds_large), "large")
        # frontmatter-field is always trivial
        self.assertEqual(mc.measure_tier({"diff_format": "frontmatter-field", "field": "description", "value": "x"}), "trivial")

    def test_tier_counts_deletions(self):
        # Replacing a 60-line section with 2 lines is LARGE (big deletion).
        prop = {"diff_format": "section-replace", "target_section": "## I", "new_content": "## I\nshort\n"}
        self.assertEqual(mc.measure_tier(prop, old_section_lines=60), "large")


class TestImmutability(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sk = _mk_skill(self.tmp)

    def test_validate_section_replace_ok_and_rename_rejected(self):
        ok, _ = ci.validate_proposal(self.sk, "skill", {
            "diff_format": "section-replace", "target_section": "## Instructions",
            "new_content": "## Instructions\nnew\n"})
        self.assertTrue(ok)
        ok, _ = ci.validate_proposal(self.sk, "skill", {
            "diff_format": "section-replace", "target_section": "## Instructions",
            "new_content": "## Renamed\nx\n"})
        self.assertFalse(ok)

    def test_frontmatter_field_name_rejected_description_ok(self):
        ok, _ = ci.validate_proposal(self.sk, "skill", {
            "diff_format": "frontmatter-field", "field": "description", "value": "v"})
        self.assertTrue(ok)
        ok, _ = ci.validate_proposal(self.sk, "skill", {
            "diff_format": "frontmatter-field", "field": "name", "value": "evil"})
        self.assertFalse(ok)

    def test_subset_semantics_allow_additions_block_changes(self):
        self.assertTrue(ci.immutable_preserved({"a"}, {"a", "b"}))
        self.assertFalse(ci.immutable_preserved({"a"}, {"b"}))

    def test_dataset_immutable_field_modify_rejected(self):
        ev = self.tmp / "evals.json"
        ev.write_text(json.dumps([{"id": "a", "query": "q", "should_trigger": True}]))
        for bad_fields in ({"id": "z"}, {"grader": "x"}, {"files": ["y"]}, {"file": "z"}):
            ok, _ = ci.validate_proposal(ev, "dataset", {
                "diff_format": "dataset-op",
                "dataset_ops": [{"op": "modify", "id": "a", "fields": bad_fields}]})
            self.assertFalse(ok, bad_fields)
        ok, _ = ci.validate_proposal(ev, "dataset", {
            "diff_format": "dataset-op", "dataset_ops": [{"op": "remove", "id": "a"}]})
        self.assertFalse(ok)

    def test_unified_diff_rejected(self):
        ok, why = ci.validate_proposal(self.sk, "skill", {
            "diff_format": "unified-diff", "unified_diff": "--- a\n+++ b\n+x\n"})
        self.assertFalse(ok)
        self.assertIn("not allowed", why)

    def test_evals_dir_is_fingerprinted(self):
        # The evals/ harness is part of the skill signature (issue #1).
        evals = self.sk / "evals"
        evals.mkdir()
        (evals / "evals.json").write_text('[{"query":"q","should_trigger":true}]')
        before = ci.immutable_signatures(self.sk, "skill")
        self.assertTrue(any(s.startswith("eval:") for s in before))
        # Tampering with the harness breaks the subset check → violation.
        (evals / "evals.json").write_text('[{"query":"rigged","should_trigger":true}]')
        after = ci.immutable_signatures(self.sk, "skill")
        self.assertFalse(ci.immutable_preserved(before, after))


class TestApply(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sk = _mk_skill(self.tmp)

    def test_section_replace_preserves_frontmatter(self):
        ap.apply_proposal(self.sk, "skill", {
            "diff_format": "section-replace", "target_section": "## Instructions",
            "new_content": "## Instructions\nNEW1\n"})
        txt = (self.sk / "SKILL.md").read_text()
        self.assertIn("NEW1", txt)
        self.assertIn("name: x", txt)
        self.assertNotIn("\nold\n", txt)

    def test_frontmatter_field_apply(self):
        ap.apply_proposal(self.sk, "skill", {
            "diff_format": "frontmatter-field", "field": "description", "value": "much better"})
        self.assertEqual(c.parse_skill_md(self.sk)[1], "much better")

    def test_dataset_add(self):
        ev = self.tmp / "evals.json"
        ev.write_text(json.dumps([{"id": "a", "query": "q", "should_trigger": True}]))
        ap.apply_proposal(ev, "dataset", {
            "diff_format": "dataset-op",
            "dataset_ops": [{"op": "add", "item": {"id": "b", "query": "z", "should_trigger": False}}]})
        data = json.loads(ev.read_text())
        self.assertEqual(len(data), 2)

    def test_dataset_add_cases_wrapper_not_lost(self):
        # Regression for issue #2: add to a 'cases'-keyed dict must persist.
        ev = self.tmp / "ds.json"
        ev.write_text(json.dumps({"cases": [{"id": "a", "query": "q"}]}))
        ap.apply_proposal(ev, "dataset", {
            "diff_format": "dataset-op",
            "dataset_ops": [{"op": "add", "item": {"id": "b", "query": "z"}}]})
        self.assertEqual(len(json.loads(ev.read_text())["cases"]), 2)

    def test_dataset_add_empty_dict_creates_evals(self):
        ev = self.tmp / "empty.json"
        ev.write_text(json.dumps({}))
        ap.apply_proposal(ev, "dataset", {
            "diff_format": "dataset-op",
            "dataset_ops": [{"op": "add", "item": {"id": "a", "query": "q"}}]})
        self.assertEqual(len(json.loads(ev.read_text())["evals"]), 1)


class TestGradeDataset(unittest.TestCase):
    def test_score_range_and_negatives(self):
        tmp = Path(tempfile.mkdtemp())
        f = tmp / "d.json"
        f.write_text(json.dumps([
            {"id": "a", "query": "alpha beta", "should_trigger": True},
            {"id": "b", "query": "gamma delta", "should_trigger": False},
        ]))
        res = gd.score_dataset(f)
        self.assertTrue(0 <= res["score"] <= 1)
        self.assertEqual(res["components"]["forbidden"], 1.0)  # has pos + neg

    def test_empty(self):
        tmp = Path(tempfile.mkdtemp())
        f = tmp / "d.json"
        f.write_text("[]")
        self.assertEqual(gd.score_dataset(f)["score"], 0.0)


class TestSnapshot(unittest.TestCase):
    def test_save_restore_dir(self):
        tmp = Path(tempfile.mkdtemp())
        sk = _mk_skill(tmp)
        ws = tmp / "ws"
        ref = snap.save_snapshot(sk, ws, 1)
        (sk / "SKILL.md").write_text("corrupted")
        snap.restore_snapshot(sk, ref)
        self.assertIn("name: x", (sk / "SKILL.md").read_text())


class TestLogIteration(unittest.TestCase):
    def test_header_and_rows(self):
        ws = Path(tempfile.mkdtemp())
        li.log_iteration(ws, iteration=0, score=0.5, delta=None, status="baseline")
        li.log_iteration(ws, iteration=1, score=0.7, delta=0.2, status="keep", tier="trivial",
                         change_summary="x")
        text = (ws / "improvement_history.tsv").read_text()
        self.assertIn("iter\tscore\tdelta\tstatus", text)
        self.assertIn("+0.200\tkeep", text)
        self.assertIn("—\tbaseline", text)


class TestDetect(unittest.TestCase):
    def test_skill_and_dataset(self):
        tmp = Path(tempfile.mkdtemp())
        sk = _mk_skill(tmp)
        self.assertEqual(dt.detect_type(sk), "skill")
        self.assertEqual(dt.detect_type(sk, full=True), "full-skill")
        ev = tmp / "evals.json"
        ev.write_text(json.dumps([{"query": "q", "should_trigger": True}]))
        self.assertEqual(dt.detect_type(ev), "dataset")


def _fake_proposer(items):
    it = iter(items)

    def proposer(ctx):
        try:
            item = next(it)
        except StopIteration:
            return {"proposal": None, "usage": {}}
        return {"proposal": {
            "diff_format": "section-replace", "target_section": "## Instructions",
            "new_content": f"## Instructions\n{item}\n", "change_summary": item},
            "usage": {"total_tokens": 10}}
    return proposer


def _fake_evaluator(scores):
    it = iter(scores)

    def evaluator(path):
        return {"score": next(it), "secondary": None, "usage": {}}
    return evaluator


class TestOrchestratorLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sk = _mk_skill(self.tmp)

    def _run(self, scores, items=None, **cfg):
        items = items or [f"v{i}" for i in range(len(scores))]
        ws = self.tmp / f"ws{len(list(self.tmp.glob('ws*')))}"
        return ai.run_improvement_loop(
            self.sk, "skill", ws,
            proposer=_fake_proposer(items), evaluator=_fake_evaluator(scores),
            config=ai.LoopConfig(**cfg)), ws

    def test_keep_until_optimal(self):
        res, _ = self._run([0.5, 0.7, 1.0], max_iterations=10, noise_sigma=0.0)
        self.assertEqual(res["exit_reason"], "optimal")
        self.assertEqual(res["best_score"], 1.0)
        self.assertEqual(res["kept"], 2)

    def test_revert_on_regression_keeps_baseline(self):
        res, _ = self._run([0.6, 0.5, 0.4, 0.45], max_iterations=10, noise_sigma=0.0,
                           convergence_window=3)
        self.assertEqual(res["best_score"], 0.6)
        self.assertEqual(res["kept"], 0)
        self.assertEqual(res["exit_reason"], "stagnation")

    def test_already_optimal_short_circuit(self):
        res, ws = self._run([1.0], max_iterations=5)
        self.assertEqual(res["exit_reason"], "already_optimal")
        self.assertEqual(len(res["iterations"]), 1)

    def test_no_signal_reverts(self):
        # baseline + 3 within-sigma iterations → 3 no-signal reverts → stagnation
        res, ws = self._run([0.60, 0.61, 0.59, 0.605], max_iterations=10, noise_sigma=0.05,
                            convergence_window=3)
        self.assertEqual(res["kept"], 0)
        self.assertEqual(res["best_score"], 0.60)
        self.assertIn("no-signal", (ws / "improvement_history.tsv").read_text())

    def test_budget_iterations(self):
        res, _ = self._run([0.1, 0.11, 0.12, 0.13], max_iterations=2, noise_sigma=0.0,
                           convergence_window=99)
        self.assertEqual(res["exit_reason"], "budget_iterations")

    def test_keep_epsilon_rejects_float_noise(self):
        # A delta below the keep-epsilon (sigma=0) must NOT KEEP (issue #3).
        res, _ = self._run([0.5, 0.5 + 1e-12], max_iterations=1, noise_sigma=0.0,
                           convergence_window=99)
        self.assertEqual(res["kept"], 0)
        self.assertEqual(res["best_score"], 0.5)

    def test_apply_error_triggers_stagnation(self):
        # Proposer keeps emitting a valid-but-unapplyable proposal (missing
        # section) → apply raises every time → must stagnate, not loop forever.
        def bad_apply_proposer(ctx):
            return {"proposal": {"diff_format": "section-replace",
                                 "target_section": "## Ghost",
                                 "new_content": "## Ghost\nx\n", "change_summary": "ghost"},
                    "usage": {}}
        ws = self.tmp / "wsapply"
        res = ai.run_improvement_loop(
            self.sk, "skill", ws, proposer=bad_apply_proposer,
            evaluator=_fake_evaluator([0.5] + [0.9] * 10),
            config=ai.LoopConfig(max_iterations=20, convergence_window=3))
        self.assertEqual(res["exit_reason"], "stagnation")
        self.assertIn("\nold\n", (self.sk / "SKILL.md").read_text())

    def test_rejected_iterations_appear_in_summary(self):
        # Issue #19: rejected iterations must be recorded, not silently dropped.
        def empty_proposer(ctx):
            return {"proposal": None, "usage": {}}
        ws = self.tmp / "wsrej"
        res = ai.run_improvement_loop(
            self.sk, "skill", ws, proposer=empty_proposer,
            evaluator=_fake_evaluator([0.5]),
            config=ai.LoopConfig(max_iterations=10, convergence_window=2))
        statuses = [i["status"] for i in res["iterations"]]
        self.assertIn("no-change", statuses)
        self.assertEqual(res["exit_reason"], "stagnation")

    def test_immutability_rejection_does_not_apply(self):
        # Proposer tries to rename a section (rejected pre-apply).
        def bad_proposer(ctx):
            return {"proposal": {"diff_format": "section-replace", "target_section": "## Instructions",
                                 "new_content": "## Renamed\nx\n", "change_summary": "rename"},
                    "usage": {}}
        ws = self.tmp / "wsimm"
        res = ai.run_improvement_loop(
            self.sk, "skill", ws, proposer=bad_proposer,
            evaluator=_fake_evaluator([0.5, 0.9, 0.9, 0.9]),
            config=ai.LoopConfig(max_iterations=5, convergence_window=3))
        # Never applied → artifact unchanged, best stays baseline.
        self.assertIn("\nold\n", (self.sk / "SKILL.md").read_text())
        self.assertEqual(res["kept"], 0)
        self.assertIn("immutability-violation", (ws / "improvement_history.tsv").read_text())


if __name__ == "__main__":
    unittest.main()
