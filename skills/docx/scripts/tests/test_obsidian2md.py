"""Tests for Obsidian-note support (TASK 030, RTM R1-R17).

Two layers, deliberately separated:

* `.md -> .md` through `obsidian2md.js` — text in, text out, no OOXML. Every rule of
  R2-R10 and R13-R15 is asserted here, because a failure points at one regex rather than
  at "the document looks wrong".
* `.md -> .docx` through `md2docx.js --obsidian` — the acceptance criteria that can only
  be answered by unzipping the package (A1, A2, A3, A8, A13).

The fixture vault is `examples/fixture-obsidian-vault/` and is committed, so these tests
do not depend on the author's machine. TASK 030 criterion **A11** (the real vault note)
is a MANUAL gate and is NOT wired here: that note lives outside the repository.

Run::  cd skills/docx && ./.venv/bin/python -m unittest tests.test_obsidian2md -v
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tests/ -> scripts/
SKILL = os.path.dirname(SCRIPTS)
OBSIDIAN2MD = os.path.join(SCRIPTS, "obsidian2md.js")
MD2DOCX = os.path.join(SCRIPTS, "md2docx.js")
VALIDATE = os.path.join(SCRIPTS, "office", "validate.py")
VAULT = os.path.join(SKILL, "examples", "fixture-obsidian-vault")
NOTE = os.path.join(VAULT, "note.md")
PLAIN = os.path.join(VAULT, "plain-commonmark.md")


def _have_node():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


HAVE_NODE = _have_node()


def run_convert(src, dst, *flags):
    """Run obsidian2md.js; return the CompletedProcess (never raises on non-zero)."""
    return subprocess.run(
        ["node", OBSIDIAN2MD, src, dst, *flags],
        capture_output=True, text=True)


def convert_text(text, *flags, name="note.md", vault=VAULT):
    """Convert an inline note placed inside the fixture vault; return its Markdown.

    Written into the vault (not into a bare tmpdir) so attachment resolution and
    `.obsidian/app.json` behave exactly as they do for a real note.
    """
    tmp = tempfile.mkdtemp(dir=vault, prefix=".t-")
    try:
        src = os.path.join(tmp, name)
        dst = os.path.join(tmp, "out.md")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(text)
        proc = run_convert(src, dst, "--vault-root", vault, *flags)
        if proc.returncode != 0:
            raise AssertionError(
                "obsidian2md.js exited %d: %s" % (proc.returncode, proc.stderr))
        with open(dst, encoding="utf-8") as fh:
            return fh.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestFrontmatter(unittest.TestCase):
    """R2 — frontmatter becomes a table by default (the user's explicit override)."""

    FM = (
        "---\n"
        "lang: en\n"
        "type: meeting-summary\n"
        "participants:\n"
        "  - Ada Lovelace\n"
        "  - Alan Turing\n"
        "tags:\n"
        "  - one\n"
        "  - two\n"
        "published: 2026-08-13\n"
        "tldr: \"suppressed\"\n"
        "---\n\n# Title\n\nBody.\n"
    )

    def test_default_mode_is_table(self):
        # R2 — the default, and the whole point of the user's requirement.
        out = convert_text(self.FM)
        self.assertIn("| Field | Value |", out)
        self.assertIn("|---|---|", out)

    def test_table_is_gfm_so_md2docx_styles_it(self):
        # R2(a) — a GFM table is what makes md2docx.js's existing `table` token path
        # render it; a hand-built docx table would not inherit the shared styling.
        out = convert_text(self.FM)
        rows = [ln for ln in out.splitlines() if ln.startswith("| ")]
        self.assertGreaterEqual(len(rows), 3)
        for row in rows:
            self.assertTrue(row.endswith("|"), row)

    def test_multivalue_uses_br_not_comma(self):
        # R2(g) — one value per line inside the cell.
        out = convert_text(self.FM)
        self.assertIn("Ada Lovelace<br>Alan Turing", out)

    def test_suppressed_keys_absent(self):
        # R2(f) — machine keys and the body-duplicating tldr never render.
        out = convert_text(self.FM)
        self.assertNotIn("suppressed", out)
        self.assertNotIn("meeting-summary", out)

    def test_table_lands_after_h1(self):
        # R2(a).
        out = convert_text(self.FM)
        self.assertLess(out.index("# Title"), out.index("| Field | Value |"))

    def test_table_lands_after_the_source_blockquote(self):
        # R2(a) — an Obsidian template puts a provenance blockquote under the H1; the
        # table must not split it.
        text = self.FM.replace("Body.", "Body.").replace(
            "# Title\n\nBody.", "# Title\n\n> **Source:** somewhere\n\nBody.")
        out = convert_text(text)
        self.assertLess(out.index("> **Source:**"), out.index("| Field | Value |"))

    def test_no_h1_puts_table_on_top(self):
        # R2(j).
        out = convert_text("---\nlang: en\ntags:\n  - x\n---\n\nJust a paragraph.\n")
        self.assertTrue(out.lstrip().startswith("| Field | Value |"), out[:80])

    def test_no_displayed_key_emits_nothing(self):
        # R2(i) — an empty header row would be worse than no table.
        out = convert_text("---\nlang: en\ntype: note\nslug: x\n---\n\n# T\n\nBody.\n")
        self.assertNotIn("| Field | Value |", out)
        self.assertNotIn("|---|---|", out)

    def test_no_frontmatter_at_all_emits_nothing(self):
        # R2(i).
        out = convert_text("# T\n\nBody.\n")
        self.assertNotIn("| Field | Value |", out)

    def test_pipe_in_value_is_escaped(self):
        # R2(h) — an unescaped pipe would end the column and corrupt the table.
        out = convert_text('---\nlang: en\nauthor: "A | B"\n---\n\n# T\n')
        self.assertIn(r"A \| B", out)

    def test_render_mode_is_prose(self):
        # R2(b).
        out = convert_text(self.FM, "--frontmatter", "render")
        self.assertNotIn("| Field | Value |", out)
        self.assertIn("**Participants:**", out)

    def test_strip_mode_emits_nothing(self):
        # R2(c) — the pre-TASK-030 behaviour, still selectable.
        out = convert_text(self.FM, "--frontmatter", "strip")
        self.assertNotIn("Ada Lovelace", out)
        self.assertNotIn("| Field | Value |", out)

    def test_invalid_mode_is_a_usage_error(self):
        # R15(c).
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n")
            proc = run_convert(src, os.path.join(tmp, "o.md"),
                               "--frontmatter", "bogus")
        self.assertEqual(proc.returncode, 2)


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestLocalisation(unittest.TestCase):
    """R13 — every user-visible string comes from MESSAGES."""

    def test_auto_reads_lang_from_frontmatter(self):
        # R13(a).
        out = convert_text("---\nlang: ru\ntags:\n  - x\n---\n\n# T\n")
        self.assertIn("| Поле | Значение |", out)

    def test_auto_falls_back_to_english(self):
        # R13(a) — no `lang:` key at all.
        out = convert_text("---\ntags:\n  - x\n---\n\n# T\n")
        self.assertIn("| Field | Value |", out)

    def test_explicit_lang_overrides_frontmatter(self):
        # R13(b).
        out = convert_text("---\nlang: ru\ntags:\n  - x\n---\n\n# T\n", "--lang", "en")
        self.assertIn("| Field | Value |", out)

    def test_ru_and_en_differ_only_in_messages(self):
        # A15 — the structure is identical, only the dictionary strings change.
        body = "---\ntags:\n  - x\n---\n\n# T\n\n![[missing.png]]\n"
        ru = convert_text(body, "--lang", "ru")
        en = convert_text(body, "--lang", "en")
        self.assertIn("изображение не найдено", ru)
        self.assertIn("image not found", en)
        self.assertEqual(len(ru.splitlines()), len(en.splitlines()))


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestEmbeds(unittest.TestCase):
    """R3 — ![[embed]] becomes a real image (closes D2)."""

    def test_image_embed_becomes_an_image_token(self):
        # R3(a).
        out = convert_text("# T\n\n![[diagram.png]]\n")
        self.assertRegex(out, r"!\[diagram\]\(<.*diagram\.png>\)")

    def test_width_hint_rides_the_alt_prefix(self):
        # R3(b), R3(g).
        out = convert_text("# T\n\n![[diagram.png|120]]\n")
        self.assertIn("![w=120|diagram](", out)

    def test_width_and_height_hint(self):
        # R3(c).
        out = convert_text("# T\n\n![[photo.jpg|100x50]]\n")
        self.assertIn("![w=100x50|photo](", out)

    def test_non_numeric_hint_is_not_a_size(self):
        # R3(g) — `![[x.png|caption]]` must not become `w=caption|`.
        out = convert_text("# T\n\n![[diagram.png|some caption]]\n")
        self.assertNotIn("w=some", out)
        self.assertIn("![diagram](", out)

    def test_pdf_embed_is_a_reference_line(self):
        # R3(d) — a PDF cannot be embedded as an image.
        out = convert_text("# T\n\n![[report.pdf]]\n")
        self.assertIn("*File: report.pdf*", out)
        self.assertNotIn("![", out)

    def test_pdf_page_anchor_is_stripped(self):
        # R3(d).
        out = convert_text("# T\n\n![[report.pdf#page=3]]\n")
        self.assertIn("*File: report.pdf*", out)

    def test_audio_and_video_are_reference_lines(self):
        # R3(d).
        out = convert_text("# T\n\n![[a.mp3]]\n\n![[b.mp4]]\n")
        self.assertIn("*File: a.mp3*", out)
        self.assertIn("*File: b.mp4*", out)

    def test_note_embed_is_a_pointer_by_default(self):
        # R3(e) — transclusion is opt-in.
        out = convert_text("# T\n\n![[linked note]]\n")
        self.assertIn("See note", out)

    def test_every_image_extension_is_recognised(self):
        # R3(f). Asserting on a NONEXISTENT file only proved the extension reached the
        # image branch — it could not tell an embeddable format from one that throws at
        # build time. `webp` did exactly that: in IMAGE_EXTENSIONS here, absent from
        # md2docx.js's detectImageType(). Assert against the shipped set instead.
        for ext in ("png", "jpg", "jpeg", "gif", "bmp", "svg"):
            out = convert_text("# T\n\n![[nothing-here.%s]]\n" % ext)
            self.assertIn("image not found", out, ext)

    def test_image_extensions_match_md2docx_detect_image_type(self):
        # R3(f) regression lock — the two lists must stay in step. An extension here but
        # not there resolves to a real path and then throws `Unsupported image format`.
        lib = os.path.join(SCRIPTS, "_obsidian_lib.js")
        with open(lib, encoding="utf-8") as fh:
            declared = re.search(r"IMAGE_EXTENSIONS = new Set\(\[([^\]]*)\]", fh.read())
        exts = set(re.findall(r"'([a-z]+)'", declared.group(1)))
        with open(MD2DOCX, encoding="utf-8") as fh:
            body = fh.read()
        detect = body[body.index("function detectImageType"):]
        detect = detect[:detect.index("\n}")]
        supported = set(re.findall(r"ext === '\.([a-z]+)'", detect))
        self.assertEqual(exts - supported, set(),
                         "extensions resolvable here but unrenderable by md2docx.js")

    def test_webp_is_a_file_reference_not_a_broken_image(self):
        # R3(d)/(f) — the docx image layer has no webp, so naming the file beats crashing.
        out = convert_text("# T\n\n![[picture.webp]]\n")
        self.assertIn("*File: picture.webp*", out)
        self.assertNotIn("![", out)


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestLinks(unittest.TestCase):
    """R4 — [[wikilink]] becomes text (closes D3)."""

    def test_labelled_link_keeps_the_label(self):
        # R4(a).
        self.assertIn("A label", convert_text("# T\n\n[[target|A label]]\n"))

    def test_bare_link_keeps_the_last_segment(self):
        # R4(b).
        out = convert_text("# T\n\n[[folder/sub/target]]\n")
        self.assertIn("target", out)
        self.assertNotIn("folder/sub", out)

    def test_heading_anchor_becomes_an_arrow(self):
        # R4(c).
        self.assertIn("target → Section", convert_text("# T\n\n[[target#Section]]\n"))

    def test_block_anchor_is_dropped(self):
        # R4(d) — a block id means nothing outside the vault.
        out = convert_text("# T\n\n[[target#^abc123]]\n")
        self.assertIn("target", out)
        self.assertNotIn("abc123", out)

    def test_embedded_pipes_stay_in_the_label(self):
        # R4(e) — split on the FIRST pipe only; `split('|')[1]` would yield just `b`.
        out = convert_text("# T\n\n[[a|b|c]]\n")
        self.assertIn("b|c", out)

    def test_italic_mode(self):
        # R4(f).
        out = convert_text("# T\n\n[[target|Label]]\n", "--links", "italic")
        self.assertIn("*Label*", out)

    def test_no_literal_wikilink_survives_outside_code(self):
        # A2 at the text layer.
        out = convert_text("# T\n\n[[a]] [[b|c]] [[d#e]]\n")
        self.assertNotIn("[[", out)


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestAssetResolution(unittest.TestCase):
    """R5 — Obsidian's own precedence order, plus the confinement rule."""

    def test_attachment_folder_from_app_json(self):
        # R5(a) — `./_attachments` relative to the note.
        out = convert_text("# T\n\n![[diagram.png]]\n")
        self.assertIn("_attachments/diagram.png", out)

    def test_vault_wide_search_finds_a_nested_file(self):
        # R5(d) — `nested.png` is in neither the attachment folder nor the note's dir.
        out = convert_text("# T\n\n![[nested.png]]\n")
        self.assertIn("nested.png", out)
        self.assertNotIn("image not found", out)

    def test_space_in_the_resolved_path_still_yields_an_image(self):
        # A4 / D4 regression — `sub dir with space/`.
        out = convert_text("# T\n\n![[nested.png]]\n")
        self.assertRegex(out, r"!\[nested\]\(<[^>]*sub dir with space[^>]*>\)")

    def test_absolute_attachment_folder_is_refused(self):
        # R5(a) — app.json is untrusted input that travels with a vault.
        vault = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(vault, ".obsidian"))
            with open(os.path.join(vault, ".obsidian", "app.json"), "w") as fh:
                json.dump({"attachmentFolderPath": "/etc"}, fh)
            src = os.path.join(vault, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![[hosts]]\n")
            proc = run_convert(src, os.path.join(vault, "o.md"), "--vault-root", vault)
            self.assertIn("ignoring absolute attachmentFolderPath", proc.stderr)
        finally:
            shutil.rmtree(vault, ignore_errors=True)

    def test_escaping_attachment_folder_is_refused(self):
        # R5(a) — `../secrets` would redirect every lookup outside the vault.
        base = tempfile.mkdtemp()
        try:
            vault = os.path.join(base, "vault")
            os.makedirs(os.path.join(vault, ".obsidian"))
            os.makedirs(os.path.join(base, "secrets"))
            with open(os.path.join(base, "secrets", "leak.png"), "wb") as fh:
                fh.write(b"\x89PNG\r\n")
            with open(os.path.join(vault, ".obsidian", "app.json"), "w") as fh:
                json.dump({"attachmentFolderPath": "../secrets"}, fh)
            src = os.path.join(vault, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![[leak.png]]\n")
            proc = run_convert(src, os.path.join(vault, "o.md"), "--vault-root", vault)
            self.assertIn("escapes the vault", proc.stderr)
            with open(os.path.join(vault, "o.md"), encoding="utf-8") as fh:
                self.assertIn("image not found", fh.read())
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_missing_asset_is_a_placeholder_and_a_warning(self):
        # A5 / R7(a) — exit 0, nothing silently lost.
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![[nope.png]]\n")
            proc = run_convert(src, os.path.join(tmp, "o.md"))
            self.assertEqual(proc.returncode, 0)
            self.assertIn("attachment not found", proc.stderr)
            with open(os.path.join(tmp, "o.md"), encoding="utf-8") as fh:
                self.assertIn("image not found", fh.read())

    def test_strict_assets_exits_8_with_a_json_envelope(self):
        # A6 / R7(b)(c) / R15(e) — code 8 is AssetNotFound.
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![[nope.png]]\n")
            proc = run_convert(src, os.path.join(tmp, "o.md"),
                               "--strict-assets", "--json-errors")
            self.assertEqual(proc.returncode, 8)
            envelope = json.loads(proc.stderr.strip().splitlines()[-1])
            self.assertEqual(envelope["v"], 1)
            self.assertEqual(envelope["code"], 8)
            self.assertEqual(envelope["type"], "AssetNotFound")
            self.assertIn("nope.png", envelope["details"]["missing"])


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestSafeDestinations(unittest.TestCase):
    """R6 — every emitted destination must lex as an image AND survive decodeURI."""

    def test_spaces_use_the_angle_bracket_form(self):
        # R6(a) — a bare space would lex as a `text` token (D4).
        out = convert_text("# T\n\n![[nested.png]]\n")
        self.assertRegex(out, r"\]\(<[^>]*>\)")

    def test_percent_in_a_filename_is_percent_encoded(self):
        # R6(b) / A16 — decodeURI("100% coverage.png") raises URIError, so the angle
        # bracket form alone would crash md2docx.js on a legal filename.
        out = convert_text("# T\n\n![[100% coverage.png]]\n")
        self.assertIn("100%25%20coverage.png", out)
        self.assertNotIn("(<", out.split("100%25")[0].rsplit("![", 1)[-1])


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestCallouts(unittest.TestCase):
    """R8 — the [!type] marker must never reach the document."""

    def test_titled_callout_becomes_a_bold_paragraph(self):
        out = convert_text("# T\n\n> [!warning] Watch out\n> Body.\n")
        self.assertIn("> **Watch out**", out)
        self.assertNotIn("[!warning]", out)

    def test_untitled_callout_uses_the_type_label(self):
        # R8(b).
        out = convert_text("# T\n\n> [!warning]\n> Body.\n")
        self.assertIn("> **Warning**", out)

    def test_untitled_callout_label_is_localised(self):
        # R8(b) + R13.
        out = convert_text("# T\n\n> [!warning]\n> Body.\n", "--lang", "ru")
        self.assertIn("> **Внимание**", out)

    def test_unknown_type_falls_back_to_the_type_itself(self):
        # R8(c).
        out = convert_text("# T\n\n> [!nonsense]\n> Body.\n")
        self.assertIn("> **Nonsense**", out)
        self.assertNotIn("[!nonsense]", out)

    def test_foldable_suffix_is_consumed(self):
        # R8(d) — `+` and `-` must not survive into the title.
        for suffix in ("+", "-"):
            out = convert_text("# T\n\n> [!note]%s Title\n> Body.\n" % suffix)
            self.assertIn("> **Title**", out)
            self.assertNotIn("[!note]", out)

    def test_callout_body_stays_a_blockquote(self):
        # R8(e).
        out = convert_text("# T\n\n> [!note] Title\n> First.\n> Second.\n")
        self.assertIn("> First.", out)
        self.assertIn("> Second.", out)


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestMinorSyntax(unittest.TestCase):
    """R9."""

    def test_highlight_becomes_bold(self):
        # R9(a).
        self.assertIn("**hot**", convert_text("# T\n\n==hot== text\n"))

    def test_inline_comment_is_removed(self):
        # R9(b).
        out = convert_text("# T\n\nbefore %%hidden%% after\n")
        self.assertNotIn("hidden", out)
        self.assertIn("before after", out)

    def test_block_comment_is_removed(self):
        # R9(b).
        out = convert_text("# T\n\n%%\nhidden block\n%%\n\nvisible\n")
        self.assertNotIn("hidden block", out)
        self.assertIn("visible", out)

    def test_inline_tags_are_stripped_by_default(self):
        # R9(c).
        out = convert_text("# T\n\n#alpha #beta/gamma remain absent\n")
        self.assertNotIn("#alpha", out)
        self.assertNotIn("#beta", out)
        self.assertIn("remain absent", out)

    def test_inline_tags_can_be_kept(self):
        # R9(c).
        out = convert_text("# T\n\n#alpha here\n", "--inline-tags", "keep")
        self.assertIn("#alpha", out)

    def test_a_heading_is_not_a_tag(self):
        # R9(c) — `# Heading` has a space after the hash.
        out = convert_text("# T\n\n## A Heading\n\nbody\n")
        self.assertIn("## A Heading", out)

    def test_a_numeric_reference_is_not_a_tag(self):
        # R9(c) — `#42` is an issue number.
        out = convert_text("# T\n\nIssue #42 stays\n")
        self.assertIn("#42", out)

    def test_a_url_fragment_is_not_a_tag(self):
        # R9(c) — the `#` is not preceded by whitespace.
        out = convert_text("# T\n\nSee https://example.invalid/p#section here\n")
        self.assertIn("#section", out)

    def test_task_boxes_become_glyphs(self):
        # R9(d) — md2docx.js has no list checkbox support.
        out = convert_text("# T\n\n- [ ] open\n- [x] done\n")
        self.assertIn("- ☐ open", out)
        self.assertIn("- ☑ done", out)


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestInertRegions(unittest.TestCase):
    """R10 — no rule may rewrite the inside of a code region."""

    FENCE = (
        "# T\n\n```markdown\n"
        "![[x.png]]\n[[y]]\n> [!warning] Not a callout\n==nope==\n%%nope%%\n#nope\n"
        "```\n\nAfter.\n"
    )

    def test_fenced_block_is_byte_identical(self):
        out = convert_text(self.FENCE)
        for literal in ("![[x.png]]", "[[y]]", "> [!warning] Not a callout",
                        "==nope==", "%%nope%%", "#nope"):
            self.assertIn(literal, out, literal)

    def test_tilde_fence_is_also_inert(self):
        # R10(a).
        out = convert_text("# T\n\n~~~\n[[y]]\n~~~\n")
        self.assertIn("[[y]]", out)

    def test_inline_code_span_is_inert(self):
        # R10(b).
        out = convert_text("# T\n\nA span `![[z.png]]` stays.\n")
        self.assertIn("`![[z.png]]`", out)

    def test_mermaid_block_passes_through_unchanged(self):
        # R10(c) — regression against the existing Mermaid capability.
        src = "# T\n\n```mermaid\ngraph TD\n  A[==A==] --> B[[B]]\n```\n"
        out = convert_text(src)
        self.assertIn("A[==A==] --> B[[B]]", out)

    def test_thematic_break_mid_body_survives(self):
        # R10(d) — the frontmatter regex is anchored at offset 0.
        out = convert_text("# T\n\nBefore.\n\n---\n\nAfter.\n")
        self.assertIn("Before.", out)
        self.assertIn("After.", out)
        self.assertIn("\n---\n", out)

    def test_frontmatter_is_only_read_at_offset_zero(self):
        # R10(d) — a `---` block later in the note is not frontmatter.
        out = convert_text("# T\n\nBody.\n\n---\nlang: ru\n---\n\nMore.\n")
        self.assertNotIn("| Field | Value |", out)
        self.assertIn("lang: ru", out)


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestAdversarialCycle1(unittest.TestCase):
    """Regression locks for the ten findings confirmed in adversarial cycle 1.

    Each test here reproduced against the pre-fix code. They are grouped rather than filed
    under the requirement they belong to so the next reader can see, in one place, what this
    module got wrong once — and so nobody "simplifies" a guard back out.
    """

    # --- L-1 / C-1 / DOC-2 (CRITICAL): the indented-code mask ate nested list items ------

    def test_tab_indented_nested_list_is_not_treated_as_code(self):
        # Obsidian's editor indents with a TAB by default, so this is the ordinary shape of
        # a meeting note — and every embed and wikilink inside it used to survive literally,
        # with exit 0 and no warning. The whole silent-loss class this module exists to close.
        out = convert_text("# T\n\n- Parent\n\t- See [[Meeting]]\n\t- ![[diagram.png]]\n")
        self.assertNotIn("[[", out)
        self.assertIn("![diagram](", out)

    def test_four_space_indented_nested_list_is_not_treated_as_code(self):
        out = convert_text("# T\n\n- Parent\n    - See [[Meeting]]\n    - ![[diagram.png]]\n")
        self.assertNotIn("[[", out)
        self.assertIn("![diagram](", out)

    def test_ordered_and_deeply_nested_lists_are_also_live(self):
        out = convert_text(
            "# T\n\n1. One\n\t1. [[A]]\n\t\t- ![[diagram.png]]\n\n* Star\n\t* [[B]]\n")
        self.assertNotIn("[[", out)
        self.assertIn("![diagram](", out)

    def test_strict_assets_sees_a_missing_embed_inside_a_nested_list(self):
        # The defect also blinded --strict-assets: the embed was never parsed, so it could
        # not reach ctx.missing and the run exited 0 claiming success.
        tmp = tempfile.mkdtemp(dir=VAULT, prefix=".t-")
        try:
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n- Parent\n\t- ![[no-such-file.png]]\n")
            proc = run_convert(src, os.path.join(tmp, "o.md"),
                               "--vault-root", VAULT, "--strict-assets")
            self.assertEqual(proc.returncode, 8)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_real_indented_code_block_is_still_inert(self):
        # R10(a) must survive the fix — the repair is a precondition on the mask, not its
        # removal. A blank line, then four spaces, outside any list: still code.
        out = convert_text("# T\n\nIntro paragraph.\n\n    [[not-a-link]]\n    ![[x.png]]\n\nAfter.\n")
        self.assertIn("[[not-a-link]]", out)
        self.assertIn("![[x.png]]", out)

    def test_indented_line_cannot_interrupt_a_paragraph(self):
        # CommonMark: indented code needs a preceding blank line. Without one it is a lazy
        # continuation of the paragraph, so its wikilink is live text.
        out = convert_text("# T\n\nA paragraph\n    [[Target]]\n")
        self.assertNotIn("[[", out)

    # --- L-2 (HIGH): --obsidian re-based relative image links onto the temp dir ----------

    def test_plain_commonmark_relative_image_survives_the_obsidian_route(self):
        # Obsidian emits `![](img/pic.png)` when "Use [[Wikilinks]]" is off. Re-basing on
        # the mkdtemp dir turned a document that converted fine into a hard exit 1.
        tmp = tempfile.mkdtemp(dir=VAULT, prefix=".t-")
        try:
            src = os.path.join(tmp, "n.md")
            rel = os.path.relpath(os.path.join(VAULT, "_attachments", "diagram.png"), tmp)
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("---\nlang: en\n---\n\n# T\n\n![s](%s)\n" % rel.replace(" ", "%20"))
            out = os.path.join(tmp, "o.docx")
            proc = subprocess.run(
                ["node", MD2DOCX, src, out, "--obsidian", "--vault-root", VAULT],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(len(_media(out)), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # --- C-2 (HIGH): the frontmatter table was spliced inside a fenced block -------------

    def test_frontmatter_table_is_not_injected_into_a_fenced_block(self):
        # A note with frontmatter and no H1 is the NORMAL Obsidian shape (the title is the
        # filename). A shell fence whose first line starts `# ` used to capture the table.
        out = convert_text(
            "---\nlang: en\ntags:\n  - x\n---\n\nIntro.\n\n```sh\n# install\nmake\n```\n\nEnd.\n")
        self.assertTrue(out.lstrip().startswith("| Field | Value |"), out[:120])
        self.assertIn("```sh\n# install\nmake\n```", out)
        fence = out.index("```sh")
        self.assertLess(out.index("| Field | Value |"), fence)

    # --- SEC-1 (MEDIUM): transclusion was an unconfined file read -----------------------

    def test_transclusion_outside_the_vault_is_refused(self):
        # Transclusion inlines the target's TEXT into the .docx, so an unconfined target is
        # an arbitrary-file read driven by a note someone else wrote.
        base = tempfile.mkdtemp()
        try:
            vault = os.path.join(base, "vault")
            os.makedirs(os.path.join(vault, ".obsidian"))
            with open(os.path.join(base, "secret.md"), "w", encoding="utf-8") as fh:
                fh.write("SECRET KEY MATERIAL\n")
            src = os.path.join(vault, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![[../secret]]\n")
            dst = os.path.join(vault, "o.md")
            proc = run_convert(src, dst, "--vault-root", vault, "--transclude")
            self.assertEqual(proc.returncode, 0)
            self.assertIn("refusing to transclude", proc.stderr)
            with open(dst, encoding="utf-8") as fh:
                self.assertNotIn("SECRET KEY MATERIAL", fh.read())
        finally:
            shutil.rmtree(base, ignore_errors=True)

    # --- SEC-2 (LOW): the app.json guard was a string compare a symlink walked through ---

    def test_symlinked_attachment_folder_cannot_leave_the_vault(self):
        # `attachmentFolderPath: att` where `att` is a symlink out of the vault satisfies a
        # string-prefix check while the bytes come from anywhere on disk.
        base = tempfile.mkdtemp()
        try:
            vault = os.path.join(base, "vault")
            elsewhere = os.path.join(base, "elsewhere")
            os.makedirs(os.path.join(vault, ".obsidian"))
            os.makedirs(elsewhere)
            shutil.copy(os.path.join(VAULT, "_attachments", "diagram.png"),
                        os.path.join(elsewhere, "secret.png"))
            os.symlink(elsewhere, os.path.join(vault, "att"))
            with open(os.path.join(vault, ".obsidian", "app.json"), "w") as fh:
                json.dump({"attachmentFolderPath": "att"}, fh)
            src = os.path.join(vault, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![[secret.png]]\n")
            dst = os.path.join(vault, "o.md")
            proc = run_convert(src, dst, "--vault-root", vault)
            self.assertIn("leaves the vault", proc.stderr)
            with open(dst, encoding="utf-8") as fh:
                self.assertIn("image not found", fh.read())
        finally:
            shutil.rmtree(base, ignore_errors=True)

    # --- U-1 / U-2 (HIGH, carried from cycle 1's unverified set): the tag stripper -------

    def test_intra_document_link_anchor_survives_tag_stripping(self):
        # The tag lead class included `(`, so the `(` of a Markdown destination matched and
        # `[text](#some-heading)` became `[text]()` — a destroyed link, in a document that
        # may contain no Obsidian syntax at all.
        out = convert_text("# T\n\nSee [the section](#some-heading) below.\n")
        self.assertIn("[the section](#some-heading)", out)

    def test_markdown_hard_line_break_survives_tag_stripping(self):
        # Two trailing spaces are a Markdown hard line break. A document-wide
        # `/[ \t]+$/gm` strip deleted them from EVERY line, tags or no tags.
        out = convert_text("# T\n\nline one  \nline two\n")
        self.assertIn("line one  \n", out)

    def test_tag_stripping_still_works_after_those_two_fixes(self):
        # Guard against fixing the false positives by disabling the feature.
        out = convert_text("# T\n\n#alpha #beta/x here\n")
        self.assertNotIn("#alpha", out)
        self.assertNotIn("#beta", out)
        self.assertIn("here", out)

    def test_trailing_spaces_are_trimmed_only_where_a_tag_was_removed(self):
        out = convert_text("# T\n\nkeep me  \n#tag gone\n")
        self.assertIn("keep me  \n", out)
        self.assertNotIn("#tag", out)

    # --- DOC-1 (MEDIUM): four of seven Obsidian flags were silently accepted -------------

    def test_every_obsidian_flag_requires_the_obsidian_switch(self):
        # SKILL.md said "every Obsidian flag requires --obsidian"; the check covered three.
        # A value-carrying flag has a non-null default, so `opts` alone cannot tell "not
        # given" from "given the default" — the parser has to record what was typed.
        cases = [
            ["--vault-root", VAULT], ["--frontmatter", "table"], ["--lang", "ru"],
            ["--links", "italic"], ["--inline-tags", "keep"],
            ["--transclude"], ["--strict-assets"],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for flag in cases:
                proc = subprocess.run(
                    ["node", MD2DOCX, NOTE, os.path.join(tmp, "o.docx"), *flag],
                    capture_output=True, text=True)
                self.assertEqual(proc.returncode, 1, "%s was accepted without --obsidian" % flag[0])
                self.assertIn("requires --obsidian", proc.stderr, flag[0])


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestAdversarialCycle2(unittest.TestCase):
    """Regression locks for cycle 2 — which attacked cycle 1's own fixes.

    Every finding here is a defect a REPAIR introduced. That is the case for running the
    cycle at all: a fix arrives with no review pass behind it, and four of these six were
    worse than harmless.
    """

    # --- O-1 (HIGH): a masked fence inside a list cleared `inList` ----------------------

    def test_fence_inside_a_list_does_not_reopen_the_silent_loss(self):
        # The fence's sentinel lands at column 0 (keep() eats its indentation), the walker
        # read that as a flush line, and the NEXT indented continuation was masked as code.
        # Cycle 1's CRITICAL, one blank line later.
        out = convert_text(
            "# T\n\n- Step one:\n\n  ```bash\n  make\n  ```\n\n"
            "    See ![[diagram.png]] and [[Other]] here.\n\n- Step two\n")
        self.assertNotIn("[[", out)
        self.assertIn("![diagram](", out)

    def test_tab_indented_fence_inside_a_list_is_also_safe(self):
        out = convert_text("# T\n\n- Step:\n\n\t```\n\tcode\n\t```\n\n\tmore ![[diagram.png]]\n")
        self.assertIn("![diagram](", out)

    def test_the_fenced_block_itself_is_still_inert(self):
        # Guard against fixing the leak by simply not masking fences any more.
        out = convert_text("# T\n\n- Step:\n\n  ```md\n  [[keep-me]]\n  ```\n")
        self.assertIn("[[keep-me]]", out)

    # --- T30-V1 (HIGH): tag stripping flattened nested lists ----------------------------

    def test_a_list_item_that_loses_a_tag_keeps_its_indentation(self):
        # `\t- nested #tag` became `- nested`, promoting a child to a sibling and losing the
        # outline in the .docx.
        out = convert_text("# T\n\n- item one #tag\n\t- nested #other\n")
        self.assertIn("\t- nested", out)
        self.assertNotIn("#tag", out)
        self.assertNotIn("#other", out)

    def test_four_space_nested_item_keeps_its_indentation_too(self):
        out = convert_text("# T\n\n- parent\n    - child #tag\n")
        self.assertIn("    - child", out)

    # --- T30-V2 (MEDIUM): a tagged callout title rendered `**Title **` ------------------

    def test_callout_title_with_a_tag_is_not_left_with_stray_emphasis(self):
        out = convert_text("# T\n\n> [!note] Title #tag\n> Body.\n")
        self.assertIn("> **Title**", out)
        self.assertNotIn("**Title **", out)

    # --- T30-V3 (HIGH): numeric refs followed by punctuation were deleted ---------------

    def test_issue_references_with_trailing_punctuation_survive(self):
        # `#42.` `#7,` `#99!` were all stripped from ordinary prose — the rule says a
        # numeric reference is never a tag, and the lookahead only honoured it before
        # whitespace or end-of-line.
        out = convert_text("# T\n\nSee #42. Also #7, and #99!\n")
        self.assertIn("#42.", out)
        self.assertIn("#7,", out)
        self.assertIn("#99!", out)

    def test_a_word_tag_with_trailing_punctuation_is_still_stripped(self):
        out = convert_text("# T\n\nFiled under #project, done.\n")
        self.assertNotIn("#project", out)
        self.assertIn("done.", out)

    # --- V2-02 (HIGH): a transcluded note's relative images pointed at the wrong dir -----

    def test_transcluded_note_relative_image_resolves_against_its_own_directory(self):
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, ".obsidian"))
            os.makedirs(os.path.join(base, "sub", "img"))
            shutil.copy(os.path.join(VAULT, "_attachments", "diagram.png"),
                        os.path.join(base, "sub", "img", "pic.png"))
            with open(os.path.join(base, "sub", "child.md"), "w", encoding="utf-8") as fh:
                fh.write("---\nlang: en\n---\n\n# Child\n\n![c](img/pic.png)\n")
            src = os.path.join(base, "parent.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("---\nlang: en\n---\n\n# Parent\n\n![[child]]\n")
            out = os.path.join(base, "o.docx")
            proc = subprocess.run(
                ["node", MD2DOCX, src, out, "--obsidian", "--vault-root", base, "--transclude"],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(len(_media(out)), 1, "the transcluded image must be embedded")
        finally:
            shutil.rmtree(base, ignore_errors=True)

    # --- T3 (LOW): the R6(c) guard never walked table cells -----------------------------

    def test_unparsed_image_inside_a_table_cell_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "my folder"))
            shutil.copy(os.path.join(VAULT, "_attachments", "diagram.png"),
                        os.path.join(tmp, "my folder", "p.png"))
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n| a | b |\n|---|---|\n| x | ![i](my folder/p.png) |\n")
            proc = subprocess.run(["node", MD2DOCX, src, os.path.join(tmp, "o.docx")],
                                  capture_output=True, text=True)
            self.assertIn("unescaped spaces", proc.stderr)

    # --- T5 (HIGH, carried): the app.json test asserted a warning, not the refusal -------

    def test_absolute_attachment_folder_refusal_is_asserted_by_effect(self):
        # The original asserted only the warning string, so a warn-then-follow
        # implementation passed it. Assert the OUTCOME: the attachment is not resolved.
        base = tempfile.mkdtemp()
        try:
            vault = os.path.join(base, "vault")
            outside = os.path.join(base, "outside")
            os.makedirs(os.path.join(vault, ".obsidian"))
            os.makedirs(outside)
            shutil.copy(os.path.join(VAULT, "_attachments", "diagram.png"),
                        os.path.join(outside, "target.png"))
            with open(os.path.join(vault, ".obsidian", "app.json"), "w") as fh:
                json.dump({"attachmentFolderPath": outside}, fh)
            src = os.path.join(vault, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![[target.png]]\n")
            dst = os.path.join(vault, "o.md")
            proc = run_convert(src, dst, "--vault-root", vault)
            self.assertIn("ignoring absolute attachmentFolderPath", proc.stderr)
            with open(dst, encoding="utf-8") as fh:
                body = fh.read()
            self.assertIn("image not found", body)
            self.assertNotIn(outside, body)
        finally:
            shutil.rmtree(base, ignore_errors=True)


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestAdversarialCycle3(unittest.TestCase):
    """Regression locks for cycle 3, which attacked cycle 2's repairs.

    Two of the six cycle-2 fixes carried new defects. Both are here, together with the
    transclusion pipeline bug the round surfaced as a side effect.
    """

    # --- C3-01 (HIGH): the sentinel step-over leaked list state past the list's end -----

    def test_indented_code_after_a_list_and_a_column0_fence_stays_inert(self):
        # A fence at column 0 CLOSES the list, but `keep()` swallowed its indentation, so
        # the walker saw only a sentinel and kept `inList` true forever after. The next
        # genuine top-level indented code block was left visible and rewritten:
        # `#include <stdio.h>` came back as `<stdio.h>`.
        out = convert_text(
            "# T\n\n- item one\n\n```\nx\n```\n\n    #include <stdio.h>\n\ndone\n")
        self.assertIn("    #include <stdio.h>", out)

    def test_that_block_is_inert_for_every_rule_not_just_tags(self):
        out = convert_text(
            "# T\n\n- a\n\n```\nx\n```\n\n    [[NotALink]] and ==hi==\n\nend\n")
        self.assertIn("[[NotALink]]", out)
        self.assertIn("==hi==", out)

    def test_an_indented_fence_still_does_not_close_the_list(self):
        # The other half of the trade: an INDENTED fence is list content, so the list must
        # stay open and its continuation must stay live (this is cycle 2's O-1).
        out = convert_text("# T\n\n- Step:\n\n\t```\n\tcode\n\t```\n\n\tmore [[a link]]\n")
        self.assertNotIn("[[", out)

    # --- C3-02 / V3-01 (HIGH): transcluded text was rewritten twice --------------------

    def test_transcluded_code_block_is_not_rewritten_by_the_parent_pass(self):
        # transclude() runs inside rewriteEmbeds — the FIRST of five passes — so text handed
        # back unmasked is rewritten again by the parent's remaining passes, with the child's
        # own masking already spent.
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, ".obsidian"))
            with open(os.path.join(base, "child.md"), "w", encoding="utf-8") as fh:
                fh.write('# Child\n\n```sh\n# deps  [[not-a-link]]  #include <stdio.h>\n'
                         'echo "==keep=="\n```\n')
            src = os.path.join(base, "parent.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# Parent\n\n![[child]]\n")
            dst = os.path.join(base, "out.md")
            proc = run_convert(src, dst, "--vault-root", base, "--transclude")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(dst, encoding="utf-8") as fh:
                body = fh.read()
            self.assertIn("[[not-a-link]]", body)
            self.assertIn("#include <stdio.h>", body)
            self.assertIn("==keep==", body)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_heading_demote_does_not_edit_a_comment_inside_a_transcluded_fence(self):
        # The R12(a) demote ran after unmasking and read `# deps` inside a shell fence as a
        # heading, rewriting the code it was inlining.
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, ".obsidian"))
            with open(os.path.join(base, "child.md"), "w", encoding="utf-8") as fh:
                fh.write("# Child\n\n```sh\n# deps\nmake\n```\n")
            src = os.path.join(base, "parent.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# Parent\n\n![[child]]\n")
            dst = os.path.join(base, "out.md")
            run_convert(src, dst, "--vault-root", base, "--transclude")
            with open(dst, encoding="utf-8") as fh:
                body = fh.read()
            self.assertIn("\n# deps\n", body)
            self.assertNotIn("## deps", body)
            self.assertIn("## Child", body)      # the real heading IS demoted
        finally:
            shutil.rmtree(base, ignore_errors=True)

    # --- C3-03 (MEDIUM): the tag tidy collapsed alignment the author chose --------------

    def test_internal_alignment_survives_tag_stripping(self):
        out = convert_text("# T\n\n- val  = 1   #tag\n")
        self.assertIn("val  = 1", out)
        self.assertNotIn("#tag", out)

    # --- V3-02 (MEDIUM): G5 missed angle-bracket and titled destinations ---------------

    def test_transcluded_angle_bracket_image_is_re_rooted(self):
        # The shape this skill itself emits for any path with a space.
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, ".obsidian"))
            os.makedirs(os.path.join(base, "sub", "my imgs"))
            shutil.copy(os.path.join(VAULT, "_attachments", "diagram.png"),
                        os.path.join(base, "sub", "my imgs", "pic.png"))
            with open(os.path.join(base, "sub", "child.md"), "w", encoding="utf-8") as fh:
                fh.write("---\nlang: en\n---\n\n# Child\n\n![c](<my imgs/pic.png>)\n")
            src = os.path.join(base, "parent.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("---\nlang: en\n---\n\n# Parent\n\n![[child]]\n")
            out = os.path.join(base, "o.docx")
            proc = subprocess.run(
                ["node", MD2DOCX, src, out, "--obsidian", "--vault-root", base, "--transclude"],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(len(_media(out)), 1)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_remote_and_absolute_destinations_are_left_alone(self):
        # The re-rooting must not touch what it does not own.
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, ".obsidian"))
            with open(os.path.join(base, "child.md"), "w", encoding="utf-8") as fh:
                fh.write("# Child\n\n![r](https://example.invalid/x.png)\n\n"
                         "![d](data:image/png;base64,AAAA)\n\n[t](rel.md)\n")
            src = os.path.join(base, "parent.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# Parent\n\n![[child]]\n")
            dst = os.path.join(base, "out.md")
            run_convert(src, dst, "--vault-root", base, "--transclude")
            with open(dst, encoding="utf-8") as fh:
                body = fh.read()
            self.assertIn("https://example.invalid/x.png", body)
            self.assertIn("data:image/png;base64,AAAA", body)
            self.assertIn("[t](rel.md)", body)
        finally:
            shutil.rmtree(base, ignore_errors=True)


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestAdversarialCycle4(unittest.TestCase):
    """Regression locks for cycle 4, which retired four regex-based masking designs.

    Cycle 4 found two CRITICALs. Both were reachable from ordinary notes, both were silent,
    and both defeated `--strict-assets`. The masking is now one line-based state machine
    over a single shared store; these tests are what stops it from becoming regexes again.
    """

    # --- C4-01 (CRITICAL): an unmatched backtick masked whole sections -----------------

    def test_a_stray_backtick_does_not_mask_the_rest_of_the_document(self):
        # An unmatched run paired with the NEXT genuine span's opener, so every paragraph
        # between them was stored as one "inline span" and restored verbatim. Embeds and
        # wikilinks reached the .docx literally, at exit 0, with no warning.
        out = convert_text(
            "# T\n\nA stray ` backtick in prose.\n\nSee [[Note]] and ![[diagram.png]] here.\n\n"
            "Use `code` at the end.\n")
        self.assertNotIn("[[", out)
        self.assertIn("![diagram](", out)
        self.assertIn("`code`", out)      # the real span is still masked

    def test_strict_assets_still_sees_a_missing_asset_past_a_stray_backtick(self):
        # The mask also hid the missing attachment from R7(b), so exit 8 never fired.
        tmp = tempfile.mkdtemp(dir=VAULT, prefix=".t-")
        try:
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\nA stray ` here.\n\nSee ![[nope.png]].\n\nUse `code`.\n")
            proc = run_convert(src, os.path.join(tmp, "o.md"),
                               "--vault-root", VAULT, "--strict-assets")
            self.assertEqual(proc.returncode, 8)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unterminated_blockquoted_fence_ends_with_its_blockquote(self):
        # A fence inside a blockquote was not matched by the fence pass (the `>` defeated
        # its `^[ \t]*`), fell through to the inline pass, and swallowed the document.
        out = convert_text(
            "# T\n\n> ```js\n> snippet\n\nReal [[Note]] and ![[diagram.png]] here\n\n"
            "Some `inline` code\n")
        self.assertNotIn("[[", out)
        self.assertIn("![diagram](", out)

    def test_a_matched_inline_span_is_still_masked(self):
        # Guard against fixing the leak by not masking inline code at all.
        out = convert_text("# T\n\nA `![[z.png]]` span and ``a ` b`` too.\n")
        self.assertIn("`![[z.png]]`", out)

    # --- C4-02 / V4-01 (CRITICAL/HIGH): nested transclusion substituted wrong text ------

    def test_nested_transclusion_preserves_every_generation(self):
        # A embeds B embeds C. Separate mask stores per note meant C was masked against one
        # store and unmasked against another: C's code block was DESTROYED and B's was
        # duplicated in its place.
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, ".obsidian"))
            for name, body in (
                ("C", "# C\n\n```sh\nCCC_CODE\n```\n"),
                ("B", "# B\n\n```sh\nBBB_CODE\n```\n\n![[C]]\n"),
                ("A", "# A\n\n![[B]]\n"),
            ):
                with open(os.path.join(base, name + ".md"), "w", encoding="utf-8") as fh:
                    fh.write(body)
            dst = os.path.join(base, "out.md")
            proc = run_convert(os.path.join(base, "A.md"), dst,
                               "--vault-root", base, "--transclude")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(dst, encoding="utf-8") as fh:
                body = fh.read()
            self.assertEqual(body.count("BBB_CODE"), 1, "B duplicated or lost")
            self.assertEqual(body.count("CCC_CODE"), 1, "C duplicated or lost")
            self.assertNotIn("obsmask", body, "a mask sentinel leaked into the output")
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_no_mask_sentinel_ever_reaches_the_output(self):
        # The single highest-signal check in the suite: a sentinel in the output means the
        # store identity is wrong somewhere.
        out = convert_text(
            "# T\n\n```sh\ncode\n```\n\nA `span` and\n\n    indented\n\n> quote\n")
        self.assertNotIn("obsmask", out)

    # --- C4-04 (HIGH): a fence indented 1-3 spaces did not close the list --------------

    def test_fence_indented_one_to_three_spaces_closes_the_list(self):
        # List CONTENT starts after the marker and its spaces; using marker-indent + 1 made
        # a 1-space-indented fence look like list content, so the list never closed and the
        # following indented code block was rewritten.
        out = convert_text("# T\n\n- a\n\n ```\nx\n ```\n\n    #include <stdio.h>\n\nend\n")
        self.assertIn("    #include <stdio.h>", out)

    def test_a_fence_indented_into_the_list_stays_list_content(self):
        # The other side of the same boundary.
        out = convert_text("# T\n\n- a\n\n  ```\nx\n  ```\n\n  more [[a link]]\n")
        self.assertNotIn("[[", out)


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestAdversarialCycle5(unittest.TestCase):
    """Regression locks for cycle 5, which attacked the cycle-4 state-machine rewrite.

    Cycle 5 found the defect in `flushParagraph` — the index arithmetic I had flagged as the
    least-reviewed code in the file — plus four more the suite could not see.
    """

    # --- C5-02 (CRITICAL): flushParagraph duplicated paragraph text --------------------

    def test_a_multi_line_code_span_does_not_duplicate_its_paragraph(self):
        # Masking can shrink a paragraph's line count; the write-back mapped the new lines
        # onto the old slots with a NEGATIVE slice offset, which JavaScript reads as "all but
        # the last N" rather than "empty", so lines landed in two slots each.
        out = convert_text("# T\n\nalpha `one\ntwo\nthree` beta\ngamma\n")
        self.assertEqual(out.count("alpha"), 1)
        self.assertEqual(out.count("gamma"), 1)

    def test_an_image_in_such_a_paragraph_is_embedded_once(self):
        # The visible symptom: the same picture twice in the .docx.
        tmp = tempfile.mkdtemp(dir=VAULT, prefix=".t-")
        try:
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\nsee `one\ntwo\nthree` and ![[diagram.png]]\nend\n")
            out = os.path.join(tmp, "o.docx")
            proc = subprocess.run(
                ["node", MD2DOCX, src, out, "--obsidian", "--vault-root", VAULT],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(len(_media(out)), 1, "image embedded more than once")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # --- C5-01 (HIGH): a CRLF note's fence never closed --------------------------------

    def test_crlf_note_converts_past_its_first_fence(self):
        # The closing regex is `$`-anchored and allows only spaces/tabs, so ```\r could never
        # match, while the opener's info-string class ate the \r. Every fence opened, none
        # closed, and the rest of the document was masked to EOF.
        out = convert_text("# T\r\n\r\n```\r\nx\r\n```\r\n\r\nSee [[Other]] here\r\n")
        self.assertNotIn("[[", out)

    def test_crlf_does_not_disable_strict_assets(self):
        # The mask also hid the missing attachment, so exit 8 stopped firing.
        tmp = tempfile.mkdtemp(dir=VAULT, prefix=".t-")
        try:
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8", newline="") as fh:
                fh.write("# T\r\n\r\n```\r\nx\r\n```\r\n\r\n![[nope.png]]\r\n")
            proc = run_convert(src, os.path.join(tmp, "o.md"),
                               "--vault-root", VAULT, "--strict-assets")
            self.assertEqual(proc.returncode, 8)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # --- C5-03 (HIGH): a blockquoted fence had its `>` prefix doubled ------------------

    def test_blockquoted_fence_keeps_exactly_one_quote_prefix(self):
        # The buffer already carries the prefix; prepending it again produced `> > ```js`,
        # which changes the quote depth and the rendered structure.
        out = convert_text("# T\n\n> ```js\n> code\n> ```\n\nafter\n")
        self.assertIn("> ```js", out)
        self.assertNotIn("> > ", out)

    # --- C5-03b (HIGH): a backslash-escaped backtick opened a mask region --------------

    def test_escaped_backtick_does_not_open_a_mask(self):
        # Same shape as cycle 4's stray-backtick CRITICAL, through a different door.
        out = convert_text("# T\n\nA \\` and [[X]] and `code` here.\n")
        self.assertNotIn("[[", out)
        self.assertIn("`code`", out)

    def test_an_escaped_backtick_inside_a_real_span_is_still_content(self):
        out = convert_text("# T\n\nUse `a \\` b` and [[X]].\n")
        self.assertIn("`a \\` b`", out)
        self.assertNotIn("[[", out)

    # --- C5-04 (MEDIUM): a tilde fence may carry backticks in its info string ----------

    def test_tilde_fence_with_a_backtick_in_its_info_string_is_a_fence(self):
        # CommonMark forbids a backtick in a BACKTICK fence's info string and allows it in a
        # tilde fence's; applying the backtick rule to both left the block unmasked.
        out = convert_text("# T\n\n~~~`js\n[[keep-me]]\n~~~\n\nSee [[Y]]\n")
        self.assertIn("[[keep-me]]", out)      # inside the fence: inert
        self.assertNotIn("See [[Y]]", out)     # outside it: rewritten

    def test_a_backtick_fence_info_string_still_rejects_backticks(self):
        # The other side of the same rule. `` ```a`b `` is three ticks with the info string
        # "a`b", which CommonMark does not accept as a fence — so its contents are ordinary
        # text and must be rewritten. (Note `` ````js `` would be a FOUR-tick fence with info
        # "js", which is perfectly valid; the two are easy to confuse.)
        out = convert_text("# T\n\n```a`b\n[[rewrite-me]]\n```\n")
        self.assertNotIn("[[rewrite-me]]", out)


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestCarryoverMedium(unittest.TestCase):
    """The MEDIUM findings the cycles raised but never verified.

    Three were live defects; three were mutation survivors — requirements with no test at
    all, which is the same exposure as a defect and harder to see.
    """

    # --- C5-06: blank runs inside an indented code block were deleted -----------------

    def test_blank_line_run_inside_indented_code_survives(self):
        # The blank-run branch pushed ONE blank and jumped the cursor past the rest, so the
        # masked region restored different bytes than it captured — it edited the code.
        out = convert_text("para\n\n    line1\n\n\n    line2\n\nafter\n")
        self.assertIn("    line1\n\n\n    line2", out)

    def test_masking_is_reversible_on_that_shape(self):
        # The property the defect broke, asserted directly.
        script = (
            'const l=require(process.argv[1]);'
            'const s="para\\n\\n    a\\n\\n\\n\\n    b\\n\\nafter\\n";'
            'const {store,keep}=l.newMaskStore();'
            'process.stdout.write(String(l.unmaskCode(l.maskAll(s,keep),store)===s));')
        proc = subprocess.run(
            ["node", "-e", script, os.path.join(SCRIPTS, "_obsidian_lib.js")],
            capture_output=True, text=True)
        self.assertEqual(proc.stdout.strip(), "true", proc.stderr)

    # --- C5-05b (I4): a note could forge a mask sentinel -----------------------------

    def test_a_note_carrying_the_sentinel_bytes_cannot_inject_stored_code(self):
        # U+0000 is valid UTF-8 and readFileSync preserves it, so the "NUL cannot occur"
        # assumption was false: an in-range index spliced an unrelated code region into the
        # note. Control characters are now stripped before masking — which XML 1.0 requires
        # anyway, since a NUL would make the .docx unopenable.
        tmp = tempfile.mkdtemp(dir=VAULT, prefix=".t-")
        try:
            src = os.path.join(tmp, "n.md")
            nul = chr(0)
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n```sh\nSECRET_FENCE\n```\n\nHere: "
                         + nul + "obsmask0" + nul + "\n")
            dst = os.path.join(tmp, "o.md")
            proc = run_convert(src, dst, "--vault-root", VAULT)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(dst, encoding="utf-8") as fh:
                body = fh.read()
            self.assertEqual(body.count("SECRET_FENCE"), 1, "a stored region was injected")
            self.assertEqual(body.count(chr(0)), 0, "NUL reached the output")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # --- C5-04: a diamond was mis-reported as a cycle --------------------------------

    def test_diamond_transclusion_inlines_the_shared_note_twice(self):
        # A embeds B and C; both embed Shared. `visited` was never cleared on unwind, so the
        # second, non-recursive occurrence tripped the cycle branch: the shared note was
        # replaced by a pointer and the run reported a cycle that did not exist.
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, ".obsidian"))
            for name, body in (("Shared", "# Shared\n\nSHARED_BODY_TEXT\n"),
                               ("B", "# B\n\n![[Shared]]\n"),
                               ("C", "# C\n\n![[Shared]]\n"),
                               ("A", "# A\n\n![[B]]\n\n![[C]]\n")):
                with open(os.path.join(base, name + ".md"), "w", encoding="utf-8") as fh:
                    fh.write(body)
            dst = os.path.join(base, "out.md")
            proc = run_convert(os.path.join(base, "A.md"), dst,
                               "--vault-root", base, "--transclude")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("cycle", proc.stderr)
            with open(dst, encoding="utf-8") as fh:
                body = fh.read()
            self.assertEqual(body.count("SHARED_BODY_TEXT"), 2)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_a_true_cycle_is_still_caught(self):
        # The other side of the same change: `visited` must still catch a real cycle.
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, ".obsidian"))
            for name, body in (("P", "# P\n\nP_BODY\n\n![[Q]]\n"),
                               ("Q", "# Q\n\nQ_BODY\n\n![[P]]\n")):
                with open(os.path.join(base, name + ".md"), "w", encoding="utf-8") as fh:
                    fh.write(body)
            proc = run_convert(os.path.join(base, "P.md"), os.path.join(base, "o.md"),
                               "--vault-root", base, "--transclude")
            self.assertEqual(proc.returncode, 0)
            self.assertIn("cycle", proc.stderr)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    # --- C5-08 (mutation survivor): R12(c) depth cap had no test ---------------------

    def test_transclusion_depth_cap_is_enforced(self):
        # A->B->C->D inline; E is refused at the cap. Disabling MAX_TRANSCLUDE_DEPTH left
        # the suite green, so the requirement was unlocked.
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, ".obsidian"))
            chain = ["A", "B", "C", "D", "E"]
            for i, name in enumerate(chain):
                nxt = "\n\n![[%s]]\n" % chain[i + 1] if i + 1 < len(chain) else "\n"
                with open(os.path.join(base, name + ".md"), "w", encoding="utf-8") as fh:
                    fh.write("# %s\n\n%s_BODY%s" % (name, name, nxt))
            dst = os.path.join(base, "out.md")
            proc = run_convert(os.path.join(base, "A.md"), dst,
                               "--vault-root", base, "--transclude")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("depth limit", proc.stderr)
            with open(dst, encoding="utf-8") as fh:
                body = fh.read()
            for name in ("B", "C", "D"):
                self.assertIn(name + "_BODY", body, name + " should be inlined")
            self.assertNotIn("E_BODY", body, "E is past the cap and must not be inlined")
        finally:
            shutil.rmtree(base, ignore_errors=True)

    # --- C5-10 (mutation survivor): render mode's multi-value branch had no test ------

    def test_render_mode_keeps_every_value_of_a_multi_value_key(self):
        # Dropping every attendee after the first passed the suite — the D1 failure class
        # this task exists to close, in a selectable mode.
        out = convert_text(
            "---\nlang: en\nparticipants:\n  - Ada Lovelace\n  - Alan Turing\n---\n\n# T\n",
            "--frontmatter", "render")
        self.assertIn("- Ada Lovelace", out)
        self.assertIn("- Alan Turing", out)

    # --- C5-11 (mutation survivor): six R5 sub-features had no test -------------------

    def test_r5d_vault_index_folds_nfc_and_case(self):
        # macOS hands out NFD; a byte compare finds no such filename at all. The note spells
        # the name in NFC and the file on disk is written in NFD.
        #
        # The name MUST contain a character that actually decomposes. The first version of
        # this test used "Схема.png", whose Cyrillic letters have no decomposition, so NFD
        # and NFC were the same string and the test asserted nothing — a vacuous test, which
        # is the defect class it exists to catch. "й" (U+0439) decomposes to и + U+0306.
        # It also uses a capital in the note to exercise the case-fold half of R5(d).
        import unicodedata
        name = "Стройка.png"
        self.assertNotEqual(unicodedata.normalize("NFD", name),
                            unicodedata.normalize("NFC", name),
                            "fixture name must decompose or this test proves nothing")
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, ".obsidian"))
            os.makedirs(os.path.join(base, "deep"))
            on_disk = unicodedata.normalize("NFD", name)
            shutil.copy(os.path.join(VAULT, "_attachments", "diagram.png"),
                        os.path.join(base, "deep", on_disk))
            if unicodedata.normalize("NFD", os.listdir(os.path.join(base, "deep"))[0]) != on_disk:
                self.skipTest("filesystem normalises filenames; NFD cannot be staged here")
            src = os.path.join(base, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![[%s]]\n" % unicodedata.normalize("NFC", name).upper())
            dst = os.path.join(base, "o.md")
            proc = run_convert(src, dst, "--vault-root", base)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(dst, encoding="utf-8") as fh:
                self.assertNotIn("image not found", fh.read())
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_r5e_ambiguous_attachment_warns_with_every_candidate(self):
        # Spec clause R-2: more than one vault-wide match must list the candidates rather
        # than silently taking the first.
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, ".obsidian"))
            for sub in ("one", "two"):
                os.makedirs(os.path.join(base, sub))
                shutil.copy(os.path.join(VAULT, "_attachments", "diagram.png"),
                            os.path.join(base, sub, "shot.png"))
            src = os.path.join(base, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![[shot.png]]\n")
            proc = run_convert(src, os.path.join(base, "o.md"), "--vault-root", base)
            self.assertIn("ambiguous attachment", proc.stderr)
            self.assertIn("one", proc.stderr)
            self.assertIn("two", proc.stderr)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_r5f_vault_root_is_discovered_by_walking_up_to_dot_obsidian(self):
        # No --vault-root given: the root is the nearest ancestor holding `.obsidian/`.
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, ".obsidian"))
            os.makedirs(os.path.join(base, "notes", "deep"))
            os.makedirs(os.path.join(base, "assets"))
            shutil.copy(os.path.join(VAULT, "_attachments", "diagram.png"),
                        os.path.join(base, "assets", "far.png"))
            src = os.path.join(base, "notes", "deep", "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![[far.png]]\n")
            dst = os.path.join(base, "notes", "deep", "o.md")
            proc = run_convert(src, dst)          # deliberately no --vault-root
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(dst, encoding="utf-8") as fh:
                self.assertNotIn("image not found", fh.read())
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_r5h_skip_dirs_are_not_indexed(self):
        # `.trash` is Obsidian's soft-delete folder: indexing it resurrects deleted files.
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, ".obsidian"))
            os.makedirs(os.path.join(base, ".trash"))
            shutil.copy(os.path.join(VAULT, "_attachments", "diagram.png"),
                        os.path.join(base, ".trash", "deleted.png"))
            src = os.path.join(base, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![[deleted.png]]\n")
            dst = os.path.join(base, "o.md")
            run_convert(src, dst, "--vault-root", base)
            with open(dst, encoding="utf-8") as fh:
                self.assertIn("image not found", fh.read())
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_r5h_directory_symlinks_are_not_followed_by_the_index(self):
        # The vault-wide search has no confinement check of its own, so not descending into a
        # directory symlink is what keeps it inside the vault.
        #
        # Honest scope: this test asserts the OUTCOME, not the `isSymbolicLink()` guard.
        # Removing that guard does NOT make this fail, because `readdir(withFileTypes)`
        # already reports a symlinked directory as `isDirectory() === false` (measured). The
        # explicit check is defensive redundancy; the outcome is what matters and is locked
        # here either way.
        base = tempfile.mkdtemp()
        try:
            vault = os.path.join(base, "vault")
            outside = os.path.join(base, "outside")
            os.makedirs(os.path.join(vault, ".obsidian"))
            os.makedirs(outside)
            shutil.copy(os.path.join(VAULT, "_attachments", "diagram.png"),
                        os.path.join(outside, "target.png"))
            os.symlink(outside, os.path.join(vault, "linked"))
            src = os.path.join(vault, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![[target.png]]\n")
            dst = os.path.join(vault, "o.md")
            run_convert(src, dst, "--vault-root", vault)
            with open(dst, encoding="utf-8") as fh:
                self.assertIn("image not found", fh.read())
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_r5a_dot_slash_attachment_folder_rejects_dot_dot(self):
        # The note-relative form is checked for `..` separately from the vault-relative one.
        base = tempfile.mkdtemp()
        try:
            vault = os.path.join(base, "vault")
            os.makedirs(os.path.join(vault, ".obsidian"))
            os.makedirs(os.path.join(base, "outside"))
            shutil.copy(os.path.join(VAULT, "_attachments", "diagram.png"),
                        os.path.join(base, "outside", "t.png"))
            with open(os.path.join(vault, ".obsidian", "app.json"), "w") as fh:
                json.dump({"attachmentFolderPath": "./../outside"}, fh)
            src = os.path.join(vault, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![[t.png]]\n")
            dst = os.path.join(vault, "o.md")
            proc = run_convert(src, dst, "--vault-root", vault)
            self.assertIn("..", proc.stderr)
            with open(dst, encoding="utf-8") as fh:
                self.assertIn("image not found", fh.read())
        finally:
            shutil.rmtree(base, ignore_errors=True)


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestIdempotenceAndRegression(unittest.TestCase):
    """R14 — the two properties that make this safe to ship."""

    def test_conversion_is_idempotent(self):
        # A7 / R14(a).
        with tempfile.TemporaryDirectory() as tmp:
            first = os.path.join(tmp, "1.md")
            second = os.path.join(tmp, "2.md")
            self.assertEqual(run_convert(NOTE, first, "--vault-root", VAULT).returncode, 0)
            self.assertEqual(run_convert(first, second, "--vault-root", VAULT).returncode, 0)
            with open(first, encoding="utf-8") as a, open(second, encoding="utf-8") as b:
                self.assertEqual(a.read(), b.read())

    def test_plain_commonmark_is_byte_identical(self):
        # A10 / R14(b) — zero regression for a document with no Obsidian syntax.
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, "out.md")
            self.assertEqual(run_convert(PLAIN, dst, "--vault-root", VAULT).returncode, 0)
            with open(PLAIN, encoding="utf-8") as a, open(dst, encoding="utf-8") as b:
                self.assertEqual(a.read(), b.read())


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestTransclusion(unittest.TestCase):
    """R12 — MVP=NO, behind --transclude."""

    def test_transclusion_inlines_the_target_body(self):
        # R12(a).
        out = convert_text("# T\n\n![[linked note]]\n", "--transclude")
        self.assertIn("Body of the linked note", out)

    def test_target_frontmatter_is_never_re_emitted(self):
        # R12(b).
        out = convert_text("# T\n\n![[linked note]]\n", "--transclude")
        self.assertNotIn("type: note", out)

    def test_mutual_transclusion_terminates(self):
        # A9 / R12(d)(e) — `linked note.md` embeds `note.md` back.
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_convert(NOTE, os.path.join(tmp, "o.md"),
                               "--vault-root", VAULT, "--transclude")
            self.assertEqual(proc.returncode, 0)
            self.assertIn("cycle", proc.stderr)

    def test_headings_are_demoted(self):
        # R12(a).
        out = convert_text("# T\n\n![[linked note]]\n", "--transclude")
        self.assertIn("### Some Heading", out)


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestCliContract(unittest.TestCase):
    """R1, R15 — exit codes and argument handling."""

    def test_missing_operands_is_a_usage_error(self):
        proc = subprocess.run(["node", OBSIDIAN2MD], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)

    def test_unknown_flag_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n")
            proc = run_convert(src, os.path.join(tmp, "o.md"), "--nonsense")
        self.assertEqual(proc.returncode, 2)

    def test_flag_without_its_value_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n")
            proc = run_convert(src, os.path.join(tmp, "o.md"), "--lang")
        self.assertEqual(proc.returncode, 2)

    def test_same_path_is_refused_with_exit_6(self):
        # R1(d) / R15(d) — the input note must never be destroyed.
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n")
            proc = run_convert(src, src, "--json-errors")
            self.assertEqual(proc.returncode, 6)
            self.assertEqual(json.loads(proc.stderr.strip())["type"],
                             "SelfOverwriteRefused")
            with open(src, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "# T\n")

    def test_unreadable_input_is_exit_1(self):
        # R15(b).
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_convert(os.path.join(tmp, "nope.md"),
                               os.path.join(tmp, "o.md"), "--json-errors")
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(json.loads(proc.stderr.strip())["type"], "IOError")

    def test_bad_vault_root_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n")
            proc = run_convert(src, os.path.join(tmp, "o.md"),
                               "--vault-root", os.path.join(tmp, "nope"))
        self.assertEqual(proc.returncode, 2)


def _unzip(path, member="word/document.xml"):
    with zipfile.ZipFile(path) as zf:
        return zf.read(member).decode("utf-8")


def _media(path):
    with zipfile.ZipFile(path) as zf:
        return [n for n in zf.namelist()
                if n.startswith("word/media/") and n.lower().endswith((".png", ".jpg"))]


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestOneCommandRoute(unittest.TestCase):
    """R11 — md2docx.js --obsidian, and the acceptance criteria that need the package."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.docx = os.path.join(cls.tmp, "out.docx")
        cls.proc = subprocess.run(
            ["node", MD2DOCX, NOTE, cls.docx, "--obsidian",
             "--vault-root", VAULT, "--page-size", "A4"],
            capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_exits_zero(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)

    def test_a1_every_embed_became_an_image(self):
        # A1 — 5 resolvable embeds in the fixture note, no mermaid block.
        self.assertEqual(len(_media(self.docx)), 5)

    def test_a3_frontmatter_value_is_inside_a_table(self):
        # A3 — the user's requirement, asserted structurally.
        xml = _unzip(self.docx)
        tables = re.findall(r"<w:tbl>.*?</w:tbl>", xml, re.S)
        self.assertTrue(tables)
        self.assertTrue(any("Ada Lovelace" in t for t in tables),
                        "participants must render inside a <w:tbl>")

    def test_a3_table_uses_the_shared_header_shading(self):
        # A3 — "in the style of the other tables" means the SAME styling, which only
        # holds because the frontmatter goes through md2docx.js's `table` token path.
        tables = re.findall(r"<w:tbl>.*?</w:tbl>", _unzip(self.docx), re.S)
        frontmatter = next(t for t in tables if "Ada Lovelace" in t)
        self.assertIn("D5E8F0", frontmatter)
        self.assertIn("CCCCCC", frontmatter)

    def test_a2_only_code_regions_keep_a_literal_wikilink(self):
        # A2 — the three survivors are the fenced block's two and the inline span's one,
        # which R10 REQUIRES to survive. Anything else is a leak.
        self.assertEqual(_unzip(self.docx).count("[["), 3)

    def test_a13_width_hint_is_applied_with_the_aspect_ratio(self):
        # A13 / R3(g)(h) — diagram.png is 400x300, so `|120` gives 120x90.
        xml = _unzip(self.docx)
        extents = [(int(a), int(b)) for a, b in
                   re.findall(r'<wp:extent cx="(\d+)" cy="(\d+)"', xml)]
        px = [(cx // 9525, cy // 9525) for cx, cy in extents]
        self.assertIn((120, 90), px)
        self.assertIn((100, 50), px)     # photo.jpg via `|100x50`
        self.assertIn((400, 300), px)    # the un-hinted embed keeps its natural size

    def test_a8_package_validates(self):
        # A8.
        proc = subprocess.run(
            [sys.executable, VALIDATE, self.docx], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_vault_root_without_obsidian_is_rejected(self):
        # R11(d) — exit 1, md2docx.js's code for every usage error.
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                ["node", MD2DOCX, NOTE, os.path.join(tmp, "o.docx"),
                 "--vault-root", VAULT],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("requires --obsidian", proc.stderr)

    def test_flag_order_does_not_matter(self):
        # R11(d) — the check runs after the parse loop.
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                ["node", MD2DOCX, NOTE, os.path.join(tmp, "o.docx"),
                 "--vault-root", VAULT, "--obsidian"],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_strict_assets_exits_8_on_the_one_command_route(self):
        # R11(e) — same code as the standalone CLI, without the JSON envelope.
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                ["node", MD2DOCX, NOTE, os.path.join(tmp, "o.docx"),
                 "--obsidian", "--vault-root", VAULT, "--strict-assets"],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 8)

    def test_no_temp_directory_is_left_behind_on_success(self):
        # R11(c). The original version of this test only ran the `--strict-assets` path,
        # which exits BEFORE `fs.mkdtempSync` — so it snapshotted a run that created no
        # temp directory at all and could never have failed.
        before = self._temp_dirs()
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                ["node", MD2DOCX, NOTE, os.path.join(tmp, "o.docx"),
                 "--obsidian", "--vault-root", VAULT],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self._temp_dirs() - before, set())

    def test_no_temp_directory_is_left_behind_on_failure(self):
        # R11(c) — the half that matters. This input reaches mkdtemp and THEN dies, so a
        # missing cleanup hook shows up here and nowhere else.
        before = self._temp_dirs()
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(VAULT, ".t-fail.md")
            try:
                with open(src, "w", encoding="utf-8") as fh:
                    fh.write("# T\n\n![broken](<no-such-image.png>)\n")
                proc = subprocess.run(
                    ["node", MD2DOCX, src, os.path.join(tmp, "o.docx"),
                     "--obsidian", "--vault-root", VAULT],
                    capture_output=True, text=True)
                self.assertNotEqual(proc.returncode, 0,
                                    "fixture must fail AFTER the temp dir is made")
            finally:
                if os.path.exists(src):
                    os.remove(src)
        self.assertEqual(self._temp_dirs() - before, set())

    @staticmethod
    def _temp_dirs():
        return {n for n in os.listdir(tempfile.gettempdir())
                if n.startswith("md2docx-obsidian-")}


@unittest.skipUnless(HAVE_NODE, "node not available")
class TestNoRegressionWithoutObsidian(unittest.TestCase):
    """R11(f) / R6(c) — what changes for callers who never pass --obsidian."""

    def test_plain_markdown_still_converts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "o.docx")
            proc = subprocess.run([
                "node", MD2DOCX,
                os.path.join(SKILL, "examples", "fixture-simple.md"), out],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(os.path.getsize(out) > 0)

    def test_unescaped_space_in_an_image_path_warns(self):
        # R6(c) — the D4 diagnostic, deliberately NOT gated on --obsidian.
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "my folder"))
            with open(os.path.join(tmp, "my folder", "p.png"), "wb") as fh:
                fh.write(b"\x89PNG\r\n")
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![a](my folder/p.png)\n")
            proc = subprocess.run(
                ["node", MD2DOCX, src, os.path.join(tmp, "o.docx")],
                capture_output=True, text=True)
            self.assertIn("unescaped spaces", proc.stderr)

    def test_angle_bracket_destination_does_not_warn(self):
        # R6(c) — the angle-bracket form DOES parse, so warning about it would be a
        # false positive on every document this skill itself generates.
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "my folder"))
            shutil.copy(os.path.join(VAULT, "_attachments", "diagram.png"),
                        os.path.join(tmp, "my folder", "p.png"))
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![a](<my folder/p.png>)\n")
            proc = subprocess.run(
                ["node", MD2DOCX, src, os.path.join(tmp, "o.docx")],
                capture_output=True, text=True)
            self.assertNotIn("unescaped spaces", proc.stderr)
            self.assertEqual(len(_media(os.path.join(tmp, "o.docx"))), 1)

    def test_alt_text_without_the_prefix_is_untouched(self):
        # R11(f) / R3(i) — the size-hint parse is a no-op for everyone else.
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(os.path.join(VAULT, "_attachments", "diagram.png"),
                        os.path.join(tmp, "d.png"))
            src = os.path.join(tmp, "n.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("# T\n\n![w=weight|chart](d.png)\n")
            out = os.path.join(tmp, "o.docx")
            proc = subprocess.run(["node", MD2DOCX, src, out],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            xml = _unzip(out)
            self.assertIn("w=weight|chart", xml)
            extents = [(int(a) // 9525, int(b) // 9525) for a, b in
                       re.findall(r'<wp:extent cx="(\d+)" cy="(\d+)"', xml)]
            self.assertIn((400, 300), extents)


if __name__ == "__main__":
    unittest.main()
