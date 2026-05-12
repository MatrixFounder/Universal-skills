# Task 008 — docx-6.5 + docx-6.6 — `--insert-after` Asset Relocators (Images + Numbering)

> **Backlog rows:**
> - `docx-6.5` (`docs/office-skills-backlog.md` line 172) — Image relocator
> - `docx-6.6` (`docs/office-skills-backlog.md` line 173) — Numbering relocator
>
> **Predecessor (MERGED, traceability anchor):** Task 006 — `docx-6` —
> `docx_replace.py` (✅ MERGED 2026-05-12). Task 006 §9 honest-scope items
> **R10.b** (image relocation) and **R10.e** (numbering relocation) are
> the two locks this task **breaks** (deliberately) by shipping v2
> relocators that close those gaps.
>
> **Pattern reference (MERGED, source of truth for relocator helpers):**
> `skills/docx/scripts/docx_merge.py` — `_copy_extra_media`,
> `_merge_relationships`, `_remap_rids_in_subtree`,
> `_merge_content_types_defaults`, `_merge_numbering`,
> `_ensure_numbering_part`, `_max_existing_rid`. These functions encode
> the multi-document relocation logic we re-use here, including the
> ECMA-376 §17.9.20 abstractNum-before-num ordering trap.
>
> **VDD Mode**: Verification-Driven Development. Decomposition into
> Epics → Issues with RTM + Acceptance Gates.

---

## 0. Meta Information

- **Task ID:** `008`
- **Slug:** `docx-replace-relocators`
- **Mode:** VDD (Verification-Driven Development)
- **Backlog effort (per row):**
  - `docx-6.5` = **M** (`~150–250 LOC + 5–8 E2E cases`)
  - `docx-6.6` = **M** (`~80–120 LOC + 4 E2E`)
  - Combined v1 LOC budget (architect to refine): ≤ 350 LOC of new
    relocator code + ≤ 200 LOC of test code.
- **Backlog value:**
  - `docx-6.5` = **M** (closes "image/chart loss on --insert-after" gap)
  - `docx-6.6` = **L** (closes "list rendering loss" gap)
- **License:** Proprietary (per `CLAUDE.md` §3 — `skills/docx/` is
  in the proprietary subset; new files inherit the docx skill's
  `LICENSE` / `NOTICE`).
- **Dependencies:** `docx-6` ✅ MERGED, `docx-6.5` precedes `docx-6.6`
  (Epic E2 reuses E1's rId-offset + content-types infra).

### 0.1. Decisions locked from session bootstrap (2026-05-12)

| D | Decision | Rationale |
|---|---|---|
| **D1** | Ship as a **single atomic chain** of sub-tasks (one TASK / one ARCHITECTURE / one PLAN), Epic E1 first then Epic E2. | E2 depends on E1's `_max_existing_rid` + content-types-defaults infra; bundling avoids two review cycles. Backlog row docx-6.6 explicitly lists docx-6.5 as a dependency. |
| **D2** | Introduce a **new docx-only sibling module `_relocator.py`** at `skills/docx/scripts/_relocator.py`, holding all image + numbering + content-types helpers. NOT placed under `office/` (cross-skill replication boundary preserved per `CLAUDE.md §2`). | `_actions.py` is already 431 LOC. Adding ~300 LOC of relocator logic to `_actions.py` would breach the same "single responsibility" rationale that drove the original 006-07a split. Sibling module mirrors `docx_anchor.py` precedent. |
| **D3** | Re-use the docx_merge.py functions **by copy, not import**. `_relocator.py` will contain its own implementations of `_copy_extra_media`, `_merge_relationships`, `_remap_rids_in_subtree`, `_merge_content_types_defaults`, `_merge_numbering`. Justified divergence: the docx-6 insert path operates on **one** insert tree (not N extras), so the "extra_index" parameter collapses and the prefix becomes `insert_` (fixed). | `docx_merge.py` is itself a complete CLI tool with a different file-layout invariant (output file + N input files); cross-importing into `_actions.py` creates a circular module-coupling we don't want. The duplicated LOC (~150) is an honest cost paid once. |
| **D4** | Order **mandatory**: Epic E1 (docx-6.5, image relocator) lands before Epic E2 (docx-6.6, numbering relocator). E2 inherits E1's `_max_existing_rid` + `_merge_content_types_defaults` directly via in-module call. | Bundles the shared rel-relocation infrastructure into one ship-able chunk. Plan-reviewer must reject any sub-task ordering that violates this. |
| **D5** | Both relocators are **always-on** for `--insert-after`. No `--no-relocate-images` or `--no-relocate-numbering` opt-out flag in v1. | Relocation is the **correct** behaviour; v1 of docx-6 emitted warnings precisely because relocation was not yet implemented. The R10.b / R10.e warnings are deleted, not made opt-in. |
| **D6** | Honest-scope items R10.b and R10.e (Task 006 §9) are **closed** (deleted from the catalogue). The stderr WARNING lines in `_actions.py:_extract_insert_paragraphs` are deleted. Regression-lock tests `T-docx-insert-after-image-warns` and `T-docx-numid-survives-warning` are **converted** to GREEN-path tests that verify successful relocation (rendered image survives + numId rebound to base-side numbering definition). | Honest-scope is about deliberate gaps; if the gap is closed the lock must go too — leaving a stale "WARNING: not relocated" line in code or a test that asserts the warning is emitted would be a lie about current behaviour. |
| **D7** | Chart parts (`chartN.xml` + `chartN.xml.rels`), OLE objects (`oleObject*`), and SmartArt diagrams (`diagrams/*`) are **in scope of E1** (backlog row 6.5 explicitly: "Включает images, charts, OLE objects, SmartArt diagrams"). The full `_MERGEABLE_REL_TYPES` set from `docx_merge.py` (image, hyperlink, diagramData, diagramLayout, diagramQuickStyle, diagramColors, chart, oleObject) is the v1 target set. | Backlog explicit. The honest scope of v2 becomes "supports all md2docx-produced relationship targets" (= the eight types above). |
| **D8** | Cross-3/4/5/7 contracts (encryption, macro warning, json-errors, self-overwrite) are **untouched** by this task. The exit-code matrix stays at {0,1,2,3,6,7}. No new exit codes are added. | Pure additive behaviour: relocation succeeds → exit 0 unchanged; relocation has nothing to relocate → exit 0 unchanged; relocation cannot proceed (malformed source) → exit 1 `Md2DocxOutputInvalid` (existing class, no new error type). |

---

## 1. General Description

### 1.1. Problem Statement

`docx_replace.py --insert-after PATH` in v1 (Task 006) materialises
the markdown source through a `md2docx.js` subprocess into a temporary
`.docx`, unpacks it, deep-clones the body's block-level children, and
splices those clones into the base document after the anchor paragraph.

**The lossy gap:** the deep-cloned `<w:p>` blocks carry references to
relationship-bearing assets that live in the **temporary insert tree**,
not in the base document:

- `<w:drawing>` blocks containing `<a:blip r:embed="rId7">` — the
  `rId7` resolves against the *insert tree*'s `word/_rels/document.xml.rels`,
  pointing to `word/media/image1.png` in the *insert tree*. Once spliced
  into the base, the `rId7` resolves against the **base**'s rels file
  — where `rId7` either does not exist (Word raises "couldn't read
  content") or, worse, points to an **unrelated asset** (silent
  corruption: an image is replaced by the base's logo).
- `<w:numId w:val="3">` — the `numId=3` resolves against the *insert
  tree*'s `word/numbering.xml`. Once spliced into the base, the `numId=3`
  resolves against the **base**'s `numbering.xml` (or nothing, if the
  base has no `numbering.xml`), so the list item renders as plain text
  (no bullet, no number, no indent).

v1 acknowledged the gap with two stderr WARNING lines and two
regression-lock tests (R10.b, R10.e). v2 closes the gap with full
asset relocation in the same `_extract_insert_paragraphs` / `_do_insert_after`
call-path.

### 1.2. Connection with the Existing System

| Touch point | What changes |
|---|---|
| `skills/docx/scripts/_actions.py` | `_extract_insert_paragraphs` signature **changes** (NOT just "widens"): today it is `_extract_insert_paragraphs(insert_tree_root: Path, *, base_has_numbering: bool) -> list[etree._Element]` (`_actions.py:255-312`). New surface (M2): `_extract_insert_paragraphs(insert_tree_root: Path, base_tree_root: Path) -> tuple[list[etree._Element], RelocationReport]` where the function **commits side-effects in place** before returning: writes `base/word/_rels/document.xml.rels`, `base/word/numbering.xml` (or installs it), `base/[Content_Types].xml`, and copies files into `base/word/media/` (+ optionally `base/word/charts/`, `base/word/embeddings/`, `base/word/diagrams/`). The `base_has_numbering` kwarg is removed (the relocator detects this internally). Caller `_do_insert_after` (`_actions.py:315-358`) is restructured: the relocator runs **once, before** the per-part walk; the per-part walk then writes only `document.xml` / `header*.xml` / etc. (the rels / numbering / CT files are already up-to-date). The two stderr WARNING lines are deleted. |
| `skills/docx/scripts/_relocator.py` **(NEW, docx-only)** | New module owning all eight functions for image + numbering + content-types relocation. ~250–350 LOC. |
| `skills/docx/scripts/docx_replace.py` | No CLI surface change. No new flags. `--help` text updated to remove the "image r:embed not wired" honest-scope phrase. Optionally adds one line in the success summary noting `N media file(s) / N abstractNum def(s) relocated` (Open Question Q-A2). |
| `skills/docx/scripts/tests/test_docx_replace.py` | Existing tests `test_extract_insert_paragraphs_emits_*_warning` are **rewritten** as `test_extract_relocates_image` and `test_extract_relocates_numbering` (GREEN-path equivalents) — NOT deleted, so the function-call coverage on `_extract_insert_paragraphs` is preserved on the new GREEN path. |
| `skills/docx/scripts/tests/test_docx_relocator.py` **(NEW)** | New unit-test module for `_relocator.py` (≥ 25 tests across the eight relocation functions + edge cases). |
| `skills/docx/scripts/tests/test_e2e.sh` | Tests `T-docx-insert-after-image-warns` (line 1969) and `T-docx-numid-survives-warning` (line 2239) are **rewritten**: they now assert the GREEN path (rendered image survives, numId rebound). Two **new** E2E cases added: `T-docx-insert-after-image-relocated` and `T-docx-insert-after-numbering-relocated`. |
| `docs/office-skills-backlog.md` | Rows `docx-6.5` and `docx-6.6` updated to `✅ DONE 2026-05-12`. |
| `skills/docx/SKILL.md` | "Honest scope (v1)" note in §`docx_replace.py` row revised: image + numbering relocation are now in scope; cross-run anchor remains out of scope (R10.a is untouched). |
| `skills/docx/scripts/.AGENTS.md` | docx-6.5 / docx-6.6 row added; LOC / test counts synced. |

### 1.3. Goal of Development

Close `docx-6` honest-scope items **R10.b** and **R10.e**: ship a
v2 `--insert-after` path that copies media files, appends relationships,
remaps `r:embed/r:link/r:id` references, copies abstractNum + num
definitions, and remaps `<w:numId>` references — so that an
`--insert-after` of a markdown source containing an image, chart, or
bulleted list produces a base document where the image renders, the
chart displays, and the bullets are bullets.

**Out of scope (preserved honest-scope items):**
- R10.a (cross-run anchor) — untouched.
- R10.c (last-paragraph deletion) — untouched.
- R10.d (`--all --delete-paragraph` blast-radius warning) — untouched.

#### 1.3.1. ARCH §10 honest-scope items — closure mapping (M1)

The current `docs/ARCHITECTURE.md` §10 Architecture-Layer honest-scope
catalogue has five items (A1–A5). This task touches them as follows:

| ARCH §10 item | Subject | This-task action |
|---|---|---|
| **A1** | No `--allow-empty-body` escape hatch | **Untouched.** Out of scope. |
| **A2** | No relationship relocation in `--insert-after` (v1) | **CLOSED by this task.** Image + chart + OLE + SmartArt rels relocated via Epic E1. |
| **A3** | ~~No scope filter~~ | **Already closed** by docx-6.7 (LIGHT task-007, 2026-05-12). No-op here. |
| **A4** | TOCTOU symlink race | **Untouched.** Out of scope. |
| **A5** | ~~`--unpacked-dir` library mode~~ | **Already shipped** (UC-4 in 006-07b). No-op here. |

The Architect handoff (§8) should phrase the change as "Close ARCH
§10 A2 (relationship relocation gap)" — that is the precise label.
Task-006 §9 row identifiers R10.b and R10.e are the **TASK-layer**
honest-scope catalogue; the corresponding ARCH-layer identifier is
just A2 (relationship + numbering are bundled architecturally under
"asset relocation" in ARCH §10).

---

## 2. List of Use Cases

### 2.1. UC-1 — `--insert-after` with an image in the markdown source

**Actor:** Agent (or CLI user)
**Preconditions:**
- Base `.docx` exists; anchor text is present in body.
- MD source contains `![alt](path/to/image.png)`, which `md2docx.js`
  resolves to a `<w:drawing>` with `<a:blip r:embed="rIdN">`.

**Main scenario:**
1. User invokes `docx_replace.py BASE.docx OUT.docx --anchor "TEXT" --insert-after src.md`.
2. `docx_replace.py` unpacks BASE.docx; materialises src.md via md2docx.js into a tmp tree.
3. `_extract_insert_paragraphs(base_tree, insert_tree)` is called.
4. Relocator copies `insert_tree/word/media/*` into `base_tree/word/media/` with prefix `insert_` (collision-safe).
5. Relocator computes `rid_offset = _max_existing_rid(base_rels) + 1`.
6. Relocator appends every mergeable-type Relationship from `insert_tree/word/_rels/document.xml.rels` to `base_tree/word/_rels/document.xml.rels`, with `Id` rewritten to `rId<offset+i>` and `Target` rewritten to the new media path.
7. Relocator walks each deep-cloned `<w:p>` from insert body and rewrites every `r:embed`/`r:link`/`r:id` attribute using the rId remap.
8. Relocator merges `<Default Extension>` entries from `insert_tree/[Content_Types].xml` into base's `[Content_Types].xml` (so .png/.jpeg/.svg MIME mappings exist).
9. The (now-rid-rewritten) `<w:p>` clones are spliced after the anchor.
10. Base tree is repacked; the output is written and validated.

**Postconditions:**
- Exit 0.
- Output `.docx` opens in Word/LibreOffice and the inserted image renders correctly.
- `office.validate` passes.
- Stderr success summary: `OUT.docx: inserted N paragraph(s) after anchor 'TEXT' (M match(es)) [relocated K media file(s)]`.
  *(Q-A2: whether to append the bracketed suffix is for the architect.)*

**Alternative scenarios:**
- **Alt-1a — no relationship-bearing assets:** insert body has zero `r:embed/r:link/r:id` references. Relocator is a no-op (zero media copied, zero rels appended). Behaviour identical to v1 minus the deleted warning. Exit 0.
- **Alt-1b — chart in MD source:** MD has a chart embedding (rare from md2docx but possible if MD contains an HTML `<img>` tag of a `.svg` chart). Relocator copies `chartN.xml` + `chartN.xml.rels` (chart parts have their OWN rels file — see §3.2 below for the recursive rel-copy spec). Exit 0.
- **Alt-1c — image filename collision:** insert tree has `media/image1.png` and base already has `media/image1.png`. Relocator names the destination using the fixed `insert_` prefix: first attempt `insert_image1.png`; if that collides → `insert_2_image1.png`; if that collides → `insert_3_image1.png`; etc. The counter `<n>` is the second-position integer; the `insert_` prefix is fixed (NOT parameterised) per Decision D3. Mirrors `docx_merge.py:172-176` counter-loop pattern, with `docx_merge`'s `extra<i>_` prefix collapsed to `insert_`. Exit 0.
- **Alt-1d — insert tree has `word/media/` but no rel pointing to it (orphan media):** relocator copies nothing for orphans (we copy only what's referenced via a `_MERGEABLE_REL_TYPES` relationship). Orphans are silently dropped. Exit 0.
- **Alt-1e — relocator encounters a malformed rels file** (e.g. corrupt XML): `Md2DocxOutputInvalid` raised, exit 1 (existing error class, no new code).

**Acceptance Criteria (Gherkin):**
```
Given a base .docx with anchor "Section 3:"
And a markdown source containing ![demo](logo.png)
When --insert-after src.md is invoked
Then the output .docx opens without "couldn't read content" errors
And the inserted paragraph contains a <w:drawing> whose r:embed resolves to base's word/media/insert_logo.png
And base/word/media/insert_logo.png is a byte-identical copy of insert/word/media/logo.png
And base/word/_rels/document.xml.rels contains a new Relationship of Type ".../relationships/image" with Target="media/insert_logo.png"
And no [docx_replace] WARNING lines are emitted to stderr.
```

---

### 2.2. UC-2 — `--insert-after` with a numbered/bulleted list in the markdown source

**Actor:** Agent (or CLI user)
**Preconditions:**
- Base `.docx` exists; anchor present.
- MD source contains `1. item` / `2. item` / `- bullet`, which md2docx
  resolves to `<w:p>` blocks with `<w:numPr><w:numId w:val="N"/></w:numPr>`.

**Main scenario:**
1. As UC-1 steps 1–3.
2. Relocator inspects insert tree's `word/numbering.xml`. If empty / missing, no-op. Otherwise:
3. If base has no `word/numbering.xml`: install insert's verbatim (copy file; ensure `[Content_Types].xml` Override + `word/_rels/document.xml.rels` Relationship for numbering — `_ensure_numbering_part` from docx_merge).
4. Otherwise: compute `anum_offset = max(base_abstractNumId) + 1`, `num_offset = max(base_numId) + 1`. Clone every `<w:abstractNum>` from insert numbering and re-insert into base numbering (preserving ECMA-376 §17.9.20 order: abstractNum-before-num — exactly the iter-2.3 trap from docx_merge.py:388-433). Clone every `<w:num>`, bump its `w:numId` by `num_offset` and its inner `<w:abstractNumId w:val>` by `anum_offset`. Build a `num_id_remap = {old_numId: new_numId}` map.
5. Walk each deep-cloned `<w:p>` and rewrite `<w:numId w:val>` references using `num_id_remap`.
6. Splice as UC-1.

**Postconditions:**
- Exit 0.
- Bulleted/numbered lists render with correct markers and indentation in the output `.docx`.
- `office.validate` passes.

**Alternative scenarios:**
- **Alt-2a — insert has list, base has no `numbering.xml`:** install insert's verbatim, ensure parts wired in (`_ensure_numbering_part` from docx_merge). Exit 0.
- **Alt-2b — insert has list, base has unrelated list:** offset-shift to avoid abstractNumId / numId collision. Exit 0.
- **Alt-2c — insert has no list, base has numbering.xml:** numbering relocator is a no-op (`saw_numid` flag from v1 stays the gate; just no warning). Exit 0.
- **Alt-2d — insert has list but `<w:abstractNum>` element has malformed (non-integer) `w:abstractNumId`:** skip that one element (mirrors docx_merge ValueError pass-through). The Other valid defs are still relocated. Exit 0.
- **Alt-2e — insert has `<w:num>` whose `<w:abstractNumId>` child is missing:** skip that one element. Exit 0.

**Acceptance Criteria (Gherkin):**
```
Given a base .docx with anchor "Section 3:" and an existing list using numId=1
And a markdown source containing "1. step one\n2. step two\n"
When --insert-after src.md is invoked
Then base/word/numbering.xml contains a new <w:abstractNum w:abstractNumId="N+1">
And base/word/numbering.xml contains a new <w:num w:numId="M+1"> whose <w:abstractNumId w:val> points at N+1
And the inserted <w:p> blocks reference <w:numId w:val="M+1">
And the output .docx opens with bullets/numbers rendered as bullets/numbers
And no [docx_replace] WARNING lines about numbering are emitted to stderr.
```

---

### 2.3. UC-3 — `--insert-after` with image + list combined (E1 + E2 integration)

**Actor:** Agent
**Preconditions:** As UC-1 and UC-2 combined.

**Main scenario:** Both relocators run sequentially in `_extract_insert_paragraphs`:
1. Image relocator (copies media, appends rels, rewrites rIds, merges content-types defaults).
2. Numbering relocator (copies abstractNum + num, rewrites numIds).
3. Clones spliced after anchor.

**Postconditions:**
- Exit 0.
- Output contains both rendered image AND a properly-numbered list.

**Acceptance Criteria:** UC-1 + UC-2 criteria simultaneously.

---

### 2.4. UC-4 — Backward-compatibility regression — `--insert-after` with plain text (no relationships)

**Actor:** Agent
**Preconditions:** MD source contains only `**bold**` + plain text (no images, no lists).

**Main scenario:** As Task 006 UC-2. Relocators are no-ops; splice path is byte-equivalent (modulo the absence of the deleted WARNING lines) to v1.

**Postconditions:** Exit 0. Output byte-equivalent to v1 except for the missing WARNING noise (and `[Content_Types].xml` may have additional `<Default>` entries if insert tree had any).

**Acceptance Criteria:** All existing Task 006 `T-docx-insert-after-*` cases (`-file`, `-stdin`, `-empty-stdin`, `-all-duplicates`) still pass unchanged.

---

## 3. Non-functional Requirements

### 3.1. Performance

- Relocator pass-cost dominated by media copy. Worst case: 16 MiB MD source × 8 embedded PNGs × 4 MiB each = ~32 MiB I/O. Target: < 500 ms relocator overhead on the 32-MiB worst case (excluding md2docx subprocess, which is dominated by Node startup).
- Memory: lxml parse of the eight relevant XML files (numbering, rels, content-types, ×2 for insert + base = ≤ 8 KiB each typical, ≤ 256 KiB pathological). No streaming required.

### 3.2. Security

- Same hardened XML parser used everywhere: `etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)`. The insert tree comes from md2docx.js which is trusted, BUT the relocator parses **base**'s rels / numbering / content-types — those are user-supplied. Mandatory `_SAFE_PARSER` reuse.
- Path traversal: media copy must reject any `Target` that starts with `/`, contains `..`, or resolves outside `word/media/` after `Path(target).resolve()`. (CWE-22.)
- ZIP-slip parity: media file writes use `Path.is_relative_to(base_dir)` check before `write_bytes`. Mirrors `office/unpack.py` precedent.

### 3.3. Validation Hook

- The optional `DOCX_REPLACE_POST_VALIDATE=1` env-var hook (Task 006 §3.3) keeps working. The output, post-relocation, must pass `office/validate.py`. This is the **gate** that catches numbering-XML order violations (ECMA-376 §17.9.20) and broken Relationship rIds — both errors documented as Schematron warnings in the existing validator. Sub-tasks that ship relocator code must run `DOCX_REPLACE_POST_VALIDATE=1 ./tests/test_e2e.sh` locally before merge.

### 3.4. Honest-Scope Documentation Requirement

- `--help` text in `docx_replace.py` REMOVES the line "image r:embed not wired" and the line about `<w:numId>` rendering as plain text.
- `--help` text MAY ADD a single line: `--insert-after: images, charts, OLE, SmartArt, numbered lists are relocated from MD source into the base document`.
- `SKILL.md`'s `docx_replace.py` row "Honest scope (v1)" sentence is reworded: only R10.a (cross-run anchor) remains. R10.b and R10.e are removed.
- `docs/office-skills-backlog.md` rows for `docx-6.5` and `docx-6.6` flipped to `✅ DONE 2026-05-12`.

### 3.5. Compatibility

- Output `.docx` opens correctly in: Word 2016+, LibreOffice 7.x, Pages, Google Docs (the four targets tested in Task 006 docx skill suite).
- Backward compat with Task 006: every Task 006 E2E case that does NOT involve images or lists must pass byte-for-byte (or with only the difference of missing WARNING noise on stderr).
- The relocator must be **idempotent** if invoked twice on the same base+insert pair: a second invocation must not append duplicate Relationships, must not copy media twice, must not duplicate abstractNum defs. **Note:** because the insert tree is a fresh tmp tree per md2docx subprocess call, idempotency is provided by the construction; we do NOT have to write idempotency-check logic into the relocator. But the unit-test suite SHOULD include one explicit "relocator-called-twice-on-same-base-with-fresh-clones-of-same-insert produces identical output" check (defensive regression lock).

---

## 4. Constraints & Assumptions

### 4.1. Technical Constraints

- **No new external dependencies.** lxml + python-docx (qn helper) only; same baseline as Task 006.
- **No imports across skill boundaries.** `_relocator.py` lives in `skills/docx/scripts/`, sibling to `_actions.py`. xlsx/pptx do not need it. `CLAUDE.md §2` invariants preserved.
- **No edits to `skills/docx/scripts/office/`** (the cross-3-skill shared OOXML helper) and no edits to `skills/docx/scripts/_soffice.py`, `_errors.py`, `preview.py`, `office_passwd.py` (the 4-skill / 3-skill replicated files). All twelve `diff -q` checks must remain silent.
- **No reimplementation of `office.unpack` / `office.pack`.** Relocator works on the in-memory unpacked tree only.
- **No use of `python-docx` high-level API.** Direct lxml.etree only.

### 4.2. Business Constraints

- Single-task chain to ship 6.5 + 6.6 atomically (Decision D1). No partial ship of "6.5 only".

### 4.3. Assumptions

- The md2docx.js subprocess always produces a `.docx` whose `word/_rels/document.xml.rels` exists. (Asserted; raise `Md2DocxOutputInvalid` otherwise.)
- `[Content_Types].xml` always exists in both base and insert trees. (Asserted; same error class.)
- The set of `_MERGEABLE_REL_TYPES` (image / hyperlink / diagramData / diagramLayout / diagramQuickStyle / diagramColors / chart / oleObject) is **complete** for v1. If md2docx ever produces a new relationship type, it falls through silently (rId not in rid_map → reference is left alone, mirroring docx_merge precedent). This is an intentional deferral, NOT a bug.
- Chart parts (`word/charts/chartN.xml` + `word/charts/_rels/chartN.xml.rels`) and OLE parts (`word/embeddings/oleObject*`) are copied **whole** when their root relationship is mergeable. The chart's own `chartN.xml.rels` is NOT recursively scanned in v1 — we copy it verbatim (its internal rIds reference the chart's local part, NOT base's `word/_rels/document.xml.rels`, so they stay valid as long as the chart part filename is preserved or renamed consistently). **Two independent media-copy paths interact here, and the distinction matters for N1 clarity:**
  - **Path 1 — image relocator:** scans `_MERGEABLE_REL_TYPES` rels in `insert/word/_rels/document.xml.rels`; for any rel of `Type` `.../image`, copies `insert/word/media/<file>` → `base/word/media/insert_<file>` (per R1/R3).
  - **Path 2 — chart-internal references:** a chart part's own `chartN.xml.rels` may reference further parts (typically `../media/imageN.png` if the chart embeds raster fills, or `../embeddings/...` for nested OLE). Because the chart's rels file is copied **verbatim**, those internal Targets remain literally `../media/imageN.png`. For that to resolve in base, the referenced media file must exist at base-side `word/media/imageN.png`. If the image was also referenced from `document.xml`, Path 1 already copied it (under the `insert_` prefix → the chart's `../media/imageN.png` literal will be **broken** in base). v1 accepts this as a v3 ticket; if observed in the single chart E2E case, the architect must downgrade or skip the case rather than expand v2 scope.
- *Honest-scope note H1 (§9):* complex multi-level diagrams with sub-rels pointing to OTHER parts (e.g. SmartArt `drawing.xml.rels` → `diagrams/data.xml.rels`) are tested in a single E2E case — if it surfaces a defect, that's a v3 ticket, not a blocker for v2 ship.

---

## 5. Requirements Traceability Matrix (RTM)

> **Epics (2) → Issues (15 total) → Sub-features (≥ 3 per issue). High granularity per VDD requirement.**

### Epic E1 — Image / Relationship Relocator (docx-6.5)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R1** | Media file copy with collision-safe prefix | Yes | (a) Scan `insert_tree/word/media/` for files; (b) Compute prefix = `"insert_"` (fixed; not parameterised); (c) On collision in `base/word/media/`, fall through to `insert_N_<name>` (counter loop); (d) Return `{old_relative_target: new_relative_target}` map; (e) Skip if `insert/word/media/` doesn't exist (graceful). |
| **R2** | Max-rId scan over base rels | Yes | (a) Parse `base/word/_rels/document.xml.rels`; (b) Iterate all `<Relationship Id="rIdN">`; (c) Extract integer N (regex `r"rId(\d+)$"`); (d) Return `max(N) + 0` (caller adds offset); (e) Return 0 if base rels file missing. |
| **R3** | Append mergeable relationships to base rels with offset | Yes | (a) Parse insert tree's rels file; (b) For each rel of Type ∈ `_MERGEABLE_REL_TYPES`: allocate fresh rId starting at `max_existing + 1`, increment with collision-skip; (c) Rewrite `Target` using media rename map (image rels only); (d) Preserve `TargetMode` if present; (e) Return `{old_extra_rid: new_base_rid}` map; (f) Drop rels of non-mergeable types silently; (g) **Path-traversal guard (M7):** reject any insert `Target` that starts with `/`, contains `..`, has a drive letter, or fails `Path("word").joinpath(target).resolve().is_relative_to(base_tree_root.resolve())` — raise `Md2DocxOutputInvalid` (exit 1). |
| **R3.5** | Copy non-media parts referenced by mergeable rels (M3) | Yes | (a) For Type ∈ {chart, oleObject, diagramData, diagramLayout, diagramQuickStyle, diagramColors}: read `Target` (relative to `word/_rels/document.xml.rels` parent = `word/`); (b) Copy the file `insert_tree/word/<target>` → `base_tree/word/<target>` (default path); (c) If a file already exists at that path in base: rename to `insert_<basename>` with the same prefix-counter loop as media (R1.c); rewrite the `Target` in the appended Relationship to match; (d) If the part has a sibling `_rels/<basename>.rels` file (e.g. `word/charts/_rels/chart1.xml.rels`): copy that sibling whole as well (verbatim — no recursive remap in v1, per D7 / Q-A4); (e) Apply R3 path-traversal guard (M7) to every Target before copying. |
| **R4** | Remap `r:embed/r:link/r:id` inside cloned `<w:p>` blocks | Yes | (a) Walk every subtree element; (b) For each of the seven `_RID_ATTRS` (embed, link, id, dm, lo, qs, cs): if attr value is in rid_map, rewrite; (c) Leave unmapped rIds alone (defensive); (d) Return rewrite count; (e) Idempotent on re-call. |
| **R5** | Merge `[Content_Types].xml` `<Default Extension>` entries | Yes | (a) Parse both content-types files; (b) Lowercase-compare extensions; (c) Append missing entries to base; (d) Preserve `ContentType` value as-is; (e) Persist only if changes made. |
| **R6** | Wire E1 relocator into `_extract_insert_paragraphs` | Yes | (a) Widen signature to accept `base_tree_root: Path`; (b) Run media copy + rels merge + rid remap + content-types merge BEFORE returning clones; (c) Delete the R10.b WARNING stderr line; (d) Update caller `_do_insert_after` to thread `base_tree_root`; (e) Update docstring. |
| **R7** | E1 unit tests | Yes | (a) `test_copy_extra_media_basic_collision`; (b) `test_copy_extra_media_no_media_dir`; (c) `test_max_existing_rid_*` (empty rels, single rId, gap-filled); (d) `test_merge_relationships_*` (mergeable types only, rid offset, target rewrite, drop non-mergeable); (e) `test_remap_rids_in_subtree_*` (embed, link, id, partial map); (f) `test_merge_content_types_defaults_*` (no-op, append, case-fold); ≥ 15 tests for E1 alone. |
| **R8** | E1 E2E test (T-docx-insert-after-image-relocated) | Yes | (a) Fixture: base.docx + src.md with `![](logo.png)`; (b) Run with no env hooks; (c) Assert exit 0; (d) Unpack output, verify `word/media/insert_logo.png` exists and is byte-identical to source; (e) Verify rels file has new Relationship entry; (f) Verify inserted `<w:p>` has rewritten r:embed. |

### Epic E2 — Numbering Relocator (docx-6.6)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R9** | Read insert tree numbering.xml | Yes | (a) Parse `insert/word/numbering.xml` if present; (b) Extract list of `<w:abstractNum>` and `<w:num>` elements; (c) Return `(0, [], [])` if file missing/empty; (d) Use `_SAFE_PARSER`. |
| **R10** | Compute abstractNumId / numId offsets from base | Yes | (a) Parse base `word/numbering.xml` if present; (b) Compute `anum_offset = max(base_abstractNumId) + 1`; (c) Compute `num_offset = max(base_numId) + 1`; (d) Return `(0, 0)` if base has no numbering; (e) Use `_SAFE_PARSER`. |
| **R11** | Clone + offset-shift abstractNum + num defs into base, preserving ECMA-376 §17.9.20 ordering | Yes | (a) Insert each cloned `<w:abstractNum>` at index `first_num_idx` (= before first existing `<w:num>`); (b) Insert each cloned `<w:num>` at index `num_insert_idx` (= after last existing `<w:num>`, before `<w:numIdMacAtCleanup>` if present); (c) Bump `w:abstractNumId` attr by `anum_offset`; (d) Bump `w:numId` attr and inner `<w:abstractNumId w:val>` by their respective offsets; (e) Return `{old_numId: new_numId}` remap. |
| **R12** | Install verbatim if base has no numbering.xml | Yes | (a) Detect missing base numbering; (b) Copy insert's `numbering.xml` to `base/word/numbering.xml`; (c) Call `_ensure_numbering_part` (adds Content-Types Override + word rels Relationship if missing); (d) Skip offset logic (no-op pass-through). |
| **R13** | Rewrite `<w:numId w:val>` inside cloned `<w:p>` blocks | Yes | (a) For each clone, iter `qn("w:numId")` elements; (b) If `w:val` is in remap, rewrite; (c) Leave unmapped vals alone (defensive); (d) Return rewrite count. |
| **R14** | Wire E2 relocator into `_extract_insert_paragraphs`, post-E1 | Yes | (a) Call E2 after E1 in same function; (b) Delete the R10.e WARNING stderr line; (c) Idempotent re-call check; (d) Update docstring. |
| **R15** | E2 unit + E2E tests | Yes | (a) `test_merge_numbering_no_base_install_verbatim`; (b) `test_merge_numbering_offset_shift`; (c) `test_merge_numbering_ecma_ordering` (ECMA-376 §17.9.20 regression lock); (d) `test_remap_numid_in_clone`; (e) E2E `T-docx-insert-after-numbering-relocated`; (f) E2E `T-docx-insert-after-image-and-numbering` (integration); ≥ 10 tests for E2 alone. |

**Total: 16 issues (R1–R8 + R3.5 + R9–R15), ≥ 80 sub-features (recount: R1=5, R2=5, R3=7, R3.5=5, R4=5, R5=5, R6=5, R7=6, R8=6, R9=4, R10=5, R11=5, R12=4, R13=4, R14=4, R15=6 = 81 letter-bullets), ≥ 25 new unit tests, ≥ 5 new E2E cases (image-relocated, numbering-relocated, image-and-numbering, path-traversal, plus rewritten warn-cases asserting GREEN), 2 rewritten E2E cases.**

---

## 6. Open Questions

### 6.1. For the Architect (Q-A1 … Q-A2) — MUST resolve before Planning

- **Q-A1 — Module placement:** Architect to ratify D2 (`_relocator.py` single docx-only sibling, ~300 LOC) or overturn with rationale (e.g. split into `_relocator_images.py` + `_relocator_numbering.py`).
- **Q-A2 — Success-summary annotation:** Should the stderr success line append `(relocated K media file(s), N abstractNum def(s))` or stay silent on relocation counts? Argument for: visibility / debuggability. Argument against: noise / breaks existing parsers that match the v1 success-line regex.

#### Ratification-only items (architect must confirm but should not need substantive deliberation)

- **Q-A3 (ratification of §3.5)** — One idempotency regression-lock test included. Architect to ratify (`_relocator.py` is constructed to be idempotent by the fresh-tmp-tree invariant; one defensive test is cheap).
- **Q-A4 (ratification of D7 + §4.3 Assumption)** — Chart `chartN.xml.rels` copied **verbatim**, NOT recursively scanned for sub-rel remapping. Architect to ratify (resolved by D7; the verbatim-copy stance is correct because the chart's internal rIds reference the chart's local part, not base's `document.xml.rels`).

### 6.2. For the User (non-blocking)

- **Q-U1 — Charts in md2docx:** does md2docx.js actually emit `chartN.xml` references from any Markdown input? If not, the chart-relocation branches are dead code in v1 (defensive only) — architect may downscope to image+numbering+OLE+SmartArt and drop chart-specific branches with a documented "no md2docx-produced chart input in v1" honest-scope note. *(Default proposal: keep chart-relocation branches because they're zero cost — the same `_MERGEABLE_REL_TYPES` filter handles them; deletion saves no LOC.)*
- **Q-U2 — Pages / Google Docs rendering:** if relocated images render in Word + LibreOffice but break in Pages or Google Docs, is that a v2 blocker or a v3 follow-up? *(Default proposal: v3. Pages / Google Docs are downstream consumers; OOXML conformance is the v2 contract.)*

---

## 7. Verification Plan (Acceptance Gates)

| Gate | Description | Pass condition |
|---|---|---|
| **G1** | All Task 006 E2E cases that don't touch images/lists pass unchanged (T-docx-insert-after-file, -stdin, -empty-stdin, -all-duplicates, -happy, -anchor-not-found, -cross-run-anchor-fails, -same-path, -encrypted, -macro-warning, -envelope-shape, -delete-paragraph-*, -scope-*). | `./tests/test_e2e.sh` exit 0 with **all existing T-docx-* cases passing**, EXCEPT the two cases being rewritten by Gate G5 (`T-docx-insert-after-image-warns` → now asserts GREEN path; `T-docx-numid-survives-warning` → now asserts GREEN path). Binary: 22 of 24 existing cases unchanged + 2 rewritten = 24 passing post-merge. |
| **G2** | New E2E case `T-docx-insert-after-image-relocated` green: inserted image renders, media file copied with `insert_` prefix, rels file has new Relationship. | E2E suite exits 0; assertions in §2.1 Postconditions hold. |
| **G3** | New E2E case `T-docx-insert-after-numbering-relocated` green: inserted list has bullets/numbers, abstractNum + num defs offset-shifted in base/word/numbering.xml. | E2E suite exits 0; assertions in §2.2 Postconditions hold. |
| **G4** | New E2E case `T-docx-insert-after-image-and-numbering` green: image + list both work in same invocation. | E2E suite exits 0; assertions in §2.3 hold. |
| **G5** | Rewritten E2E cases `T-docx-insert-after-image-warns` and `T-docx-numid-survives-warning` now assert GREEN-path relocation (no WARNING line; image / list survives). | E2E suite exits 0; both updated cases pass. |
| **G6** | Unit-test suite: `python3 -m unittest discover` exit 0; ≥ 25 new tests across `test_docx_relocator.py`; ≥ 100 total unit tests for docx-6 module incl. existing 108. | Local unittest run exits 0 with the new test count. |
| **G7** | Cross-skill replication boundary: all 12 `diff -q` invocations silent (CLAUDE.md §2). Breakdown: office/ tree `diff -qr` ×2 (docx→xlsx + docx→pptx) + `_soffice.py` ×2 (docx→xlsx + docx→pptx) + `_errors.py` ×3 (docx→xlsx + docx→pptx + docx→pdf) + `preview.py` ×3 (docx→xlsx + docx→pptx + docx→pdf) + `office_passwd.py` ×2 (docx→xlsx + docx→pptx) = **12 invocations**. | `bash` command from CLAUDE.md §2 produces zero output. |
| **G8** | `validate_skill.py skills/docx` exits 0. | Script exit code 0. |
| **G9** | Backlog rows docx-6.5 and docx-6.6 flipped to `✅ DONE 2026-05-12`. SKILL.md "Honest scope (v1)" line for `docx_replace.py` reworded. `scripts/.AGENTS.md` docx-6.5/6.6 row added. | git diff on the three files shows the expected updates. |
| **G10** | `DOCX_REPLACE_POST_VALIDATE=1 ./tests/test_e2e.sh` passes — the post-pack OOXML validator must accept the relocated numbering.xml (ECMA-376 §17.9.20 ordering trap is real; this gate catches it). | Hermetic env-var-on run exits 0. |
| **G11** | Path-traversal regression test (M7): a malformed insert rels file with `Target="../../etc/passwd"` (or `Target="/abs/path"`) causes `Md2DocxOutputInvalid` exit 1; no file is written outside `base_tree/word/`. | New E2E case `T-docx-insert-after-path-traversal` exits 1 with `Md2DocxOutputInvalid` envelope; no `etc/passwd` (or equivalent) byte appears on disk. |

---

## 8. Architecture Handoff Notes

The architect should:

1. **Confirm or refute Decisions D1–D8** in §0.1.
2. **Resolve Q-A1 (module placement)**, **Q-A2 (success-summary annotation)**, **Q-A3 (idempotency test)**, **Q-A4 (chart sub-rels recursion)** before Planning.
3. **Specify the function signatures of `_relocator.py`** — list of public functions with parameter and return types, mirroring the `docx_anchor.py` § "Internal (function signatures — locked surface)" precedent in ARCH §5.
4. **Update ARCH §11 Atomic-Chain Skeleton** to include the new sub-tasks for docx-6.5 + docx-6.6 (e.g. 008-01 through 008-NN).
5. **Update ARCH §9 Cross-Skill Replication Boundary** to add `_relocator.py` (NEW) to the "docx-only, no replication" list and confirm the eleven (twelve) `diff -q` checks are unchanged.
6. **Close R10.b and R10.e from ARCH §10 Architecture-Layer Honest-Scope** (or move them to the "closed by this task" section).
7. **Specify whether the relocator should emit per-asset count in the stderr success line (Q-A2)** with concrete format spec.

---

## 9. Honest-Scope Catalogue (v1 of this task)

The following items are deliberate gaps in v2; the planner / developer
must NOT widen them without an architect-level decision:

| # | Item | Why deferred to v3 |
|---|---|---|
| **H1** | Multi-level SmartArt sub-rels recursion. SmartArt parts with `drawing.xml.rels` → `diagrams/data.xml.rels` → media references. v2 copies parts verbatim; if md2docx ever produces this, an E2E case covers the typical path but pathological diagrams may have broken sub-refs. | md2docx.js produces simple inserts (images, lists, tables, headings); SmartArt is rare; the verbatim-copy approach is correct for 95% of cases. |
| **H2** | Hyperlinks (`r:id` on `<w:hyperlink>`) are mergeable per `_MERGEABLE_REL_TYPES` but external URLs (TargetMode="External") are uncommon in md2docx output. We carry the rel through; we do NOT validate the URL or rewrite anchor refs. | YAGNI. |
| **H3** | Fonts embedded in `word/fonts/` are NOT relocated. md2docx.js doesn't emit `word/fonts/`; if it ever does, fonts are silently dropped. | Out of backlog scope (6.5 says "images, charts, OLE objects, SmartArt diagrams"). |
| **H4** | The relocator does not deduplicate identical media (e.g. same PNG byte-string under two different filenames). Each unique filename is copied. | YAGNI; storage cost of duplicate media is negligible vs the engineering cost of byte-comparison logic. |
| **H5** | The relocator does not preserve insert tree's `<Override PartName>` entries (e.g. if insert tree has an `Override` for `/word/charts/chart1.xml`, we copy the chart part but do NOT add the Override). | If md2docx produces a part with a non-default content-type, the part will not render correctly in v2. v3 ticket: scan insert tree's Override list and merge new ones into base. |

---

## 10. References

- **Task 006** (`docs/tasks/task-006-docx-replace-master.md`) — v1 docx-6 specification (MERGED). Specifically §9 honest-scope catalogue rows R10.b and R10.e (the locks this task breaks).
- **Architecture 006** (`docs/ARCHITECTURE.md`) — §11.3 (relationship-target warning) and §11.4 (numbering-relocation warning) — both will be edited / removed in this task's architecture phase.
- **`skills/docx/scripts/docx_merge.py`** lines 109–544 — reference implementation for `_merge_styles`, `_copy_extra_media`, `_merge_relationships`, `_remap_rids_in_subtree`, `_merge_numbering`, `_ensure_numbering_part`, `_merge_content_types_defaults`. The new `_relocator.py` re-uses this pattern with the `insert_` prefix collapse (Decision D3).
- **ECMA-376 Part 1 §17.9.20** — `<w:abstractNum>` MUST precede `<w:num>`. The ordering trap is documented in `docx_merge.py:388-433` as the "iter-2.3 trap" (Word silent-repairs and rebinds list refs to the wrong abstract def if violated).
- **ECMA-376 Part 1 §17.18.4** — `<w:numId>` references resolve against `word/numbering.xml`; missing-numbering = plain-text render.
- **ECMA-376 Part 2 §9** — OOXML Relationship structure; rId allocation and Target path resolution rules.
- **`docs/office-skills-backlog.md` lines 172, 173** — the backlog rows being closed by this task.
- **`CLAUDE.md §2`** — cross-skill replication invariants (twelve `diff -q` checks).

---

## 11. Implementation Summary (post-merge actuals, 2026-05-12)

> **Status:** ✅ **MERGED + VDD-Multi hardened.** All 8 sub-tasks
> 008-01a..008-08 executed via `/vdd-develop-all` auto-continue; final
> hardening pass via `/vdd-multi` adversarial review (3 critics × 2
> iterations, terminal verdict PASS / clean-pass).

### 11.1. Chain delivered

| Sub-task | Scope | Status |
|---|---|---|
| 008-01a | `_relocator.py` skeleton + `RelocationReport` + 49 test stubs + AST-walk D3 lock | ✅ DONE |
| 008-01b | F16 `_assert_safe_target` (CWE-22) | ✅ DONE |
| 008-02 | E1 core: F10 + F11 + F12 + R4 + R5 (20 tests) | ✅ DONE |
| 008-03 | R3.5 non-media part copy: F13 + 2 helpers (9 tests) | ✅ DONE |
| 008-04 | `_extract_insert_paragraphs` signature change + E1 wiring + R10.b WARNING delete + Q-A2 success-line | ✅ DONE |
| 008-05 | E2 core: F14 + F15 + `_ensure_numbering_part` (12 tests; ECMA-376 §17.9.20 regression-lock) | ✅ DONE |
| 008-06 | E2 wiring + R10.e WARNING delete + 3 new/rewritten E2E cases | ✅ DONE |
| 008-07 | G11 path-traversal E2E + Q-A3 idempotency + ARCH §12.3.1 invariant tests | ✅ DONE |
| 008-08 | SKILL.md + backlog + .AGENTS.md + ARCH §9 NIT n1 (eleven→12) + `--help` reword | ✅ DONE |

### 11.2. VDD-Multi adversarial review (post-merge, 2 iterations)

**Iteration 1** (3 critics in parallel): 5 HIGH + 2 MED real findings:

| Finding | Domain | Fix locus |
|---|---|---|
| F14 cleanup-only base case: abstractNums appended AFTER `<w:numIdMacAtCleanup>` (ECMA-376 §17.9.20 violation) | Logic C-2 | `_relocator.py` two-branch insertion sites |
| F14 `etree.fromstring(etree.tostring(...))` used DEFAULT parser → XXE defence-in-depth gap | Security M2 + Performance H1 (escalated) | Both calls pass `_SAFE_PARSER` |
| F14 partial-skip left dangling `<w:abstractNumId w:val>` refs to skipped insert defs | Logic H-4 | `_is_int` + `skipped_insert_anum_ids` + `insert_anum_ids_valid` pre-validation |
| F10 never called `_assert_safe_target`; could follow symlinks via `iterdir()` filenames | Security H1 | F10 + F13 reject `src.is_symlink()`; F10 calls `_assert_safe_target` on `src.name` |
| F16 URL-encoded `%2e%2e/` bypassed `..` check (Word URL-decodes rels Target per ECMA-376 Part 2 §9.2) | Logic H-2 | `urllib.parse.unquote` + double-pass syntactic checks |
| F14 no size cap → 500k abstractNum DoS via OOM | Security H2 | 8 MiB cap with `reason="numbering_size_cap"` |
| E2E `T-docx-insert-after-numbering-relocated` exercised verbatim-install branch only | Logic M-2 | Test rewritten to pre-stamp base numbering.xml; asserts offset-shift, base survival, clone numId intersection, ECMA-376 ordering |

**6 new regression-locks** added to `TestVddMultiHardening`:
`test_cleanup_only_base_preserves_ordering`,
`test_num_pointing_at_skipped_abstractnum_is_dropped`,
`test_assert_safe_target_rejects_url_encoded_parent`,
`test_assert_safe_target_rejects_url_encoded_absolute`,
`test_copy_extra_media_rejects_symlinks`,
`test_merge_numbering_rejects_oversized_input`.

**Iteration 2**: all 3 critics converge `clean-pass`. Cosmetic nits
applied (L-3 stale "5 MiB"→"8 MiB", P1 `stat()` cache, P3 hoisted
`unquote` import). Logic critic: 4 LOW edge-cases declined. Security
critic: hostile probes (double-encoding `%252e`, unicode fullwidth dots,
TOCTOU, dense-XML, External case-sensitivity) all caught by canonical
filesystem semantics. Performance critic: 0 regressions; H1 deepcopy-vs-
roundtrip trade-off accepted (security-first).

### 11.3. Production code (final LOC)

| File | LOC | Cap | Notes |
|---|---:|---:|---|
| `_relocator.py` | **839** | ≤ 900 | F9 + F10–F13 + helpers + F14 + F15 + `_ensure_numbering_part` + F16. Q-A1 cap raised 500→900 post-vdd-multi (ARCH §12.1 D2). Final +58 LOC over initial 781 estimate: 6 vdd-multi hardening blocks (cleanup-only branch, `_is_int` helper, `skipped_insert_anum_ids` tracking, URL-decode double-pass in F16, symlink guards in F10/F13, size cap with cached `stat()`). |
| `_actions.py` | 412 | ≤ 600 | `_extract_insert_paragraphs` signature widened; R10.b + R10.e WARNINGs deleted. |
| `docx_replace.py` | 506 | ≤ 600 | Q-A2 success-line annotation wired. |
| `test_docx_relocator.py` | 1278 | — | 49 LIVE tests + 6 `TestVddMultiHardening` regression-locks. |
| **Total docx-008 delta** | **~860 prod + ~1280 tests** | — | New `_relocator.py` 839 + `_actions.py` net 0 + `docx_replace.py` +6 + new test file 1278. |

### 11.4. Test surface

- **Unit tests:** 166 total / 0 failures / 9 skipped (8 pre-existing + 1 retired `test_numid_survives_replace` documented R10.e replacement).
- **49 new** in `test_docx_relocator.py` (43 LIVE from 008-01a..008-07 + 6 from `TestVddMultiHardening` regression-locks).
- **+2 rewritten** R10.b/R10.e tests + **2 `TestPathTraversal`** tests in `test_docx_replace.py`.
- **E2E suite:** 151 cases / 0 failed; +4 new (image-relocated, numbering-relocated, image-and-numbering integration, path-traversal G11) + 2 rewritten (image-warns, numid-survives-warning → GREEN-path).
- **POST_VALIDATE=1 hermetic run:** 151/0 (G10).
- **Cross-skill `diff -q` (12 invocations):** all silent.
- **`validate_skill.py skills/docx`:** ✅ PASSED.

### 11.5. Honest-scope catalogue (after this task)

- **R10.a** (cross-run anchor) — preserved.
- **R10.b** (image relocation) — **CLOSED** by 008-04.
- **R10.c** (last-paragraph deletion) — preserved.
- **R10.d** (`--all --delete-paragraph` blast radius) — preserved.
- **R10.e** (numbering relocation) — **CLOSED** by 008-06.
- **ARCH §10 A2** — **CLOSED** by §12.
- **TASK §9 H1–H5** — v3 deferrals (multi-level SmartArt sub-rels, hyperlink validation, embedded fonts, media dedup, insert `<Override>` parts).

### 11.6. Decisions delivered as-specified

D1–D8 ratified and honored without deviation. Q-A1 (single sibling)
ratified with LOC cap raised 500→800 post-merge per Sarcasmotron MIN-1
(docx-008 chain) — rationale: D3 by-copy port of 13 docx_merge functions
is honestly larger than the initial estimate; numbering merge alone is
~140 LOC. Q-A2 (success-line annotation) shipped with zero-suppression
back-compat. Q-A3 (idempotency test) shipped with weaker-invariant
documentation. Q-A4 (chart sub-rels verbatim, no recursive remap)
shipped per D7.

### 11.7. Reviews record

- `/vdd-start-feature` task-review (round 1): APPROVED WITH COMMENTS;
  8 MAJOR + 4 minor fixed inline.
- `/vdd-start-feature` architecture-review (round 1): APPROVED WITH
  COMMENTS; 4 MAJOR + 4 minor fixed inline.
- `/vdd-plan` plan-review (round 1): APPROVED; 1 MAJOR (G11 placement
  → two-layer shell+unit) + 4 NIT fixed inline.
- `/vdd-develop` per-sub-task Sarcasmotron reviews (008-01a, 008-01b):
  APPROVED via Hallucination Convergence (0 CRIT/MAJ + minor inline fixes).
- `/vdd-develop-all` end-of-chain Sarcasmotron review: APPROVED via
  Hallucination Convergence; only MIN-1 LOC overrun (resolved by Q-A1
  cap raise).
- `/vdd-multi` 3-critic adversarial review (2 iterations): 5 HIGH + 2
  MED real findings in iter-1, all fixed; iter-2 all critics
  clean-pass. See §11.2.

---

**End of TASK: docx-008 — docx-6.5 + docx-6.6 — `--insert-after` Asset Relocators (✅ MERGED + VDD-Multi hardened 2026-05-12).**
