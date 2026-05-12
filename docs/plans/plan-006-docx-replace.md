# Development Plan: Task 006 — `docx_replace.py` (docx-6)

> **Status:** ✅ **MERGED 2026-05-12** (11-sub-task chain executed + VDD-Multi adversarial QA pass + post-VDD-Multi honest-scope recommendations applied). All 11 sub-tasks landed via Sarcasmotron Hallucination Convergence (only 006-04 required an iter-2 fix). See [`docs/reviews/task-006-plan-review.md`](reviews/task-006-plan-review.md) for the original round-1/round-2 plan-review and [`docs/TASK.md`](TASK.md) §11 Implementation Summary for delivery actuals.
>
> **Source documents:**
> - [`docs/TASK.md`](TASK.md) — Task 006, **DRAFT v2** APPROVED_WITH_COMMENTS ([`docs/reviews/task-006-review.md`](reviews/task-006-review.md)). RTM R1–R12 in §5; UC-1..UC-4 in §2; D1–D8 in §0; honest-scope §9 (§11.1–§11.4 aliases).
> - [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — **DRAFT v2** APPROVED ([`docs/reviews/task-006-architecture-review.md`](reviews/task-006-architecture-review.md)). F1–F8 functional regions; Q-A1..Q-A5 closed; atomic-chain skeleton in §11.
> - **Predecessor PLAN.md** (Task 005 / xlsx-3 / md_tables2xlsx) — current `docs/PLAN.md` superseded by this rewrite; xlsx-3 master at [`docs/tasks/task-005-md-tables2xlsx-master.md`](tasks/task-005-md-tables2xlsx-master.md).
> - **Predecessor PLAN.md** (Task 004 / xlsx-2 / json2xlsx) archived at [`docs/plans/plan-003-json2xlsx.md`](plans/plan-003-json2xlsx.md).
>
> **D5 closure (delivery shape):** **11 sub-tasks** — mirroring ARCH §11
> Atomic-Chain Skeleton (architecture-reviewer MAJ-2 split of 006-01 into
> 006-01a + 006-01b preserved; plan-review MIN-1 split of 006-07 into
> 006-07a + 006-07b added). Order: 3 scaffolding tasks (Stage 0 —
> 006-01a extraction-all-green + 006-01b Red test stubs + 006-02 helper
> tests Green), 4 logic tasks (Stage 1 — cross-cutting + 3 actions), 2
> CLI wiring tasks (Stage 1 close — 006-07a mandatory F7+F8 + 006-07b
> conditional UC-4 library mode), 1 honest-scope lock task (Stage 2),
> 1 finalization task (Stage 2 close).
>
> **Total LOC budget (architect-locked, ARCH §3.2):**
> ≤ **600 LOC** for `docx_replace.py` (guardrail: extract `_actions.py`
> sibling if exceeded) + ≤ **180 LOC** for `docx_anchor.py`. Test code:
> `test_docx_anchor.py` ≥ 20 unit tests (~ 300 LOC); `test_docx_replace.py`
> ≥ 30 unit tests (~ 500 LOC); `tests/test_e2e.sh` += ≥ 16 named cases
> (~ 250 LOC append). Plus fixture refresh (3 fixtures from `md2docx.js`
> + 1 markdown insert-source). `docx_add_comment.py` modification:
> -45 LOC (3 function bodies removed + 1 import line added; behaviour
> byte-identical).
>
> **Stub-First (Red → Green → Refactor) applied as REFACTOR-AHEAD pattern
> per architecture-reviewer MAJ-2:**
>
> - **Phase 1 (Stage 0 — Tasks 006-01a, 006-01b, 006-02):**
>   - **006-01a** is **all-green** (byte-identical refactor of
>     `docx_add_comment.py` ↔ new `docx_anchor.py`); no test stubs
>     introduced here so the G4 regression gate is evaluated on green
>     helpers only. This is the **PRE-Phase-1 step** that protects the
>     existing docx-1 test suite.
>   - **006-01b** is the canonical **Red state** — test stubs with
>     explicit `unittest.skip("docx-6 stub — task-006-NN")` and E2E
>     `echo SKIP T-<name>` markers; fixtures created; no production
>     code beyond the 006-01a refactor.
>   - **006-02** turns the **`test_docx_anchor.py`** subset **Green**
>     (≥ 20 unit tests passing on the extracted+new helpers — proves
>     refactor is complete and helpers are usable).
> - **Phase 2 (Stage 1 — Tasks 006-03 .. 006-07b):** Per-F-region
>   implementation in dependency order:
>   - 006-03 → F1 (cross-cutting pre-flight) + F2 (part walker stub) +
>     CLI skeleton (build_parser, main, _run with pre-flight only).
>     Cross-3 / cross-4 / cross-5 / cross-7 E2E cases turn green.
>   - 006-04 → F4 `_do_replace` (+ F2 full part-walker). UC-1 E2E
>     cases turn green.
>   - 006-05 → F5 `_do_insert_after`, `_materialise_md_source`,
>     `_extract_insert_paragraphs` + stdin `-` path. UC-2 E2E cases
>     turn green.
>   - 006-06 → F6 `_do_delete_paragraph` + `_safe_remove_paragraph`
>     (last-paragraph guard + empty-cell placeholder). UC-3 E2E
>     cases turn green.
>   - **006-07a → F7 full `_run` orchestrator + F8 post-validate hook
>     (MANDATORY).** R8.k output-extension preservation. Full
>     exit-code matrix tests. **No `--unpacked-dir`** (UC-4 lives in
>     006-07b). This is the load-bearing CLI-completion sub-task and
>     is required for MVP.
>   - **006-07b → `--unpacked-dir` library mode (UC-4, MVP=No per
>     R8.g — CONDITIONAL).** Ship only if cumulative
>     `docx_replace.py` LOC ≤ 560 after 006-07a (leaves headroom for
>     UC-4 ~ 30-40 LOC). Otherwise defer to follow-up backlog row
>     `docx-6.4` and document the deferral in 006-09.
> - **Phase 3 (Stage 2 — Tasks 006-08, 006-09):**
>   - 006-08 — Honest-scope regression locks R10.a–R10.e + Q-U1
>     tracked-change default + A4 TOCTOU symlink-race acceptance test.
>   - 006-09 — `SKILL.md` + `scripts/.AGENTS.md` + backlog row ✅ DONE
>     + `validate_skill.py` exit 0 + the **eleven (actual 12, see ARCH
>     §9 NIT n1 reconciliation)** `diff -q` cross-skill replication
>     checks silent.

---

## Task Execution Sequence

### Stage 0 — Refactor + Scaffolding (Phase 1: 006-01a all-green; 006-01b Red stubs; 006-02 helper tests Green)

- **[R6.a R6.b R6.c]** **Task 006-01a** — Extract `docx_anchor.py` from
  `docx_add_comment.py` (byte-identical move of `_is_simple_text_run`,
  `_rpr_key`, `_merge_adjacent_runs`); refactor `docx_add_comment.py`
  to `from docx_anchor import ...`. **No new test stubs; no behaviour
  change.** Existing docx-1 E2E suite passes unchanged (G4 gate).
  - **RTM coverage:** **R6.a** (extract `_is_simple_text_run` /
    `_rpr_key` / `_merge_adjacent_runs`), **R6.b** (`docx_add_comment.py`
    imports), **R6.c** (byte-identical behaviour).
  - **Description:** [`docs/tasks/task-006-01a-anchor-extraction.md`](tasks/task-006-01a-anchor-extraction.md)
  - **Locks:** Module-level function bodies in `docx_anchor.py` are
    **byte-identical** to source (verified via `diff` after extraction);
    new module ≤ 90 LOC at end of 006-01a (full ≤ 180 cap reached only
    after 006-02 adds `_replace_in_run` + `_concat_paragraph_text` +
    `_find_paragraphs_containing_anchor`).
  - **Priority:** Critical · **Dependencies:** none

- **[R11.a R11.b R11.c R11.d]** **Task 006-01b** — Red-state test
  scaffolding for the docx-6 chain: `test_docx_anchor.py` stubs
  (≥ 20 cases skipped); `test_docx_replace.py` stubs (≥ 30 cases
  skipped); `tests/test_e2e.sh` `# --- docx-6: docx_replace ---` block
  with ≥ 16 named `echo SKIP T-<name>` markers; 3 fixtures generated
  via `md2docx.js` from `.md` sources + 1 inline insert-source
  markdown file.
  - **RTM coverage:** **R11.a** (E2E ≥ 16 cases), **R11.b** (anchor
    unit tests ≥ 20), **R11.c** (replace unit tests ≥ 30), **R11.d**
    (fixtures derived from `md2docx.js`).
  - **Description:** [`docs/tasks/task-006-01b-test-scaffolding.md`](tasks/task-006-01b-test-scaffolding.md)
  - **Locks:** the 16 E2E case tags (see file); 4 unit-test classes
    in `test_docx_replace.py`; SKIP markers must keep
    `test_e2e.sh` exit-0 throughout Phase 1.
  - **Priority:** Critical · **Dependencies:** 006-01a

- **[R6.d R6.e R11.b]** **Task 006-02** — Implement new helpers in
  `docx_anchor.py` (`_replace_in_run`, `_concat_paragraph_text`,
  `_find_paragraphs_containing_anchor`); turn `test_docx_anchor.py`'s
  ≥ 20 unit cases GREEN. **End-state: `docx_anchor.py` ≤ 180 LOC;
  helper module is complete.**
  - **RTM coverage:** **R6.d** (`_find_paragraphs_containing_anchor`),
    **R6.e** (`_concat_paragraph_text`), **R11.b** (anchor unit tests
    green).
  - **Description:** [`docs/tasks/task-006-02-anchor-unit-tests.md`](tasks/task-006-02-anchor-unit-tests.md)
  - **Locks:** new helper signatures verbatim per ARCH §5 internal-
    signature block (kw-only `anchor_all` for `_replace_in_run`);
    Q-U1 default behaviour pinned at unit-test level
    (`_concat_paragraph_text` includes `<w:ins>` content, excludes
    `<w:del>` content); `_replace_in_run` cursor-loop matches
    `_wrap_anchors_in_paragraph` semantics (no infinite loop on empty
    replacement).
  - **Priority:** Critical · **Dependencies:** 006-01a, 006-01b

### Stage 1 — Logic Implementation (Phase 2: per-region Green)

- **[R7.a R7.b R7.c R7.d R7.e R7.f R2.h R8.h]** **Task 006-03** —
  Cross-cutting pre-flight (F1) + CLI skeleton (build_parser + main
  + _run with pre-flight only). Implements `_assert_distinct_paths`,
  `_read_stdin_capped`, `_tempdir`; wires `assert_not_encrypted`
  (cross-3), `warn_if_macros_will_be_dropped` (cross-4), cross-5
  `--json-errors` envelope; cross-7 same-path guard (symlink-aware).
  No action dispatch yet (Replace/Insert/Delete still
  `NotImplementedError`). Cross-cutting E2E cases turn GREEN.
  - **RTM coverage:** **R7.a** (cross-3 exit 3), **R7.b** (cross-4
    stderr warning), **R7.c** (cross-5 envelope), **R7.d** (cross-7
    same-path exit 6, symlink-aware), **R7.e** (`_errors.py` imported,
    not copied), **R7.f** (stdin `-` flag presence), **R2.h** (stdin
    size cap 16 MiB → `InsertSourceTooLarge`), **R8.h** (`--json-errors`).
  - **Description:** [`docs/tasks/task-006-03-cross-cutting.md`](tasks/task-006-03-cross-cutting.md)
  - **Locks:** `_assert_distinct_paths` uses `Path.resolve(strict=False)`
    (follows symlinks); `_read_stdin_capped` reads up to
    `16 * 1024 * 1024` bytes; argparse mutex-group registration
    deferred to 006-07a (CLI is "skeleton" here — flags exist but
    action dispatch raises `NotImplementedError`); `--unpacked-dir`
    parse-side recognition only (not yet routed).
  - **Priority:** Critical · **Dependencies:** 006-02

- **[R1.a R1.b R1.c R1.d R1.e R1.f R1.g R5.a R5.b R5.c R5.d R5.e R5.f R5.g]**
  **Task 006-04** — Part-walker (F2: `_iter_searchable_parts` with
  `[Content_Types].xml` authoritative enumeration + glob fallback)
  and `_do_replace` (F4). `--replace` action: cursor-loop multi-match
  within run (per docx-1 pattern), `<w:rPr>` preservation, empty-
  replacement allowed (D3), single-run honest scope (D6/B),
  `xml:space="preserve"` set when needed. UC-1 E2E cases turn GREEN.
  - **RTM coverage:** **R1.a** (in-place text swap), **R1.b**
    (preserve `<w:rPr>`), **R1.c** (first-match default), **R1.d**
    (cursor-loop multi-match), **R1.e** (empty replacement),
    **R1.f** (single-run honest scope), **R1.g**
    (`xml:space="preserve"`), **R5.a–R5.g** (anchor-search scope
    deterministic ordering: body → headers → footers → footnotes →
    endnotes, parts enumerated via Content_Types).
  - **Description:** [`docs/tasks/task-006-04-replace-action.md`](tasks/task-006-04-replace-action.md)
  - **Locks:** Part-walk order is the **only** deterministic order in
    v1 (TASK §11.1 — no `--scope=` flag); `_iter_searchable_parts`
    primary source = `[Content_Types].xml` `<Override>` entries with
    WordprocessingML content-types; filesystem-glob fallback only on
    Content_Types parse failure (emits stderr warning); first-match
    default (no `--all`) **returns after writing the first part that
    matched** (does NOT continue walking subsequent parts).
  - **Priority:** Critical · **Dependencies:** 006-03

- **[R2.a R2.b R2.c R2.d R2.e R2.f R2.g R2.h R10.b R10.e]** **Task 006-05** —
  `--insert-after` action (F5). Implements `_materialise_md_source`
  (subprocess `node md2docx.js IN OUT`, 60 s timeout, `shell=False`),
  `_extract_insert_paragraphs` (deep-clone `<w:p>` children, strip
  trailing `<w:sectPr>` per Q-A3, emit stderr warnings on `r:embed`/
  `r:id` per R10.b and on `<w:numId>` when base lacks
  `numbering.xml` per Q-A4 / R10.e), `_do_insert_after` (paragraph-
  level concat-text matching D6/B, `--all` produces N×duplication
  via `addnext`). Stdin `-` path via `_read_stdin_capped` (006-03)
  writes to `tempfile.NamedTemporaryFile(suffix=".md")` and passes to
  subprocess. UC-2 E2E cases turn GREEN.
  - **RTM coverage:** **R2.a** (md2docx subprocess), **R2.b** (unpack
    + extract body `<w:p>`), **R2.c** (strip trailing `<w:sectPr>`),
    **R2.d** (deep-clone after anchor `<w:p>`), **R2.e** (paragraph-
    level concat-text matching), **R2.f** (`--all` N×duplication),
    **R2.g** (stdin `-` support), **R2.h** (stdin size cap regression
    already covered in 006-03 — re-asserted on insert path here),
    **R10.b** (relationship-target warning), **R10.e** (`<w:numId>`
    survives + base-doc warning).
  - **Description:** [`docs/tasks/task-006-05-insert-after-action.md`](tasks/task-006-05-insert-after-action.md)
  - **Locks:** subprocess invocation is `subprocess.run(["node",
    str(scripts_dir / "md2docx.js"), str(md_path), str(insert_docx)],
    shell=False, timeout=60, capture_output=True, check=False)`; deep-
    clone uses `copy.deepcopy` on each `<w:p>` per match (NOT shared
    reference between matches when `--all`); `<w:sectPr>` filter uses
    `lxml.etree.QName(el).localname == "sectPr"` (Q-A3 lock).
  - **Priority:** Critical · **Dependencies:** 006-04

- **[R3.a R3.b R3.c R3.d R3.e R3.f R10.c R10.d]** **Task 006-06** —
  `--delete-paragraph` action (F6). Implements `_do_delete_paragraph`
  + `_safe_remove_paragraph` (refuse last-body-paragraph deletion →
  `LastParagraphCannotBeDeleted` exit 2; empty-cell placeholder
  `etree.Element(qn("w:p"))` per Q-A5; `<w:sectPr>` body-tail
  metadata is NOT counted as a paragraph). UC-3 E2E cases turn GREEN.
  - **RTM coverage:** **R3.a** (remove from parent), **R3.b**
    (paragraph-level concat-text matching), **R3.c** (`--all` removes
    every match), **R3.d** (last-body-paragraph refusal), **R3.e**
    (empty-cell placeholder), **R3.f** (preserve `<w:sectPr>` body-
    tail metadata), **R10.c** (last-paragraph regression lock),
    **R10.d** (`--all --delete-paragraph` last-paragraph guard wins
    even with common-word anchor).
  - **Description:** [`docs/tasks/task-006-06-delete-paragraph-action.md`](tasks/task-006-06-delete-paragraph-action.md)
  - **Locks:** "last paragraph in `<w:body>`" is computed as
    `len([c for c in body if etree.QName(c).localname == "p"])`
    (ignores `<w:sectPr>`); empty-cell placeholder is the **short
    form** `<w:p/>` (Q-A5 — uses `etree.Element(qn("w:p"))`); deletion
    iterates a **snapshot** of matches before mutating (no iterator
    invalidation on `--all`).
  - **Priority:** Critical · **Dependencies:** 006-04 (part-walker
    shared); independent of 006-05.

- **[R4.a R4.b R4.c R8.a R8.b R8.c R8.d R8.e R8.f R8.i R8.j R8.k R9.a R9.b R9.c R9.d]**
  **Task 006-07a** — CLI wiring (F7 full `_run` pipeline) + post-
  validate hook (F8). **MANDATORY MVP closure** for zip-mode happy
  paths. R8.k output-extension preservation. **No `--unpacked-dir`**
  in this task — UC-4 lives in 006-07b.
  - **RTM coverage:** **R4.a** (action mutex), **R4.b** (exit 2
    `UsageError`), **R4.c** (`--anchor` required), **R8.a** positional
    INPUT/OUTPUT, **R8.b** `--anchor TEXT`, **R8.c** `--replace TEXT`,
    **R8.d** `--insert-after PATH`, **R8.e** `--delete-paragraph`,
    **R8.f** `--all`, **R8.i** one-line stderr success log (D8),
    **R8.j** `--help` documents honest scope, **R8.k** output-
    extension preserved verbatim, **R9.a**
    `DOCX_REPLACE_POST_VALIDATE` env opt-in, **R9.b** validation
    failure → exit 7 + `unlink(output)`, **R9.c** subprocess env-
    override for hermetic tests, **R9.d** truthy allowlist
    `{1, true, yes, on}`.
  - **Description:** [`docs/tasks/task-006-07a-cli-and-post-validate.md`](tasks/task-006-07a-cli-and-post-validate.md)
  - **Locks:** `_run` dispatch order (ARCH §F7 step list MAJ-1 fix,
    minus the library-mode step deferred to 006-07b): cross-7, then
    cross-3/cross-4, then unpack, then action, then pack, then
    post-validate, then success summary; argparse mutually-exclusive
    group on `{--replace, --insert-after, --delete-paragraph}` with
    `required=True`; success summary uses `Path(args.output).name`
    for filename component; **560 LOC soft ceiling** for
    `docx_replace.py` end-state (headroom for 006-07b UC-4 ≥ 40 LOC);
    **600 LOC HARD ceiling** — if exceeded, **STOP** and extract
    `_actions.py` sibling before merging 006-07a.
  - **Priority:** Critical · **Dependencies:** 006-05, 006-06

- **[R8.g R4.b]** **Task 006-07b** — `--unpacked-dir` library mode
  (UC-4). **CONDITIONAL MVP=No per R8.g.** Lands only if cumulative
  `docx_replace.py` LOC after 006-07a is ≤ 560 (≥ 40 LOC headroom).
  Implements library-mode dispatch FIRST in `_run` (ARCH §F7 step 1
  MAJ-1 fix), `NotADocxTree` guard, skip cross-7/3/4 in library
  mode, no pack step. If LOC budget is exceeded by 006-07a, this
  task is **deferred** to follow-up backlog row `docx-6.4`
  (documented in 006-09).
  - **RTM coverage:** **R8.g** (`--unpacked-dir` library mode,
    MVP=No), **R4.b** (`UsageError` when `--unpacked-dir` combined
    with positional INPUT/OUTPUT).
  - **Description:** [`docs/tasks/task-006-07b-unpacked-dir.md`](tasks/task-006-07b-unpacked-dir.md)
  - **Locks:** Library-mode dispatch happens **first** in `_run`
    (before cross-7) per ARCH MAJ-1 fix; library-mode does NOT
    invoke `_assert_distinct_paths`, `assert_not_encrypted`, or
    `warn_if_macros_will_be_dropped` (caller owns the tree); library
    mode also skips `office.pack` and post-validate (no output file
    to validate).
  - **Priority:** High (conditional) · **Dependencies:** 006-07a

### Stage 2 — Honest-Scope Locks & Finalization

- **[R10.a R10.b R10.c R10.d R10.e]** **Task 006-08** — Honest-scope
  regression locks (R10.a–R10.e), Q-U1 tracked-change default lock
  (arch-review MIN-4), and **A4 TOCTOU symlink-race acceptance test**
  (arch-review MIN-2). These tests already have stubs from 006-01b;
  this task **upgrades them to live tests** that exercise the v1
  honest-scope boundary. No new production code unless a regression
  test reveals a behaviour gap (in which case the gap is escalated
  via a NEW plan-review round, NOT silently widened in 006-08).
  - **RTM coverage:** **R10.a** (`--replace` cross-run anchor →
    `AnchorNotFound`), **R10.b** (`--insert-after` image-bearing MD →
    stderr warning + no live `r:embed`), **R10.c** (last-paragraph
    refusal regression), **R10.d** (`--all --delete-paragraph` on
    common word does NOT empty body), **R10.e** (`<w:numId>` survives).
  - **Description:** [`docs/tasks/task-006-08-honest-scope-locks.md`](tasks/task-006-08-honest-scope-locks.md)
  - **Locks:** R10.a fixture uses an anchor that spans two different-
    rPr runs (must NOT match after `_merge_adjacent_runs`); R10.b
    fixture is generated by `md2docx.js` from a markdown source
    containing `![alt](image.png)` — the resulting `.docx` contains a
    relationship-bearing `<w:p>` that triggers the stderr warning and
    is inserted **without** copying the `word/media/` part; R10.d
    uses a fixture with anchor `the` matching every paragraph in body
    — first match removed without `--all`, exit 2
    `LastParagraphCannotBeDeleted` with `--all`; Q-U1 lock asserts
    `<w:ins>`-wrapped anchor matches; `<w:del>`-wrapped anchor does
    NOT match.
  - **Priority:** High · **Dependencies:** 006-07

- **[R12.a R12.b R12.c R12.d R12.e R12.f]** **Task 006-09** — Final
  docs + backlog + validator gates. Updates `SKILL.md` (docx skill;
  scripts-list row for `docx_replace.py` + new Red Flag if a
  v1-shipping behaviour diverges from the docx-1 cookbook),
  `scripts/.AGENTS.md` (docx-6 row), `docs/office-skills-backlog.md`
  (`docx-6` row → ✅ DONE with status line, LOC, test counts);
  re-runs `validate_skill.py skills/docx` (must exit 0); re-runs the
  **eleven (actual 12 — see ARCH §9 NIT n1 reconciliation)**
  `diff -q` cross-skill replication checks (must be silent); re-runs
  full `tests/test_e2e.sh` (must exit 0). **DoD checklist explicitly
  enumerates all 12 `diff -q` invocations to close the "eleven vs
  twelve" gap.**
  - **RTM coverage:** **R12.a** (`SKILL.md` row), **R12.b**
    (`scripts/.AGENTS.md` row), **R12.c** (backlog ✅ DONE), **R12.d**
    (`validate_skill.py` exit 0), **R12.e** (`test_e2e.sh` exit 0),
    **R12.f** (eleven/12 `diff -q` silent).
  - **Description:** [`docs/tasks/task-006-09-final-docs-and-backlog.md`](tasks/task-006-09-final-docs-and-backlog.md)
  - **Locks:** the **DoD reconciliation note** explicitly lists all
    12 invocations from CLAUDE.md §2 (3-skill OOXML `office/` ×2 +
    4-skill `_soffice.py` ×2 + 4-skill `_errors.py` ×3 + 4-skill
    `preview.py` ×3 + 3-skill `office_passwd.py` ×2 = 12); backlog
    update format mirrors xlsx-3's status-line cadence.
  - **Priority:** High · **Dependencies:** 006-08

---

## RTM Coverage Matrix

| RTM Row | Sub-feature scope | Closing task(s) |
| :---: | :--- | :---: |
| **R1** | `--replace` action (in-place swap, preserve rPr, first-match, cursor-loop, empty replacement, single-run honest scope, xml:space) | 006-02 (helpers green), 006-04 (action) |
| **R2** | `--insert-after` action (md2docx subprocess, unpack/extract body, strip sectPr, deep-clone after anchor, paragraph-level concat-text, --all, stdin, stdin cap) | 006-03 (stdin cap helper + size cap), 006-05 (full action) |
| **R3** | `--delete-paragraph` action (remove from parent, concat-text match, --all, last-paragraph refusal, empty-cell placeholder, sectPr preserved) | 006-06 |
| **R4** | Action mutex (exactly one of replace/insert/delete; --anchor required) | 006-07a (argparse mutex group); 006-07b (R4.b for `--unpacked-dir` mutex with INPUT/OUTPUT) |
| **R5** | Anchor-search scope (body + headers + footers + footnotes + endnotes; Content_Types enumeration; deterministic part-walk order) | 006-04 (`_iter_searchable_parts`) |
| **R6** | `docx_anchor.py` helpers — R6.a/b/c: extract `_is_simple_text_run` / `_rpr_key` / `_merge_adjacent_runs` + refactor `docx_add_comment.py` (byte-identical); R6.d/e: new helpers `_replace_in_run` / `_concat_paragraph_text` / `_find_paragraphs_containing_anchor` | 006-01a (R6.a/b/c extraction+refactor), 006-02 (R6.d/e new helpers + green tests) |
| **R7** | Cross-cutting parity (cross-3/4/5/7; `_errors.py` imported; stdin `-` flag) | 006-03 |
| **R8** | CLI surface (positional INPUT/OUTPUT; --anchor required; --replace/--insert-after/--delete-paragraph; --all; --unpacked-dir MVP=No; --json-errors; one-line stderr success; --help documents honest scope; output extension preserved) | 006-07a (R8.a-f, R8.i-k full CLI), 006-07b (R8.g `--unpacked-dir` conditional), 006-03 (R8.h `--json-errors` + `--help` skeleton) |
| **R9** | Output integrity (`DOCX_REPLACE_POST_VALIDATE` env opt-in; failure → exit 7 + unlink; subprocess env-override for hermetic tests; truthy allowlist) | 006-07a |
| **R10** | Honest-scope regression locks: cross-run anchor → `AnchorNotFound`; image-bearing insert → stderr warning + no live r:embed; last-paragraph refusal; --all --delete-paragraph on common word; `<w:numId>` survives | 006-08 (live regression locks); also: R10.b warning code in 006-05, R10.c/d guards in 006-06, R10.e warning code in 006-05 |
| **R11** | Testing scaffolding — R11.a E2E ≥ 16 cases; R11.b anchor unit ≥ 20; R11.c replace unit ≥ 30; R11.d fixtures from md2docx.js (no manually-crafted OOXML); **R11.e — N/A (docx-1 had none; declared not applicable in 006-01b)** | 006-01b (R11.a-d stubs; R11.e N/A declaration), 006-02 (R11.b anchor green), 006-04..07a (R11.a/c unit + E2E logic green) |
| **R12** | Docs & validators (SKILL.md row; .AGENTS.md row; backlog ✅ DONE; `validate_skill.py` exit 0; `test_e2e.sh` exit 0; eleven/12 `diff -q` silent) | 006-09 |

## Use Case Coverage

| Use Case | Closing task(s) |
| :--- | :--- |
| **UC-1** — Replace text inside a run (preserve formatting) | 006-04 (action body) + 006-07a (CLI wiring) |
| **UC-2** — Insert paragraph(s) after anchor's `<w:p>` | 006-05 (action body + md2docx subprocess) + 006-07a (CLI wiring) |
| **UC-3** — Delete the paragraph containing the anchor | 006-06 (action body) + 006-07a (CLI wiring) |
| **UC-4** — Library mode (`--unpacked-dir`) — **MVP=No** | 006-07b (CONDITIONAL — lands only if 006-07a leaves ≥ 40 LOC headroom; else deferred to follow-up backlog row `docx-6.4`) |

## Open-Question Closure Trail

| Question (source) | Closing task | Resolution lock |
| :--- | :---: | :--- |
| ARCH Q-A1 — Module split (single file vs package) | 006-01a + 006-07a/07b | Single file `docx_replace.py` ≤ 600 LOC; soft ceiling 560 after 006-07a; guardrail extract `_actions.py` if exceeded |
| ARCH Q-A2 — `docx_anchor.py` extraction timing | 006-01a | Ship in same atomic chain; 006-01a is byte-identical refactor, regression-guarded by docx-1 E2E |
| ARCH Q-A3 — `<w:sectPr>` stripping | 006-05 | Strip via `QName(el).localname == "sectPr"` filter unconditionally |
| ARCH Q-A4 — Numbering relocation | 006-05 (warning) + 006-08 (regression lock R10.e) | Warn-only (honest scope §11.4); v2 ticket `docx-6.5` |
| ARCH Q-A5 — Empty-cell placeholder | 006-06 | `etree.Element(qn("w:p"))` short-form (Q-A5 lock) |
| TASK Q-U1 — Tracked-changes behaviour | 006-02 (helper-level) + 006-08 (regression lock) | Default v1: match through `<w:ins>`; ignore `<w:del>` |
| TASK Q-U2 — Comment-range preservation | (documentation only) | `<w:commentRangeStart/End>` are run siblings; untouched by `<w:t>` rewrite |
| TASK Q-U3 — Per-part match-count reporting | (deferred to v2) | v1 single-line aggregate summary only |
| task-reviewer NIT n1 — eleven vs twelve `diff -q` | 006-09 | DoD checklist enumerates all 12; "eleven" label kept for narrative continuity, count reconciled in note |
| arch-reviewer MIN-2 — A4 TOCTOU regression lock | 006-08 | Test exercises resolve→open same-path even when source is symlink-rewritten between resolve() and open() |
| arch-reviewer MIN-3 — Part-walker enumeration source | 006-04 | Content_Types primary; filesystem glob fallback only on parse failure (stderr warning) |
| arch-reviewer MIN-4 — Q-U1 default behaviour lock | 006-02 (unit) + 006-08 (e2e) | `_concat_paragraph_text` includes `<w:ins>` content, excludes `<w:del>` content |
| arch-reviewer NIT-3 — R1.g `xml:space="preserve"` explicit test | 006-02 (helper unit) + 006-04 (e2e) | Set when result contains leading/trailing space or whitespace ≠ stripped form |
| plan-reviewer MIN-3 — Q-U1 fixture generation method | 006-08 | `scripts/tests/build_tracked_change_fixture.py` LibreOffice-headless round-trip; hand-crafted OOXML deviation from R11.d REJECTED. If LO automation proves impractical → escalate to plan-review round 2 (Word COM, or documented R11.d waiver). |

## Honest-Scope Carry-Forward (TASK §9 + ARCH §10)

The following limitations are **deliberately accepted in v1**. The
chain MUST NOT silently widen scope. If implementation work surfaces
a limitation as blocking, **stop and escalate** — open a new TASK
Open Question or a v2 backlog row (`docx-6.5`, `docx-6.6`, …):

- **§11.1** Part-walk ordering deterministic, NOT user-configurable
  (no `--scope=` flag in v1).
- **§11.2** `<w:sectPr>` stripped from MD-source body before splice
  (no `--carry-section-props` flag in v1).
- **§11.3** Inserted MD content: images/charts/OLE/SmartArt NOT
  relocated (R10.b lock; v2 ticket `docx-6.5`).
- **§11.4** Numbering definitions NOT relocated (R10.e lock; warn-only).
- **ARCH A1** No `--allow-empty-body` escape hatch (last-paragraph
  refusal is unconditional in v1).
- **ARCH A2** No relationship relocation in `--insert-after`.
- **ARCH A3** No scope filter (`--scope=body|all`).
- **ARCH A4** TOCTOU symlink race between `Path.resolve()` and file
  open (mirrors xlsx-2 ARCH §10 precedent).
- **ARCH A5** `--unpacked-dir` library mode (UC-4) is **MVP=No** (R8.g).

## Platform-IO Errors (envelope-only, NOT typed `_AppError`)

The typed `_AppError` taxonomy covers docx-6's logical error classes
(AnchorNotFound, EncryptedFileError, SelfOverwriteRefused,
Md2DocxFailed, Md2DocxOutputInvalid, Md2DocxNotAvailable,
EmptyInsertSource, InsertSourceTooLarge, LastParagraphCannotBeDeleted,
NotADocxTree, PostValidateFailed, UsageError). Platform-IO failures
(`FileNotFoundError`, generic `OSError` on read/write) are
**deliberately NOT** added to the taxonomy — they're caught at the
CLI layer in `_run` and surfaced via direct
`report_error(message, code=1, error_type="FileNotFound" | "IOError",
details={"path": ...})` calls. Same pattern as xlsx-3 PLAN.

## Phase-Boundary Gates

Between each task, the developer MUST verify:

1. **Validator gate:** `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/docx` exits 0.
2. **Cross-skill byte-identity gate (at each task boundary, i.e. after
   each `task-006-NN` lands and before the next begins — MIN-2 fix;
   NOT per-commit which would be impractical):** all **12** `diff -q`
   invocations from CLAUDE.md §2 silent (the chain consumes
   `office/` / `_soffice.py` / `_errors.py` / `preview.py` /
   `office_passwd.py` as read-only; none of them is modified in
   006-NN tasks). The DoD checklist in 006-09 enumerates the 12
   invocations explicitly. Mirrors Task-005 precedent cadence.
3. **Test gate:** `cd skills/docx/scripts && ./.venv/bin/python -m unittest discover -s tests` exits 0; `bash skills/docx/scripts/tests/test_e2e.sh` exits 0 (modulo the `DOCX6_STUBS_ENABLED` env flag — see MAJ-2 lock below).
4. **G4 regression gate (006-01a only — critical):** docx-1 E2E suite
   passes **unchanged** after the `docx_anchor.py` extraction. If
   ANY existing test fails, **STOP** and revert 006-01a.
5. **LOC ceiling gate (006-07a / 006-07b):** `wc -l
   skills/docx/scripts/docx_replace.py` ≤ 560 after 006-07a (soft;
   leaves ≥ 40 LOC headroom for 006-07b UC-4); ≤ 600 after 006-07b
   (HARD ceiling). If 006-07a exceeds 560, defer 006-07b to follow-up
   backlog row `docx-6.4`. If 006-07b would push past 600, extract
   `_actions.py` sibling **before** merging.
6. **Stub-First Red-state gate (MAJ-2 lock — 006-01b onward until each
   F-region lands):** unit-test stubs use `self.fail("docx-6 stub —
   to be implemented in task-006-NN")` (NOT `unittest.skip`) so the
   suite reports an observably failing test per Phase-2 deliverable.
   E2E stubs gated behind `DOCX6_STUBS_ENABLED` env flag: default
   unset → `echo SKIP` (suite stays exit-0 in CI); `DOCX6_STUBS_ENABLED=1`
   → expect-fail (run the case; `nok` if rc != expected). Phase-2
   sub-tasks flip individual `self.fail()` lines to real assertions
   as their region lands. The CI red bar SHRINKS monotonically.
7. **Session-state persistence:** `update_state.py` invoked at each
   task boundary (mode `VDD-Develop`, task
   `Task-006-docx-replace`, status `Task-NN-Done`).

## Acceptance Gates (TASK §7 ↔ closing task)

| Gate | Pass condition | Closing task |
| :---: | :--- | :---: |
| **G1** (Cross-cutting) | cross-3/4/5/7 all green for `docx_replace.py` | 006-03 |
| **G2** (RTM coverage) | All R1–R12 sub-features have ≥ 1 E2E or unit test (R11.e is N/A — declared in 006-01b) | 006-04..07a (logic), 006-02 (helpers), 006-08 (locks) |
| **G3** (Honest-scope locks) | R10.a–R10.e regression tests live (not skipped) | 006-08 |
| **G4** (Refactor) | `docx_add_comment.py` E2E suite passes unchanged after `docx_anchor.py` extraction | 006-01a |
| **G5** (Validator) | `validate_skill.py skills/docx` exit 0 | 006-09 |
| **G6** (Cross-skill drift) | All 11 (actual 12) `diff -q` parity checks silent | 006-09 (DoD enumeration) |
| **G7** (Backlog) | `docs/office-skills-backlog.md` row docx-6 marked ✅ DONE | 006-09 |
| **G8** (Docs) | `SKILL.md` + `scripts/.AGENTS.md` updated; `--help` documents honest scope | 006-07a (--help text) + 006-09 (SKILL.md / .AGENTS.md) |

---

**End of PLAN — Task 006 — `docx_replace.py` (✅ MERGED 2026-05-12 + VDD-Multi-hardened; see [`docs/TASK.md`](TASK.md) §11 for delivery actuals).**
