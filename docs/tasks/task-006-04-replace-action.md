# Task 006-04: Part-walker (F2) + `--replace` action (F4) — UC-1 GREEN

## Use Case Connection
- **UC-1** — Replace text inside a run (preserve formatting). Main scenario + all Alt-1..Alt-8.
- **R5** — Anchor-search scope (body + headers + footers + footnotes + endnotes; deterministic order; enumerated via `[Content_Types].xml`).
- **R1** — `--replace` action behaviour.

## Task Goal

Land the **F2 part-walker** (`_iter_searchable_parts`) and the **F4
`_do_replace`** action body in `docx_replace.py`. Wire `_run` to
dispatch to `_do_replace` when `args.replace is not None`. Pack +
write the output (deferred post-validate logic comes in 006-07a).

At end of task: UC-1 E2E cases turn GREEN.

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/scripts/docx_replace.py`

**Add F2 `_iter_searchable_parts`:**

```python
_WP_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml": "header",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml": "footer",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml": "footnotes",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml": "endnotes",
}

def _iter_searchable_parts(
    tree_root: Path,
) -> Iterator[tuple[Path, etree._Element]]:
    """Yield (part_path, root_element) for every searchable XML part
    in tree_root, in this deterministic order (TASK §11.1, R5.g):
    document → headers (sorted) → footers (sorted) → footnotes → endnotes.

    Primary enumeration source = [Content_Types].xml Override entries
    (ARCH MIN-3). Filesystem glob is a fallback only if Content_Types
    is missing or malformed (stderr warning).
    """
    ct_path = tree_root / "[Content_Types].xml"
    parts_by_role: dict[str, list[Path]] = {
        "document": [], "header": [], "footer": [],
        "footnotes": [], "endnotes": [],
    }
    if ct_path.is_file():
        try:
            ct_tree = etree.parse(str(ct_path))
            ns = {"ct": "http://schemas.openxmlformats.org/package/2006/content-types"}
            for ov in ct_tree.iterfind(".//ct:Override", ns):
                ct_value = ov.get("ContentType", "")
                role = _WP_CONTENT_TYPES.get(ct_value)
                if role is None:
                    continue
                pname = ov.get("PartName", "")
                # PartName starts with "/", strip it to a relative path
                rel = pname.lstrip("/")
                parts_by_role[role].append(tree_root / rel)
        except etree.XMLSyntaxError as exc:
            print(
                f"[docx_replace] WARNING: [Content_Types].xml parse failed "
                f"({exc}); falling back to filesystem glob.",
                file=sys.stderr,
            )
            _fallback_glob_parts(tree_root, parts_by_role)
    else:
        print(
            "[docx_replace] WARNING: [Content_Types].xml missing; "
            "falling back to filesystem glob.",
            file=sys.stderr,
        )
        _fallback_glob_parts(tree_root, parts_by_role)

    # Sort headers/footers by part name (deterministic ordering R5.g).
    parts_by_role["header"].sort(key=lambda p: p.name)
    parts_by_role["footer"].sort(key=lambda p: p.name)

    for role in ("document", "header", "footer", "footnotes", "endnotes"):
        for p in parts_by_role[role]:
            if not p.is_file():
                continue  # corrupt-package tolerance
            try:
                root = etree.parse(str(p)).getroot()
            except etree.XMLSyntaxError as exc:
                # Malformed part — re-raise as a top-level error caught by _run.
                raise
            yield (p, root)


def _fallback_glob_parts(
    tree_root: Path, parts_by_role: dict[str, list[Path]],
) -> None:
    word = tree_root / "word"
    if not word.is_dir():
        return
    doc = word / "document.xml"
    if doc.is_file():
        parts_by_role["document"].append(doc)
    parts_by_role["header"].extend(word.glob("header*.xml"))
    parts_by_role["footer"].extend(word.glob("footer*.xml"))
    fn = word / "footnotes.xml"
    if fn.is_file():
        parts_by_role["footnotes"].append(fn)
    en = word / "endnotes.xml"
    if en.is_file():
        parts_by_role["endnotes"].append(en)
```

**Add F4 `_do_replace`:**

```python
def _do_replace(
    tree_root: Path,
    anchor: str,
    replacement: str,
    *,
    anchor_all: bool,
) -> int:
    """Walk every searchable part; in each paragraph run
    _merge_adjacent_runs + _replace_in_run. Returns total replacement
    count. Without --all, stops after first matched part is written.
    """
    total = 0
    for part_path, part_root in _iter_searchable_parts(tree_root):
        modified = False
        part_count = 0
        for p in part_root.iter(qn("w:p")):
            _merge_adjacent_runs(p)
            n = _replace_in_run(
                p, anchor, replacement, anchor_all=anchor_all,
            )
            if n > 0:
                modified = True
                part_count += n
                if not anchor_all:
                    break  # first-match wins within this paragraph
            if not anchor_all and total + part_count > 0:
                break  # first-match wins across paragraphs in this part
        if modified:
            # Write part back.
            with part_path.open("wb") as f:
                f.write(etree.tostring(
                    part_root, xml_declaration=True,
                    encoding="UTF-8", standalone=True,
                ))
            total += part_count
            if not anchor_all:
                return total  # first-match wins across all parts
    return total
```

**Wire into `_run` (replacing the `NotImplementedError` from 006-03):**

```python
# After cross-cutting pre-flight, add:
with _tempdir() as tmpdir:
    tree_root = unpack(args.input, tmpdir)

    if args.replace is not None:
        count = _do_replace(
            tree_root, args.anchor, args.replace,
            anchor_all=args.all,
        )
        action_summary = (
            f"replaced {count} anchor(s) "
            f"(anchor={args.anchor!r} -> {args.replace!r})"
        )
    # (insert-after dispatch lands in 006-05; delete-paragraph in 006-06)
    else:
        raise NotImplementedError("docx-6 stub — task-006-05/06")

    if count == 0:
        raise AnchorNotFound(
            f"Anchor not found: {args.anchor!r}",
            code=2, error_type="AnchorNotFound",
            details={"anchor": args.anchor},
        )

    pack(tree_root, args.output)
    # post-validate hook landing in 006-07a
    print(f"{Path(args.output).name}: {action_summary}", file=sys.stderr)
    return 0
```

#### File: `skills/docx/scripts/tests/test_docx_replace.py`

- **Un-skip and live** `TestPartWalker` (≥ 4 cases):
  - `test_content_types_primary_source` — fixture tree with
    `[Content_Types].xml` listing 1 doc + 2 headers + 1 footer +
    footnotes + endnotes; `_iter_searchable_parts` yields 6 parts in
    correct order (document, header1, header2, footer1, footnotes,
    endnotes).
  - `test_filesystem_glob_fallback_on_malformed_content_types` —
    truncate `[Content_Types].xml` to `<Types>` (no Override); function
    falls back to glob and emits stderr warning.
  - `test_missing_part_silently_skipped` — Content_Types references
    `word/header2.xml` but file doesn't exist; iterator yields
    remaining parts without raising.
  - `test_deterministic_header_order` — fixture with `header10.xml`
    + `header2.xml`; sorted output is `header10.xml` before
    `header2.xml` (ascii sort, not numeric — matches R5.g
    "sorted by part name ascending"). Document the lexicographic-vs-
    natural decision in the test docstring.

- **Un-skip and live** `TestReplaceAction` (≥ 5 cases):
  - `test_replace_in_simple_run` — fixture body has "May 2024" in a
    single bold run; after `_do_replace(..., anchor_all=False)`, run
    contains "April 2025" and `<w:rPr><w:b/></w:rPr>` is preserved
    (R1.a, R1.b).
  - `test_replace_first_match_default` — body has 3 occurrences of
    "foo"; without `--all`, only the first is replaced (R1.c).
  - `test_replace_all_flag` — same fixture; with `--all`, all 3 are
    replaced; counter == 3 (R1.d).
  - `test_replace_empty_replacement_allowed` — `--replace ""` strips
    the anchor; `<w:t>` text is "" or shortened by `len(anchor)` (R1.e).
  - `test_replace_cross_run_anchor_returns_zero` — anchor "May 2024"
    is split across `<w:r>foo May </w:r><w:r>2024</w:r>` with
    different rPr (merge keeps them separate); `_do_replace` returns 0
    → AnchorNotFound (R1.f honest-scope).

#### File: `skills/docx/scripts/tests/test_e2e.sh`

- Un-SKIP UC-1 E2E cases:
  - `T-docx-replace-happy` — anchor "May 2024" → "April 2025" in
    `docx_replace_body.docx`; output file validates via
    `office/validate.py`; bold run preservation asserted via
    `python3 -c "import docx; ..."` post-check.
  - `T-docx-replace-empty-replacement` — `--replace ""` strips anchor.
  - `T-docx-replace-all-multiple` — `--all` on fixture with 3 occurrences.
  - `T-docx-replace-anchor-not-found` — bogus anchor → exit 2
    `AnchorNotFound`.
  - `T-docx-replace-cross-run-anchor-fails` — generate or use fixture
    where anchor crosses rPr boundary → exit 2 `AnchorNotFound`
    (R10.a honest-scope lock).

### Component Integration

`_run` now dispatches to `_do_replace` when `args.replace is not
None`. The fallback `NotImplementedError("docx-6 stub —
task-006-05/06")` keeps insert/delete cases SKIP-friendly until 006-05
and 006-06 land.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01 (T-docx-replace-happy):** UC-1 main scenario. Exit 0. stderr summary `<basename>: replaced 1 anchor (...)`.
2. **TC-E2E-02 (T-docx-replace-empty-replacement):** `--replace ""` strips. Exit 0.
3. **TC-E2E-03 (T-docx-replace-all-multiple):** 3 occurrences with `--all` → counter 3.
4. **TC-E2E-04 (T-docx-replace-anchor-not-found):** Bogus anchor → exit 2.
5. **TC-E2E-05 (T-docx-replace-cross-run-anchor-fails):** Cross-rPr anchor → exit 2 `AnchorNotFound` (R10.a).
6. **TC-E2E-06 (T-docx-replace-help-honest-scope):** Already green from 006-03; re-verify.

### Unit Tests

1. **TC-UNIT-01..04 (TestPartWalker):** 4 cases above pass.
2. **TC-UNIT-05..09 (TestReplaceAction):** 5 cases above pass.

### Regression Tests

- All G4 (docx-1) and previously-green docx-6 tests still pass.
- All 12 `diff -q` cross-skill replication checks silent.

## Acceptance Criteria

- [ ] `_iter_searchable_parts` reads `[Content_Types].xml` first; glob fallback only on parse failure.
- [ ] `_do_replace` writes parts via `etree.tostring` with XML declaration.
- [ ] First-match default (no `--all`) returns after first part is modified — does NOT continue walking.
- [ ] UC-1 E2E cases (5 listed above) pass.
- [ ] TestPartWalker (≥ 4 cases) + TestReplaceAction (≥ 5 cases) pass.
- [ ] `wc -l skills/docx/scripts/docx_replace.py` ≤ 380 (F1+F2+F4+F7-skeleton ≈ 250 LOC + ~80 for F2 + ~80 for F4 + wiring; well within 600 budget).
- [ ] G4 regression: docx-1 E2E block passes unchanged.
- [ ] `validate_skill.py skills/docx` exits 0.
- [ ] All 12 `diff -q` cross-skill replication checks silent.

## Notes

The "first-match wins across all parts" semantics are tricky: without
`--all`, we want `_do_replace` to stop walking after the **first part
that had a match** wrote its replacement. The implementation uses
two break levels: inner `break` exits the paragraph loop within a
part; outer `if not anchor_all: return total` exits the part loop
after the part is written. Verify this in
`test_replace_first_match_default` with a fixture where paragraph 1
of part 1 and paragraph 1 of part 2 both contain the anchor; without
`--all`, only part 1 is modified.

The `_iter_searchable_parts` part-write semantics: parts are mutated
in-memory; `_do_replace` writes them back to disk per-part as it
detects modifications. `office.pack` reads the disk state at the end.
This is the same pattern as `docx_add_comment.py`.

For T-docx-replace-cross-run-anchor-fails, the fixture needs an
anchor split across two runs with **different** rPr (otherwise
`_merge_adjacent_runs` would coalesce them and the anchor would be
found post-merge). Generate the fixture with markdown like
`**May** 2024` (creates `<w:r rPr=bold>May</w:r><w:r> 2024</w:r>`,
different rPr).

RTM coverage: **R1.a–R1.g, R5.a–R5.g, R10.a (R10.a lock test exists
here as a happy-path E2E; full honest-scope regression suite lands in
006-08)**.
