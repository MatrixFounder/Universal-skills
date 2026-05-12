# Task 006-08: Honest-scope regression locks + Q-U1 + A4 TOCTOU

## Use Case Connection
- **All UCs** — honest-scope locks enforce the v1 boundary across every UC.
- **G3 gate** — R10.a–R10.e regression tests live (not skipped).

## Task Goal

Upgrade the **honest-scope and arch-review regression stubs** from
skipped placeholders (created in 006-01b) to **live tests** that
exercise the v1 honest-scope boundary. No new production code unless
a regression test reveals a behaviour gap — in which case the gap is
escalated via a NEW plan-review round, NOT silently widened.

Required locks:
- **R10.a** — `--replace` cross-run anchor → `AnchorNotFound`.
- **R10.b** — `--insert-after` image-bearing MD source → stderr
  warning + inserted `<w:p>` contains no live `r:embed` (warn-and-
  proceed Alt-6).
- **R10.c** — `--delete-paragraph` last-body-paragraph refusal.
- **R10.d** — `--all --delete-paragraph` last-paragraph guard wins
  even with common-word anchor.
- **R10.e** — `<w:numId>` survives in inserted paragraphs; stderr
  warning when base doc lacks `numbering.xml`.
- **Q-U1 default behaviour** — `<w:ins>` content matches; `<w:del>`
  content does NOT match (arch-review MIN-4).
- **A4 TOCTOU symlink-race** — `_assert_distinct_paths` catches
  resolved-equal paths even when source symlink target is rewritten
  between `resolve()` and `open()` (arch-review MIN-2).

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/scripts/tests/test_docx_replace.py`

**`TestHonestScopeLocks` (≥ 7 cases, all live — no SKIPs):**

1. **`test_R10a_cross_run_anchor_returns_anchor_not_found`** —
   Fixture: a paragraph with two runs of different rPr where the
   anchor "May 2024" is split across them. After `_merge_adjacent_runs`,
   the runs remain separate (different rPr keys). `_do_replace` returns 0.
   `_run` raises `AnchorNotFound`; exit code 2. Cross-5 envelope
   includes `details["anchor"] == "May 2024"`.

2. **`test_R10b_image_bearing_md_emits_warning_and_no_live_embed`** —
   Use `docx_replace_insert_with_image.md` (contains `![](nonexistent.png)`).
   Invoke `--insert-after`. Capture stderr; assert it contains
   `"[docx_replace] WARNING: inserted body references relationships"`.
   Open the output `.docx`; assert no `<w:drawing>` with live
   `r:embed` attribute is present in the inserted paragraphs (either
   md2docx stripped it, or the relationship target is `None`/absent).
   Exit code 0 (warn-and-proceed).

3. **`test_R10c_last_body_paragraph_refused`** —
   Fixture: a `.docx` with exactly ONE paragraph in `<w:body>`
   (containing anchor "ONLY"). Invoke `--delete-paragraph --anchor "ONLY"`.
   Expect exit 2 `LastParagraphCannotBeDeleted`. Verify output file
   does NOT exist (pack() never reached).

4. **`test_R10d_all_delete_paragraph_common_word_trips_guard`** —
   Fixture: `docx_replace_body.docx` (every paragraph contains "the").
   Invoke `--all --delete-paragraph --anchor "the"`. Expect exit 2
   `LastParagraphCannotBeDeleted` (mid-loop trip when body shrinks to
   1 paragraph). Verify output file NOT created.

5. **`test_R10e_numid_survives_and_warns_when_base_lacks_numbering`** —
   Fixture: insert-source markdown with `1. list item` (produces
   `<w:numId>` in md2docx output). Base `.docx` deliberately has no
   `word/numbering.xml`. Invoke `--insert-after`. Capture stderr;
   assert it contains `"[docx_replace] WARNING: inserted body
   contains <w:numId>"`. Open output; verify `<w:numId>` is PRESENT
   (not stripped) in the inserted paragraph. Exit 0.

6. **`test_QU1_ins_content_matched`** —
   Fixture: paragraph with `<w:ins><w:r><w:t>FOO</w:t></w:r></w:ins>`.
   Invoke `--anchor "FOO" --replace "BAR"` OR `--delete-paragraph`
   (whichever exercises the locator). Expect match found; action
   executed. Verifies `_concat_paragraph_text` includes `<w:ins>`.

7. **`test_QU1_del_content_not_matched`** —
   Fixture: paragraph with `<w:del><w:r><w:t>FOO</w:t></w:r></w:del>`
   AND nothing else live. Invoke `--anchor "FOO" --delete-paragraph`.
   Expect exit 2 `AnchorNotFound`. Verifies `_concat_paragraph_text`
   excludes `<w:del>`.

8. **`test_A4_TOCTOU_symlink_resolve_equal_paths_caught`** —
   In tmp_path: create `real.docx`; create `alias.docx` as symlink
   to `real.docx`. Invoke `python3 docx_replace.py real.docx
   alias.docx --anchor x --replace y`. Even though the literal paths
   differ, `Path.resolve(strict=False)` normalises both to
   `real.docx`. Expect exit 6 `SelfOverwriteRefused`. Document the
   TOCTOU race acceptance: between `resolve()` and `open(input)`, a
   malicious actor could rewrite the symlink; we accept this v1
   limitation, but the same-path-via-symlink case in the
   happy-path is caught.

### Component Integration

These tests are pure-regression locks; they do NOT add production
code. If any of them fails, the failure indicates a **behavioural
drift** that requires escalation. Do NOT silently widen scope or
"fix" the test to make it pass.

## Test Cases

### End-to-end Tests

The E2E equivalents already exist from 006-04..07:
- `T-docx-replace-cross-run-anchor-fails` covers R10.a.
- `T-docx-insert-after-image-warns` covers R10.b.
- `T-docx-delete-paragraph-last-body-refused` covers R10.c.
- `T-docx-delete-paragraph-all-common-word` covers R10.d.

This task adds the **unit-test counterparts** in `test_docx_replace.py`
to ensure the locks are pinned at the function-level (not only via E2E).
Add 3 NEW E2E cases:

1. **TC-E2E-01 (T-docx-numid-survives-warning):** UC-2 with list-
   producing markdown + no-numbering base; stderr warning; exit 0;
   output contains `<w:numId>`.
2. **TC-E2E-02 (T-docx-ins-content-matches):** UC-1 or UC-3 against
   fixture with `<w:ins>FOO</w:ins>`; exit 0.
3. **TC-E2E-03 (T-docx-del-content-not-matched):** UC-3 against
   fixture with only `<w:del>FOO</w:del>`; exit 2 `AnchorNotFound`.

### Unit Tests

1. **TC-UNIT-01..08 (TestHonestScopeLocks):** All 8 cases above pass.

### Regression Tests

- All G4 + previous docx-6 tests still green.
- All 12 `diff -q` cross-skill replication checks silent.

## Acceptance Criteria

- [ ] All 8 `TestHonestScopeLocks` unit cases pass (no SKIPs).
- [ ] All 3 new E2E cases pass.
- [ ] R10.a–R10.e + Q-U1 + A4 TOCTOU each have ≥ 1 live test.
- [ ] No production code added in this task (all changes are tests).
- [ ] G4 regression: docx-1 E2E block passes unchanged.
- [ ] `validate_skill.py skills/docx` exits 0.
- [ ] All 12 `diff -q` cross-skill replication checks silent.
- [ ] Total E2E case count ≥ 23 (≥ 16 minimum from R11.a + 3 new from
      this task + several added in 006-07a post-validate; verify with
      `grep -c "^echo SKIP\|^echo OK\|^echo PASS" tests/test_e2e.sh`
      OR `grep -c "T-docx-" tests/test_e2e.sh`).
- [ ] Total `test_docx_replace.py` unit case count ≥ 35 (≥ 30 minimum
      from R11.c + 5+ from honest-scope class here).

## Notes

For `test_R10a_cross_run_anchor_returns_anchor_not_found`, the
fixture must produce a paragraph where `_merge_adjacent_runs` does
NOT coalesce the two runs (different rPr keys). The simplest source
is markdown like `**May** 2024` which generates
`<w:r><w:rPr><w:b/></w:rPr><w:t>May</w:t></w:r><w:r><w:t xml:space="preserve"> 2024</w:t></w:r>`
— the two runs have different rPr (`<w:b/>` vs empty), merge keeps
them separate.

For `test_R10b_image_bearing_md_emits_warning_and_no_live_embed`,
the key assertion is **both**:
1. stderr warning is emitted (the WARN code path runs);
2. The inserted `<w:p>` in the output does NOT have a live `r:embed`
   attribute referencing a relationship that exists in
   `word/_rels/document.xml.rels`.

If md2docx.js produces `<w:p>` WITHOUT an `r:embed` (text-only
fallback), assertion 2 is satisfied trivially. If md2docx.js does
produce a `<w:drawing>` with `r:embed`, the relationship target is
absent from `document.xml.rels` (we never copy it across) — Word will
render this as a "missing image" placeholder, which is honest-scope
acceptable.

For `test_A4_TOCTOU_symlink_resolve_equal_paths_caught`, the test
ONLY covers the happy-path same-path-via-symlink detection. The TOCTOU
race itself (symlink rewritten between `resolve()` and `open()`) is
NOT regression-tested — that requires a controlled filesystem race
harness and is documentation-only honest scope (mirrors xlsx-2 ARCH §10
precedent). The test docstring documents this acceptance explicitly.

For Q-U1 tests, the fixtures need `<w:ins>` / `<w:del>` wrappers that
`md2docx.js` does NOT produce. **Plan-review MIN-3 fix:** the
hand-crafted-OOXML deviation from R11.d is REJECTED. Instead,
generate the tracked-change fixture via a **LibreOffice round-trip
script** committed at:

`skills/docx/scripts/tests/build_tracked_change_fixture.py`

This is a small one-shot helper (≈ 50–80 LOC, NOT shipped in
production paths — lives under `tests/` so it's clearly a fixture-
build helper). The pipeline:

1. Start from an md2docx-generated baseline `.docx` (e.g. derived
   from `docx_replace_insert_source.md` which contains "FOO" inline).
2. Subprocess-invoke LibreOffice in headless mode with a small UNO
   automation (Python or `soffice --headless --convert-to`) that:
   - Enables tracked changes (`Document.setPropertyValue("RedlineProtectionKey", ...)` or `RecordChanges`).
   - Edits the body to insert/delete "FOO" so that `<w:ins>` /
     `<w:del>` wrappers appear in the resulting OOXML.
   - Disables tracking and saves as `.docx`.
3. Save outputs as `examples/docx_replace_tracked_ins.docx` and
   `examples/docx_replace_tracked_del.docx`.

The helper is invoked **once at fixture-build time**, NOT at every
test run (the resulting `.docx` files are committed; the helper is
re-invoked only if the fixtures need refreshing).

**Open Question Q-U1-build — fallback if LibreOffice UNO automation
proves impractical:** If the headless-LibreOffice round-trip cannot
reliably produce stable `<w:ins>` / `<w:del>` markup in CI (e.g. UNO
binding flakiness, LibreOffice version variance), **escalate** to the
Plan-Review round 2 with a proposal to either (a) use Microsoft Word
COM automation on a CI runner that has Word installed, or (b)
explicitly waive R11.d for this single corner-case in a documented
TASK amendment. **Do NOT** silently hand-craft the OOXML — that
breach of R11.d would be invisible to subsequent reviewers.

RTM coverage: **R10.a, R10.b, R10.c, R10.d, R10.e** + Q-U1 default lock + A4 TOCTOU acceptance lock.
