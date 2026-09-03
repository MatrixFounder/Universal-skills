"""The intensity filter, and the two invariants a new pattern can silently break.

`filter_patterns_by_priority` keeps a `## ` section only when its `[A]`-`[D]`
tag is in the resolved set — with one exception: a section carrying NO tag
falls through to `include by default (safety)`. That branch admits an untagged
pattern at every intensity, including `minimal` for legal text, where a single
changed word changes what the document commits to.

Two properties keep the branch unused, and neither is visible by reading one
file:

1. every `## ` section in every pattern file carries a tag;
2. content that MUST survive every intensity — the whitelist — lives in the
   preamble ahead of the first `## `, where the filter keeps it
   unconditionally, rather than relying on the fallback.

The whitelist was first written as a `## ` section and passed every smoke test
by riding that fallback. These cases exist so the next one cannot.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import re
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
SKILL = SCRIPTS.parent
REFERENCES = SKILL / "references"

PATTERN_FILES = ("patterns_universal.md", "patterns_wiki.md",
                 "patterns_creative.md")
SECTION_SPLIT = re.compile(r"(?=^## )", re.M)
TAG = re.compile(r"`\[([A-D])\]`")


def _load(filename, name):
    loader = importlib.machinery.SourceFileLoader(name, str(SCRIPTS / filename))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


H = _load("humanizer.py", "text_humanizer_humanizer_filter")


def _read(rel):
    return (REFERENCES / rel).read_text(encoding="utf-8")


def _sections(text):
    return [s for s in SECTION_SPLIT.split(text) if s.startswith("## ")]


def _preamble(text):
    return SECTION_SPLIT.split(text)[0]


class TestEveryPatternIsTagged(unittest.TestCase):
    """The untagged-section fallback must stay unreachable in shipped files."""

    def test_no_section_is_untagged(self):
        for rel in PATTERN_FILES:
            for section in _sections(_read(rel)):
                head = section.split("\n", 1)[0]
                with self.subTest(file=rel, section=head):
                    self.assertRegex(
                        head, TAG,
                        f"{rel}: {head!r} carries no [A]-[D] tag, so "
                        f"filter_patterns_by_priority admits it at every "
                        f"intensity including minimal")

    def test_the_fallback_would_admit_an_untagged_section(self):
        """The branch is real. This is what it does when reached."""
        text = "preamble\n\n## 1. Tagged `[D]`\nbody\n\n## 2. Untagged\nbody\n"
        kept = H.filter_patterns_by_priority(text, {"A"})
        self.assertNotIn("Tagged", kept)
        self.assertIn("Untagged", kept)


class TestWhitelistSurvivesEveryIntensity(unittest.TestCase):
    """The whitelist is an exception list. An exception filtered out is a rule."""

    HEADING = "What is NOT a finding"

    def test_whitelist_is_in_the_preamble(self):
        self.assertIn(self.HEADING, _preamble(_read("patterns_universal.md")),
                      "the whitelist became its own `## ` section; it now "
                      "survives only through the untagged fallback")

    def test_whitelist_survives_at_every_priority_set(self):
        text = _read("patterns_universal.md")
        for name, allowed in H.INTENSITY_PRIORITIES.items():
            with self.subTest(intensity=name):
                self.assertIn(self.HEADING,
                              H.filter_patterns_by_priority(text, allowed))

    def test_whitelist_names_its_three_tests(self):
        preamble = _preamble(_read("patterns_universal.md"))
        for token in ("voice passport", "domain term", "Quoted material"):
            self.assertIn(token, preamble)


class TestIntensityReachesTheOutput(unittest.TestCase):
    """The throttle is the reason a technical rewrite is safe. Pin its contract.

    The contract is `kept == present & allowed`, not `kept == allowed`. The two
    look alike and the first draft of this class asserted the second, which
    fails on any file that simply carries no section of some class:
    `patterns_creative.md` holds no `[A]` and no `[D]` section at all. Stating
    it as an intersection makes the case independent of which classes a file
    happens to carry, so adding a `[D]` pattern tomorrow does not turn it red.
    """

    def _tag_sets(self, genre, rel):
        text = _read(rel)
        allowed = H.INTENSITY_PRIORITIES[H.INTENSITY_DEFAULTS[genre]]
        present = {TAG.search(s.split("\n", 1)[0]).group(1)
                   for s in _sections(text)}
        kept = {TAG.search(s.split("\n", 1)[0]).group(1)
                for s in _sections(H.filter_patterns_by_priority(text, allowed))}
        return present, kept, allowed

    def test_the_filter_keeps_exactly_the_allowed_intersection(self):
        for genre in sorted(H.GENRE_MAP):
            for rel in ("patterns_universal.md", H.GENRE_MAP[genre]):
                with self.subTest(genre=genre, file=rel):
                    present, kept, allowed = self._tag_sets(genre, rel)
                    self.assertEqual(kept, present & allowed)

    def test_technical_admits_nothing_but_critical(self):
        for rel in ("patterns_universal.md", H.GENRE_MAP["technical"]):
            with self.subTest(file=rel):
                _, kept, _ = self._tag_sets("technical", rel)
                self.assertLessEqual(kept, {"A"}, rel)

    def test_the_throttle_actually_removes_something(self):
        """A filter that drops nothing is indistinguishable from no filter."""
        present, kept, _ = self._tag_sets("technical", "patterns_universal.md")
        self.assertTrue(present - kept, "nothing was filtered at `low`")


class TestSensoryPatternIsScoped(unittest.TestCase):
    """R4 ships a rule that runs against common advice. Its guards are load-bearing."""

    HEADING = "Emotion Rendered Only as Sensation"

    def test_it_is_tagged_c(self):
        section = [s for s in _sections(_read("patterns_creative.md"))
                   if self.HEADING in s]
        self.assertEqual(len(section), 1, "the sensory pattern is missing")
        self.assertEqual(TAG.search(section[0].split("\n", 1)[0]).group(1), "C")

    def test_it_is_absent_below_high_intensity(self):
        text = _read("patterns_creative.md")
        for name in ("medium", "low", "minimal"):
            with self.subTest(intensity=name):
                self.assertNotIn(self.HEADING, H.filter_patterns_by_priority(
                    text, H.INTENSITY_PRIORITIES[name]))

    def test_it_is_present_at_high_and_max(self):
        text = _read("patterns_creative.md")
        for name in ("high", "max"):
            with self.subTest(intensity=name):
                self.assertIn(self.HEADING, H.filter_patterns_by_priority(
                    text, H.INTENSITY_PRIORITIES[name]))

    def test_the_food_style_states_the_exemption(self):
        food = _read("styles/food.md")
        self.assertIn("does **not** apply to this style", food)

    def test_the_pattern_names_the_food_exemption_too(self):
        """A reader of the pattern must see the exemption without opening the style."""
        creative = _read("patterns_creative.md")
        self.assertIn("**Food**", creative)


class TestModeStripping(unittest.TestCase):
    """Which template sections each mode emits.

    Counted as `^### <digit>` — the template's OWN numbered sections. The
    earlier metric counted every `^### ` line, which also counted headings
    inside the injected pattern files: adding one `###` heading to
    `patterns_universal.md` moved the documented 9/10/11 to 10/11/12 without
    touching the assembler. A metric that a content edit can move was measuring
    the wrong thing.
    """

    STRIPPED = {"prompt-gen": {"2", "9"}, "audit": {"9"}, "humanize": set()}
    NUMBERED = re.compile(r"^### (\d+)\.", re.M)

    def _numbers(self, mode):
        import subprocess
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "humanizer.py"),
             "--genre", "marketing", "--mode", mode],
            capture_output=True, text=True, check=True).stdout
        return set(self.NUMBERED.findall(out))

    def test_each_mode_strips_exactly_its_documented_sections(self):
        full = self._numbers("humanize")
        self.assertEqual(full, {str(n) for n in range(1, 10)})
        for mode, stripped in self.STRIPPED.items():
            with self.subTest(mode=mode):
                self.assertEqual(self._numbers(mode), full - stripped)

    def test_injected_content_cannot_move_the_count(self):
        """A heading inside a pattern file is not a template section."""
        out_headings = self._numbers("humanize")
        self.assertNotIn("0", out_headings)
        self.assertEqual(len(out_headings), 9)


class TestConditionalBlocks(unittest.TestCase):
    """R6 gates the outline pass by intensity. The gate is a real strip.

    A textual gate -- "run this only at max or high" -- would leave the pass in
    the emitted prompt for a technical rewrite and rely on the model obeying a
    condition stated 200 lines earlier. The block is removed instead.
    """

    def test_block_is_kept_for_a_listed_intensity(self):
        text = "a\n<!-- if-intensity: max, high -->\nBODY\n<!-- end-if -->\nb\n"
        self.assertIn("BODY", H.strip_conditional_blocks(text, "max"))
        self.assertIn("BODY", H.strip_conditional_blocks(text, "high"))

    def test_block_is_removed_for_an_unlisted_intensity(self):
        text = "a\n<!-- if-intensity: max, high -->\nBODY\n<!-- end-if -->\nb\n"
        for name in ("medium", "low", "minimal"):
            with self.subTest(intensity=name):
                out = H.strip_conditional_blocks(text, name)
                self.assertNotIn("BODY", out)
                self.assertEqual(out, "a\nb\n")

    def test_a_misspelled_intensity_raises_instead_of_dropping_silently(self):
        text = "<!-- if-intensity: hgih -->\nBODY\n<!-- end-if -->\n"
        with self.assertRaises(H.TemplateError):
            H.strip_conditional_blocks(text, "high")

    def test_every_shipped_block_names_known_intensities(self):
        template = (SKILL / "assets" / "generator_template.md").read_text(
            encoding="utf-8")
        blocks = H.CONDITIONAL_BLOCK.findall(template)
        self.assertTrue(blocks, "the template declares no conditional block")
        for names, _body in blocks:
            for name in (n.strip() for n in names.split(",")):
                with self.subTest(name=name):
                    self.assertIn(name, H.INTENSITY_PRIORITIES)

    def test_no_marker_survives_into_any_emitted_prompt(self):
        import subprocess
        for genre in sorted(H.GENRE_MAP):
            for mode in ("humanize", "audit", "prompt-gen"):
                with self.subTest(genre=genre, mode=mode):
                    out = subprocess.run(
                        [sys.executable, str(SCRIPTS / "humanizer.py"),
                         "--genre", genre, "--mode", mode],
                        capture_output=True, text=True, check=True).stdout
                    self.assertNotIn("if-intensity", out)
                    self.assertNotIn("end-if", out)


class TestVerificationPasses(unittest.TestCase):
    """R5 and R6 in the emitted prompt."""

    def _prompt(self, genre, mode="humanize"):
        import subprocess
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "humanizer.py"),
             "--genre", genre, "--mode", mode],
            capture_output=True, text=True, check=True).stdout

    def test_over_correction_reaches_every_genre(self):
        """It is a reporting rule, not a rewrite rule, so it is never gated."""
        for genre in sorted(H.GENRE_MAP):
            with self.subTest(genre=genre):
                self.assertIn("over-correction", self._prompt(genre))

    def test_pass_three_carries_its_ceiling(self):
        text = self._prompt("marketing")
        self.assertIn("Ceiling on Pass 3", text)
        self.assertIn("Two or three is the whole budget", text)

    def test_outline_pass_only_at_max_and_high(self):
        for genre in ("marketing", "social", "blog", "food", "crypto"):
            with self.subTest(genre=genre, expected="present"):
                self.assertIn("Pass 4", self._prompt(genre))
        for genre in ("corporate", "journalistic", "technical", "academic",
                      "encyclopedic", "science"):
            with self.subTest(genre=genre, expected="absent"):
                self.assertNotIn("Pass 4", self._prompt(genre))

    def test_verification_is_absent_from_the_non_rewriting_modes(self):
        for mode in ("audit", "prompt-gen"):
            with self.subTest(mode=mode):
                text = self._prompt("marketing", mode)
                self.assertNotIn("Pass 4", text)
                self.assertNotIn("Cardiogram", text)


class TestEvidenceClassesAreDeclared(unittest.TestCase):
    """R2. A file with no class is a file whose claims have no stated standing."""

    def test_every_reference_file_declares_one(self):
        files = list(REFERENCES.glob("*.md")) + list(
            (REFERENCES / "styles").glob("*.md"))
        self.assertGreater(len(files), 10)
        for path in files:
            with self.subTest(file=path.name):
                self.assertRegex(
                    path.read_text(encoding="utf-8"),
                    r"Evidence class: (measured|inference|heuristic)")


class TestEditOperationSkew(unittest.TestCase):
    """R7. The skew has to reach the prompt, and it has to reach it with its exemption."""

    ADDITIVE = ("Have an Opinion", "Use the First Person", "Let Some Mess In")
    MARKER = "**Conditional (additive):**"

    def test_the_strategy_states_the_skew(self):
        text = _read("rewriting_strategy.md")
        self.assertIn("Which Operation to Reach For", text)
        self.assertRegex(text, r"Prefer \*\*replacing\*\*.*\*\*deleting\*\*.*"
                               r"\*\*inserting\*\*")

    def test_specificity_is_exempted_from_the_skew(self):
        """Without the exemption the skew forbids the one edit that adds substance."""
        text = _read("rewriting_strategy.md")
        self.assertIn("adding specificity", text)
        self.assertIn("allowed to grow the text", text)
        self.assertIn("This is the one edit allowed to make the text longer",
                      _read("patterns_creative.md"))

    def test_the_skew_is_a_skew_and_not_a_ban(self):
        """The risk the spec names: flat AI text left flat. Red is the escape hatch."""
        text = _read("rewriting_strategy.md")
        self.assertIn("a skew, not a ban", text)
        self.assertIn("**Red**", text)

    def test_the_strategy_reaches_every_intensity(self):
        """It is injected whole, so `low` and `minimal` get the skew too.

        This is the half that matters for technical and legal text: those run
        at `A` only, where the additive rules are filtered out anyway and the
        skew is the only thing left saying "do not grow the text".
        """
        import subprocess
        for name in H.INTENSITY_PRIORITIES:
            with self.subTest(intensity=name):
                out = subprocess.run(
                    [sys.executable, str(SCRIPTS / "humanizer.py"),
                     "--genre", "technical", "--intensity", name],
                    capture_output=True, text=True, check=True).stdout
                self.assertIn("Which Operation to Reach For", out)

    def test_red_is_defined_before_the_rules_that_condition_on_it(self):
        """`prompt-gen` strips template section 2 -- the traffic-light legend.

        The four `Red` references left in the emitted prompt would then have no
        definition anywhere. The skew paragraph carries its own gloss ("three or
        more markers, the paragraph rewritten whole") and section 4 precedes
        section 5, so the reader meets the definition first. That ordering is
        the whole safety net, so it is pinned rather than assumed.
        """
        import subprocess
        for mode in ("humanize", "audit", "prompt-gen"):
            for genre in ("blog", "marketing", "food", "crypto", "corporate"):
                with self.subTest(mode=mode, genre=genre):
                    out = subprocess.run(
                        [sys.executable, str(SCRIPTS / "humanizer.py"),
                         "--genre", genre, "--mode", mode],
                        capture_output=True, text=True, check=True).stdout
                    first_use = out.find(self.MARKER)
                    if first_use < 0:
                        continue
                    gloss = out.find("three or more markers")
                    self.assertNotEqual(gloss, -1, "no gloss for Red anywhere")
                    self.assertLess(gloss, first_use,
                                    "a rule conditions on Red before Red is defined")

    def test_each_additive_rule_is_marked_conditional(self):
        sections = _sections(_read("patterns_creative.md"))
        for heading in self.ADDITIVE:
            with self.subTest(rule=heading):
                match = [s for s in sections if heading in s.split("\n", 1)[0]]
                self.assertEqual(len(match), 1, "rule renamed or removed")
                self.assertIn(self.MARKER, match[0])

    def test_the_conditional_travels_with_its_rule(self):
        """The marker is prose inside the section, so the tag filter must carry it."""
        text = _read("patterns_creative.md")
        kept = H.filter_patterns_by_priority(text, H.INTENSITY_PRIORITIES["max"])
        for heading in self.ADDITIVE:
            with self.subTest(rule=heading):
                self.assertIn(heading, kept)
        self.assertEqual(kept.count(self.MARKER), len(self.ADDITIVE))

    def test_subtractive_rules_are_not_marked(self):
        """Marking everything conditional would suspend the whole file."""
        sections = _sections(_read("patterns_creative.md"))
        for heading in ("Be Specific", "Vary Sentence Rhythm",
                        "Allow Hard Cuts", "Emotion Rendered Only as Sensation"):
            with self.subTest(rule=heading):
                match = [s for s in sections if heading in s.split("\n", 1)[0]]
                self.assertEqual(len(match), 1, "rule renamed or removed")
                self.assertNotIn(self.MARKER, match[0])


class TestScopeBoundaryIsDeclaredInBoth(unittest.TestCase):
    """R8. The body states the boundary; the description is what routing reads."""

    def test_the_body_states_it(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Scope boundary -- what this is NOT".replace("--", "—"),
                      text.replace("--", "—"))
        self.assertIn("Long-form fiction is out of scope", text)

    def test_the_description_excludes_fiction(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        description = re.search(r"^description: (.+)$", text, re.M).group(1)
        self.assertIn("non-fiction", description)
        self.assertIn("Not for prose fiction", description)
        self.assertNotIn("Creative", description)

    def test_the_frontmatter_survives_a_strict_yaml_parser(self):
        """The first R8 wording read `Not for prose fiction: a short story`.

        An unquoted `: ` inside a plain scalar makes the mapping ambiguous, and
        `validate_skill.py` rejected it -- the skill card renders as an error in
        Obsidian and VSCode. Caught by the house gate, pinned here because this
        suite is what edits the description.
        """
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML absent")
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        front = text.split("---", 2)[1]
        data = yaml.safe_load(front)
        self.assertIn("description", data)
        self.assertNotIn(": ", data["description"])

    def test_the_description_stays_inside_the_house_budget(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        description = re.search(r"^description: (.+)$", text, re.M).group(1)
        self.assertLessEqual(len(description.split()), 70,
                             "the 70-word standard; the tuning run breached it twice")


class TestModeStatesItsDeliverable(unittest.TestCase):
    """The template serves three modes and used to open, in ALL of them, with
    "You are an expert Prompt Engineer. Your goal is to generate a SYSTEM
    PROMPT" -- closing with "Output the final System Prompt".

    In `humanize`, whose deliverable is the rewritten text, that is an
    instruction to produce the wrong artefact. It usually loses to the user's
    actual text arriving after it. Under a high-pressure brief it does not: in
    the 2026-09-03 pressure campaign three of eighteen `with_skill` runs
    returned a system prompt, one of them keeping all 19 fact anchors because a
    generated prompt quotes the source inside itself.
    """

    def _prompt(self, mode, genre="technical"):
        import subprocess
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "humanizer.py"),
             "--genre", genre, "--mode", mode],
            capture_output=True, text=True, check=True).stdout

    def test_humanize_never_asks_for_a_system_prompt(self):
        for genre in sorted(H.GENRE_MAP):
            with self.subTest(genre=genre):
                text = self._prompt("humanize", genre)
                self.assertNotIn("expert Prompt Engineer", text)
                self.assertNotIn("Output the final System Prompt", text)
                self.assertIn("Your deliverable is that text, rewritten", text)
                self.assertIn("Output the rewritten text, and nothing else", text)

    def test_audit_asks_for_a_diagnosis_and_forbids_both_others(self):
        text = self._prompt("audit")
        self.assertNotIn("expert Prompt Engineer", text)
        self.assertNotIn("Output the final System Prompt", text)
        self.assertIn("traffic-light map", text)
        self.assertIn("Do not rewrite the text", text)

    def test_prompt_gen_still_asks_for_a_system_prompt(self):
        """The one mode where the original wording is correct keeps it."""
        text = self._prompt("prompt-gen")
        self.assertIn("expert Prompt Engineer", text)
        self.assertIn("Output the final System Prompt", text)

    def test_exactly_one_mode_block_survives_per_mode(self):
        """Two surviving openings would give the model two deliverables."""
        for mode in ("prompt-gen", "humanize", "audit"):
            with self.subTest(mode=mode):
                text = self._prompt(mode)
                self.assertNotIn("if-mode:", text, "a marker reached the output")
                self.assertNotIn("end-if", text)
                openings = sum(text.count(s) for s in (
                    "You are an expert Prompt Engineer",
                    "You are an expert editor. **The user's text follows",
                    "You are an expert editor performing a diagnosis"))
                self.assertEqual(openings, 1, f"{mode}: {openings} openings")


class TestModeBlockMechanism(unittest.TestCase):
    """The strip itself, exercised directly."""

    BLOCK = "a\n<!-- if-mode: humanize, audit -->\nBODY\n<!-- end-if -->\nb\n"

    def test_a_listed_mode_keeps_the_block(self):
        for mode in ("humanize", "audit"):
            self.assertIn("BODY", H.strip_mode_blocks(self.BLOCK, mode))

    def test_an_unlisted_mode_removes_it(self):
        self.assertNotIn("BODY", H.strip_mode_blocks(self.BLOCK, "prompt-gen"))

    def test_an_unknown_mode_name_raises(self):
        with self.assertRaises(H.TemplateError):
            H.strip_mode_blocks("<!-- if-mode: bogus -->\nX\n<!-- end-if -->\n",
                                "humanize")

    def test_every_mode_the_template_names_is_a_real_mode(self):
        import re as _re
        text = (SKILL / "assets" / "generator_template.md").read_text(encoding="utf-8")
        named = set()
        for group in _re.findall(r"<!-- if-mode: ([a-z, \-]+) -->", text):
            named.update(n.strip() for n in group.split(",") if n.strip())
        self.assertTrue(named, "the template declares no mode block")
        self.assertLessEqual(named, set(H.MODES), sorted(named - set(H.MODES)))

    def test_the_two_conditional_axes_do_not_consume_each_other(self):
        """An intensity block inside a mode block, and the reverse, both survive
        their own strip and are removed by the other."""
        text = ("<!-- if-mode: humanize -->\nOUTER\n"
                "<!-- if-intensity: max -->\nINNER\n<!-- end-if -->\n"
                "<!-- end-if -->\n")
        kept = H.strip_conditional_blocks(text, "max")
        self.assertIn("INNER", kept)
        self.assertIn("OUTER", H.strip_mode_blocks(kept, "humanize"))
        self.assertNotIn("OUTER", H.strip_mode_blocks(kept, "audit"))


if __name__ == "__main__":
    unittest.main()
