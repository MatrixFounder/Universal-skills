# OOXML comments and threads in `xlsx_add_comment.py`

> Reference doc for the data model behind
> [`scripts/xlsx_add_comment.py`](../scripts/xlsx_add_comment.py). The
> CLI itself is fully documented in its module docstring; this file
> explains *why* the OOXML edits happen the way they do, what
> traps lurk in the format, and which v1 limitations are locked in by
> the regression suite.

## 1. Part graph and reference use-case

**Reference use-case** (from
[`docs/office-skills-backlog.md`](../../../docs/office-skills-backlog.md)
line 191, xlsx-6 row, Notes column — Russian original preserved
verbatim per TASK round-1 m7 lock):

> «validation-агент (xlsx-7 pipe) расставляет замечания на проблемные
> ячейки timesheet/budget/CRM-export»

English gloss: an automated validation agent runs `xlsx_check_rules.py`
(xlsx-7) to produce a JSON envelope of findings, pipes that envelope
through `xlsx_add_comment.py --batch -`, and the result is a workbook
where every problematic cell carries a human-readable comment that an
auditor can triage in Excel cell-by-cell. xlsx-6 + xlsx-7 together
close the "timesheet/budget review" loop end to end.

The OOXML parts xlsx-6 touches:

- `xl/comments<N>.xml` — legacy comments part. ECMA-376 §18.7.1.
  Bound to one sheet via that sheet's rels file.
- `xl/threadedComments<M>.xml` — Excel-365 modern threaded comments,
  optional. Bound to one sheet via that sheet's rels file.
- `xl/persons/personList.xml` — Excel-365 author registry, **workbook-
  scoped** (rel goes on `xl/_rels/workbook.xml.rels`, NOT on a sheet
  rels file — see §3.3 below).
- `xl/drawings/vmlDrawing<K>.xml` — VML shapes for legacy-comment
  hover bubbles (without VML, Excel does not render the yellow
  callout). Bound to one sheet via that sheet's rels file.
- `[Content_Types].xml` — gains an `<Override>` entry per new part.
- Per-sheet `xl/_rels/sheet<S>.xml.rels` — gains `Relationship`
  entries for the parts above except `personList`.

The full ER diagram (with multiplicity) lives in
[`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md) §4.1.

## 2. Cell-syntax (`--cell`) reference

Form table:

| Form | Resolves to |
|---|---|
| `A5` | `(first-VISIBLE sheet, A5)` — workbook order, skipping `state="hidden"` and `state="veryHidden"` (M2). |
| `Sheet2!B5` | `(Sheet2, B5)`. Case-sensitive sheet-name match (M3) — `sheet2` does NOT match `Sheet2`. |
| `'Q1 2026'!A1` | `(Q1 2026, A1)` — single-quoted sheet name; whitespace allowed inside the quotes. |
| `'Bob''s Sheet'!A1` | `(Bob's Sheet, A1)` — apostrophe escape `''` → `'` (mirrors A1-formula apostrophe convention). |

**Resolution semantics** (lock-bearing):

1. Parse `--cell` value into `(sheet_name | None, cell_ref)`.
2. If sheet is unqualified (`None`), pick the first sheet where
   `state` is unset or equals `"visible"` — i.e. **first VISIBLE sheet,
   not first sheet**. Workbooks with a hidden Sheet1 land the comment on
   the next visible sheet, NOT on the hidden one (silent-hide trap).
3. If no visible sheet exists → exit 2 `NoVisibleSheet`.
4. Cell-ref is uppercased and `$`-stripped (`$A$5` → `A5`); sheet name
   is preserved verbatim.

The grammar locks live in
[`tests/test_xlsx_add_comment.py::TestCellParser`](../scripts/tests/test_xlsx_add_comment.py)
(parser unit tests) and `T-apostrophe-sheet` /
`T-hidden-first-sheet` E2E (real-fixture round-trips).

## 3. Pitfalls (the C1 + M-1 + M6 list)

> The following four traps are why this script exists as a separate
> CLI rather than a one-liner over openpyxl. Each was a real bug
> caught during the task / architecture review rounds; the
> regression tests in
> [`tests/test_xlsx_add_comment.py`](../scripts/tests/test_xlsx_add_comment.py)
> exist specifically to keep them caught.

### 3.1 `<o:idmap data>` is a comma-separated LIST, not a scalar (M-1)

ECMA-376 / VML 1.0 specifies the `data` attribute of
`<o:idmap data="...">` (which lives at the root of a `vmlDrawing*.xml`
file inside `<o:shapelayout>`) as a **comma-separated list of integer
shape-type IDs claimed by the drawing**.

A naive scalar parse silently corrupts heavily-edited workbooks where
Excel emitted multi-claim lists. Concrete failure mode: a workbook with

```xml
<o:idmap v:ext="edit" data="1,5,9"/>
```

means this single drawing already claims integers 1, 5, AND 9. A
scalar parse that reads only `"1"` will allocate `2` for the next new
VML part — colliding with the existing claim on `5`, which Excel then
silently re-renumbers on its next save, breaking shape→cell binding.

**The scanner MUST parse the full list:**
`[int(x) for x in attr.split(",") if x.strip()]`. The regression test
that locks this is
[`TestIdmapScanner::test_list_data_attr_returns_all_integers`](../scripts/tests/test_xlsx_add_comment.py).

### 3.2 `<o:idmap data>` and `o:spid` are TWO different collision domains (C1)

These two attributes look similar but live at different scopes:

- `<o:idmap data>` integers must be **workbook-wide unique across
  every `vmlDrawing<K>.xml` part**. Each VML drawing claims a set of
  shape-type IDs; no two drawings may claim the same integer. The
  scanner unions all `data` lists across all VML parts.
- `<v:shape id="_x0000_sNNNN" o:spid="...">` integers must be
  **workbook-wide unique across every `<v:shape>`**. Each individual
  shape gets its own NNNN, regardless of which drawing it lives in.
  Mirrors Excel's own `_x0000_s1025`-then-`_x0000_s1026` allocator.

**They are NOT the same collision domain.** Conflating them was the
round-1 task-review mistake (C1) — saying things like *"no two shapes
share `o:idmap`"* is structurally meaningless because shapes don't
have `o:idmap`, drawings do; and saying *"`o:idmap` workbook-wide
unique"* without the list-parsing caveat is wrong as covered in §3.1.

### 3.3 `personList` is workbook-scoped, NOT sheet-scoped (M6)

When `--threaded` is set, `xlsx_add_comment.py` emits two new parts:

- `xl/threadedComments<M>.xml` — referenced from the **sheet's** rels
  file (`xl/_rels/sheet<S>.xml.rels`).
- `xl/persons/personList.xml` — referenced from the **workbook's** rels
  file (`xl/_rels/workbook.xml.rels`).

Both are required for Excel-365 to render a thread; without
`personList` the thread renders as "unknown user" and Excel emits a
repair warning on next open. The regression test that locks this is
the E2E `T-threaded-rel-attachment` in
[`tests/test_e2e.sh`](../scripts/tests/test_e2e.sh) (real assertion
lands in task 2.05).

### 3.4 `commentsN.xml` part-counter is independent of sheet index

The integer N in `xl/comments<N>.xml` is a **part-counter** allocated
sequentially across the workbook's existing `xl/comments*.xml` files,
NOT the sheet index. A workbook with three sheets where only Sheet3
has comments stores them in `xl/comments1.xml` (NOT
`xl/comments3.xml`). The binding to Sheet3 goes through
`xl/_rels/sheet3.xml.rels` carrying:

```xml
<Relationship Id="rIdN" Target="../comments1.xml"
              Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"/>
```

The same is true for `vmlDrawing<K>.xml` and
`threadedComments<M>.xml` — three independent counters, each
independently allocated from `max+1` over the existing matching
filenames in the workbook.

The regression that locks this is the `T-multi-sheet` E2E (task 2.04
real assertion).

## 4. Honest scope (v1)

Each clause below is locked into the regression suite by a named test in
[`tests/test_xlsx_add_comment.py::TestHonestScope`](../scripts/tests/test_xlsx_add_comment.py).
A future change that lifts a limitation must remove the corresponding
test in the same commit — that is the "scope-creep alarm" mechanism.

- **R9.a** Reply-threads (`parentId` linkage) — NOT supported. Every
  threadedComment is top-level. Lock: `test_HonestScope_no_parentId`.
- **R9.b** Comment body — plain text only. Threaded body is a direct
  text node (no `<r>` / `<rPr>`); legacy body is the standard
  `<comment><text><r><t>…</t></r></text>` shape with no extra
  formatting siblings or children.
  Lock: `test_HonestScope_plain_text_body`.
- **R9.c** VML shape uses Excel's default anchor offsets only —
  `<x:Anchor>` always equals `DEFAULT_VML_ANCHOR` (no custom
  positioning). Lock: `test_HonestScope_default_vml_anchor`.
- **R9.d** Goldens are agent-output-only — never round-tripped through
  Excel (Excel may silently mutate legacy → threaded on save).
  Protocol marker `"DO NOT open these files in Excel"` lives in
  [`tests/golden/README.md`](../scripts/tests/golden/README.md).
  Lock: `test_HonestScope_goldens_README_protocol_marker`.
- **R9.e** `<threadedComment id>` is UUIDv4 — non-deterministic by
  design. `<person id>` is UUIDv5(NAMESPACE_URL, displayName) — stable.
  Re-running the script on identical input produces non-byte-equivalent
  output even with `--date` pinned (see §5 below for how the goldens
  diff harness handles this).
  Lock: `test_HonestScope_threadedComment_id_is_uuidv4`.
- **R9.f** Per-row `initials` override only via `BatchRow.initials` in
  flat-array mode; envelope-mode initials are derived from
  `--default-author`. A separate `--default-initials` flag is v2.
  Lock: `test_HonestScope_no_default_initials_flag` (asserts BOTH
  `--help` omits the flag AND argparse rejects the invocation).
- **R9.g** `--unpacked-dir DIR` library mode (parity with
  `docx_add_comment.py`) is v2 — pipeline integration in v1 is via
  `--batch path.json`. Lock: `test_HonestScope_no_unpacked_dir_flag`
  (same dual gate as R9.f).

## 5. Goldens diff strategy (m-5 / A-Q3)

Stable-shape outputs (clean-no-comments, existing-legacy-preserve,
threaded, multi-sheet, idmap-conflict) are committed as
[`tests/golden/outputs/*.golden.xlsx`](../scripts/tests/golden/outputs/)
and round-trip-checked against the live `xlsx_add_comment.py` output
via [`tests/_golden_diff.py`](../scripts/tests/_golden_diff.py).

### Canonicalisation

XML parts are normalised through `lxml.etree.tostring(..., method="c14n")`
(Canonical XML 1.0). **NOT `c14n2`** — c14n2 does not canonicalise
attribute order, which makes diffs flaky on lxml minor-version bumps.
m-5 lock; locked in [`docs/PLAN.md`](../../../docs/PLAN.md) §"Risks &
decisions deferred to development".

### Volatile-attribute mask

Two attributes are volatile by design (R9.e UUIDv4 + the `dT` timestamp
when `--date` is not pinned). The diff helper rewrites them BEFORE
canonicalisation:

| Attribute | Mask | Rationale |
|---|---|---|
| `<threadedComment id>` | `{MASKED}` | UUIDv4 — re-running produces a different value every time. |
| `<threadedComment dT>` | `MASKED` if NOT containing `2026-01-01` | Goldens are generated with `--date 2026-01-01T00:00:00Z`; any other timestamp is the live `datetime.now(UTC)` value, which is volatile. |

### Re-generation procedure

Goldens are regenerated by running `xlsx_add_comment.py` against each
named input fixture with `--date 2026-01-01T00:00:00Z`:

```bash
python3 scripts/xlsx_add_comment.py \
    scripts/tests/golden/inputs/clean.xlsx \
    scripts/tests/golden/outputs/clean-no-comments.golden.xlsx \
    --cell A5 --author "Reviewer" --text "msg" \
    --date 2026-01-01T00:00:00Z
```

`<threadedComment id>` will still differ run-to-run — that is masked,
not regenerated. Goldens commit cleanly only because the mask runs
on both the actual and the golden side of the comparison.

### Out-of-scope tests

The diff harness covers the five named goldens. Other E2E tests rely
on exit-code + lxml-assertion checks only — canonical diff is for
stable-shape outputs, NOT for exit-code-error tests (m-C plan-review
clarification).

## 6. Internal module map (Task 002 — module split)

The `xlsx_add_comment.py` script is a **thin shim** (≤ 200 LOC) that
delegates to the `xlsx_comment/` package next to it. Public CLI
behaviour is unchanged from xlsx-6 v1 (Task 001); the split exists to
make further development of the script tractable. See
`docs/ARCHITECTURE.md` §3 / §8 for the design and Q1/Q2/Q3 closure.

| Module | Responsibility |
|---|---|
| `xlsx_comment/constants.py` | OOXML namespaces, content-types, anchor + cap constants |
| `xlsx_comment/exceptions.py` | `_AppError` + 14 typed leaves |
| `xlsx_comment/cell_parser.py` | `--cell` syntax parser + sheet resolver |
| `xlsx_comment/batch.py` | `--batch` JSON loader (flat-array vs envelope) |
| `xlsx_comment/ooxml_editor.py` | OOXML mutations (largest module — scanners, part-counter, rels, legacy + threaded writers, `_VML_PARSER` security boundary) |
| `xlsx_comment/merge_dup.py` | Merged-cell resolver + duplicate-cell matrix |
| `xlsx_comment/cli_helpers.py` | Validation + date + post-pack validate utilities |
| `xlsx_comment/cli.py` | argparse + `main` + `single_cell_main` + `batch_main` |

Future contributors: when adding a v2 feature (R9.f
`--default-initials`, R9.g `--unpacked-dir`, parentId reply-threads,
rich text), land it in the **single** appropriate module above —
DO NOT spread changes across files. If a v2 feature pushes
`ooxml_editor.py` past ~1200 LOC, reconsider the Q1=A "single-file"
decision (see ARCHITECTURE §8 override clause).
