#!/usr/bin/env python3
"""The two skill gates must not drift apart.

`skill-creator/scripts/validate_skill.py` and
`skill-enhancer/scripts/analyze_gaps.py` are the repository's two gates over the
same `SKILL.md`. They duplicate several functions verbatim — deliberately, since
each skill must be installable and runnable in isolation, including as a packaged
`.skill` archive, so neither may import from the other.

Duplication without a gate is a fork with a delay. Both files have carried this
line since Task 064:

    tests/test_inline_efficiency.py asserts the two copies stay behaviourally
    identical.

That file exists in `agentic-development`, where these two skills are also
maintained, and it does check one function — `check_inline_efficiency` — for
behavioural agreement. It has never existed **in this repository**, so the
promise was unbacked here, and it covers one of the nine functions the two
files now share. This is that gate for both: byte-identity across all nine.

The second half is the property the duplication exists to protect: on any given
`SKILL.md` the two gates must not return contradictory verdicts. WI-033 was filed
because `validate_skill.py` exited 0 on `skills/pdf` while `analyze_gaps.py`
exited 1 on the same file.
"""

import ast
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VALIDATE = REPO / "skills/skill-creator/scripts/validate_skill.py"
ANALYZE = REPO / "skills/skill-enhancer/scripts/analyze_gaps.py"

# Every function the two files carry a copy of. A new shared helper belongs
# here the moment it is duplicated, or it is unguarded.
SHARED_FUNCTIONS = [
    "check_inline_efficiency",
    "mask_code",
    "collect_execution_policy_findings",
    "_normalize_section_title",
    "_collect_markdown_headings",
    "_has_section",
    "_has_real_files",
    "_section_body_lines",
    "check_validation_evidence_size",
]

# `extract_frontmatter` is NOT in that list and must not be: the two signatures
# diverged on purpose. analyze_gaps.py returns a fourth value, the body's line
# offset, because its findings name a line and validate_skill.py's do not.
DELIBERATELY_DIFFERENT = {"extract_frontmatter", "main"}


def _function_source(path, name):
    """The exact source segment of a top-level function, or None."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    source = path.read_text(encoding="utf-8")
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node)
    return None


def _top_level_functions(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}


class TestTheSharedCopiesAreIdentical(unittest.TestCase):
    def test_every_shared_function_exists_in_both_gates(self):
        in_validate = _top_level_functions(VALIDATE)
        in_analyze = _top_level_functions(ANALYZE)
        for name in SHARED_FUNCTIONS:
            with self.subTest(function=name):
                self.assertIn(name, in_validate, f"{name} is missing from validate_skill.py")
                self.assertIn(name, in_analyze, f"{name} is missing from analyze_gaps.py")

    def test_every_shared_function_is_byte_identical(self):
        for name in SHARED_FUNCTIONS:
            with self.subTest(function=name):
                a = _function_source(VALIDATE, name)
                b = _function_source(ANALYZE, name)
                self.assertIsNotNone(a)
                self.assertIsNotNone(b)
                self.assertEqual(
                    a, b,
                    f"the two copies of {name}() have drifted. The fix is to make "
                    f"them identical again, not to relax this test — a gate that "
                    f"differs between the two tools is how WI-033 started.")

    def test_the_inventory_is_not_quietly_incomplete(self):
        """A function duplicated but absent from SHARED_FUNCTIONS is unguarded."""
        shared = (_top_level_functions(VALIDATE) & _top_level_functions(ANALYZE))
        unlisted = shared - set(SHARED_FUNCTIONS) - DELIBERATELY_DIFFERENT
        self.assertEqual(
            sorted(unlisted), [],
            "these functions exist in both gates but are not covered: add them "
            "to SHARED_FUNCTIONS, or to DELIBERATELY_DIFFERENT with a reason.")

    def test_the_docstring_promise_now_names_a_file_that_exists(self):
        for path in (VALIDATE, ANALYZE):
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                for claimed in ("tests/test_inline_efficiency.py",
                                "tests/test_shared_gate_logic.py"):
                    if claimed in text:
                        target = REPO / claimed
                        self.assertTrue(
                            target.is_file(),
                            f"{path.name} claims {claimed} holds the copies "
                            f"together, but that file does not exist")


class TestTheTwoGatesDoNotContradictEachOther(unittest.TestCase):
    """WI-033's founding property, as a test."""

    def _skills(self):
        root = REPO / "skills"
        if not root.is_dir():
            self.skipTest("no skills/ in this checkout")
        return [d for d in sorted(root.iterdir()) if (d / "SKILL.md").is_file()]

    def _exit(self, script, skill, *args):
        return subprocess.run(
            [sys.executable, str(script), str(skill), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(REPO)).returncode

    def test_a_rule_in_both_gates_carries_the_same_severity(self):
        """The property WI-033 actually needed.

        Exit-code parity on every input is TOO STRONG: `analyze_gaps.py` owns
        prose rules (`[Language]`, `[Lazy]`, `[Richness]`) that the structural
        gate has no counterpart for, and those are its opinion rather than a
        contradiction. What must never happen is one rule, implemented in both,
        blocking in one and passing in the other — that is how `skills/pdf`
        came to fail one gate and pass the other.

        `required_sections` is the live example. Promoting it to an error here
        would have made the gate stricter than it had ever been: measured
        2026-09-02, 34 of 46 skills in `agentic-development` and 11 of 23 in
        `obsidian-llm-wiki` flipped from passing to failing. It is advisory in
        both instead.
        """
        no_sections = textwrap.dedent("""\
            ---
            name: nosectionskill
            description: Use when a skill carries no house-convention sections.
            tier: 2
            version: 1.0
            ---
            # nosectionskill

            A body with none of the house-convention headings.
            """)
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "nosectionskill"
            (skill / "examples").mkdir(parents=True)
            (skill / "examples" / "e.md").write_text(
                "# Example\n\nLong enough to clear the size floor.\n",
                encoding="utf-8")
            (skill / "SKILL.md").write_text(no_sections, encoding="utf-8")
            import json
            reports = {}
            for tool, blocking, advisory in ((ANALYZE, "gaps", "advisories"),
                                             (VALIDATE, "errors", "warnings")):
                out = subprocess.run(
                    [sys.executable, str(tool), str(skill), "--json"],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", cwd=str(REPO)).stdout
                reports[tool.name] = (json.loads(out), blocking, advisory)
        for name, (doc, blocking, advisory) in reports.items():
            with self.subTest(tool=name):
                self.assertFalse(
                    [x for x in doc[blocking] if "Red Flags" in x or "Rationalization" in x],
                    f"{name} blocks on a house-convention section")
                self.assertTrue(
                    [x for x in doc[advisory] if "Red Flags" in x],
                    f"{name} stopped reporting the missing section at all")

    def test_both_gates_return_the_same_verdict_on_every_skill(self):
        """Repo-local: true of THIS corpus, not a general property.

        It holds here because every skill in `skills/` clears both gates. In
        the sibling repositories `analyze_gaps.py` legitimately fails skills
        that `validate_skill.py` passes, on rules only it implements. The
        general property is the test above.
        """
        disagreements = []
        for skill in self._skills():
            analyze = self._exit(ANALYZE, skill)
            validate = self._exit(VALIDATE, skill)
            if analyze != validate:
                disagreements.append(
                    f"{skill.name}: analyze_gaps={analyze} validate_skill={validate}")
        self.assertEqual(
            disagreements, [],
            "the two gates disagree about these skills. Either the skill is "
            "wrong, or one gate has a rule the other lacks, or one ignores a "
            "config key the other honours — see WI-033:\n  "
            + "\n  ".join(disagreements))

    def test_a_skill_that_fails_one_gate_fails_the_other(self):
        """The property under a skill that is actually broken, not just the
        corpus that happens to be clean today.

        The fixture is an oversized fenced block, which both gates treat as an
        error. An earlier draft used a skill with no Red Flags — that stopped
        working the day `required_sections` became advisory in both, which is
        the right outcome for the rule and the wrong fixture for this test.
        """
        oversized = "\n".join(f"line {i}" for i in range(70))
        broken = textwrap.dedent("""\
            ---
            name: brokenskill
            description: Use when proving both gates reject the same file.
            tier: 2
            version: 1.0
            ---
            # brokenskill

            ## Red Flags
            - "x" -> **WRONG**.

            ## Rationalization Table
            | A | B |
            | :--- | :--- |
            | x | y |

            ## Notes
            ```python
            """) + oversized + "\n```\n"
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "brokenskill"
            (skill / "examples").mkdir(parents=True)
            (skill / "examples" / "e.md").write_text(
                "# Example\n\nLong enough to clear the size floor.\n",
                encoding="utf-8")
            (skill / "SKILL.md").write_text(broken, encoding="utf-8")
            analyze = self._exit(ANALYZE, skill)
            validate = self._exit(VALIDATE, skill)
        self.assertEqual(analyze, 1, "analyze_gaps.py accepted a skill with no Red Flags")
        self.assertEqual(validate, 1, "validate_skill.py accepted a skill with no Red Flags")

    def test_both_gates_expose_the_same_json_envelope_shape(self):
        """Two lists and a status, under each tool's own names."""
        skill = REPO / "skills" / "pdf"
        if not skill.is_dir():
            self.skipTest("skills/pdf is not in this checkout")
        import json
        for script, blocking, advisory in ((ANALYZE, "gaps", "advisories"),
                                           (VALIDATE, "errors", "warnings")):
            with self.subTest(tool=script.name):
                out = subprocess.run(
                    [sys.executable, str(script), str(skill), "--json"],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", cwd=str(REPO)).stdout
                doc = json.loads(out)
                self.assertEqual(sorted(doc), sorted(["skill", blocking, advisory, "status"]))
                self.assertIn(doc["status"], ("passed", "failed"))

    def test_both_gates_accept_strict(self):
        """A skill with advisories only: both gates pass, both --strict fail.

        The fixture is synthetic on purpose. An earlier draft pointed at
        `skills/hooks-creator` because it carried Execution Policy advisories —
        but WI-034 exists to close those, in that skill and the five others, and
        a test whose fixture is the repo's own remaining debt goes green by
        accident the day the debt is paid.
        """
        advisory_only = textwrap.dedent("""\
            ---
            name: advisoryskill
            description: Use when proving an advisory passes but blocks under --strict.
            tier: 2
            version: 1.0
            ---
            # advisoryskill

            ## Red Flags
            - "I'll skip it" -> **WRONG**. Read the rule.

            ## Rationalization Table
            | Agent Excuse | Reality |
            | :--- | :--- |
            | "Close enough" | It is not. |

            ## Instructions
            1. The helper script should be bundled next to the others.
            """)
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "advisoryskill"
            (skill / "examples").mkdir(parents=True)
            (skill / "examples" / "e.md").write_text(
                "# Example\n\nLong enough to clear the size floor.\n",
                encoding="utf-8")
            (skill / "SKILL.md").write_text(advisory_only, encoding="utf-8")
            plain_a = self._exit(ANALYZE, skill)
            plain_v = self._exit(VALIDATE, skill)
            strict_a = self._exit(ANALYZE, skill, "--strict")
            strict_v = self._exit(VALIDATE, skill, "--strict")
        self.assertEqual(plain_a, 0, "an advisory alone must not fail analyze_gaps")
        self.assertEqual(plain_v, 0, "a warning alone must not fail validate_skill")
        self.assertEqual(strict_a, 1, "--strict must promote the advisory")
        self.assertEqual(strict_v, 1, "--strict must promote the warning")

    def test_strict_is_per_tool_and_the_docs_say_so(self):
        """`--strict` promotes each tool's OWN advisory classes, and those differ.

        `analyze_gaps.py` carries prose rules (`[Language]`) that `validate_skill.py`
        has no counterpart for, so the two genuinely disagree under `--strict` —
        measured on 8 of this repo's 22 skills. Agreement is a property of the
        DEFAULT mode only (the test above this one). This test exists because
        `skill-creator/SKILL.md` once advertised `--strict` as "the spelling
        shared with analyze_gaps.py" directly under a sentence promising the two
        never return different verdicts; the claim and the behaviour must not
        drift apart again.
        """
        creator_doc = (REPO / "skills/skill-creator/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`--strict` is per-tool, and the two do NOT agree under it",
                      creator_doc,
                      "the per-tool caveat is gone from the Script Contract")
        disagreements = [s.name for s in self._skills()
                         if self._exit(ANALYZE, s, "--strict")
                         != self._exit(VALIDATE, s, "--strict")]
        self.assertTrue(
            disagreements,
            "the two gates now agree under --strict; if that is deliberate, "
            "delete the caveat from skill-creator/SKILL.md and this test")


if __name__ == "__main__":
    unittest.main(verbosity=2)
