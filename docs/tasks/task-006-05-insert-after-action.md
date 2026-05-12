# Task 006-05: `--insert-after` action (F5) — UC-2 GREEN

## Use Case Connection
- **UC-2** — Insert paragraph(s) after the anchor's containing `<w:p>` (main scenario + all Alt-1..Alt-8).
- **R2.a–R2.h** — md2docx subprocess, body extraction, sectPr strip, deep-clone, paragraph-level concat-text, `--all`, stdin, stdin cap.
- **R10.b, R10.e** — image-bearing MD source emits stderr warning; `<w:numId>` survives in inserted paragraphs.

## Task Goal

Implement F5 in `docx_replace.py`:
- `_materialise_md_source(md_path, scripts_dir, tmpdir) -> Path` —
  `subprocess.run(["node", str(scripts_dir/"md2docx.js"), str(md_path),
   str(insert_docx)], shell=False, timeout=60, capture_output=True,
   check=False)`. Non-zero → `Md2DocxFailed`.
- `_extract_insert_paragraphs(insert_tree_root) -> list[etree._Element]`
  — deep-clone `<w:p>` and `<w:tbl>` body children, filter trailing
  `<w:sectPr>` (Q-A3), emit stderr warnings on `r:embed`/`r:id` (R10.b
  precursor) and on `<w:numId>` references when base doc lacks
  `numbering.xml` (Q-A4 / R10.e precursor).
- `_do_insert_after(tree_root, anchor, insert_paragraphs, *, anchor_all)
   -> int` — paragraph-level concat-text matching (D6/B) via
  `_find_paragraphs_containing_anchor` from `docx_anchor.py`; insert
  deep-clones immediately after each matched `<w:p>` via `addnext`.

Wire stdin `-` path: detect `args.insert_after == "-"` →
`_read_stdin_capped()` → write bytes to `tempfile.NamedTemporaryFile
(suffix=".md", delete=False)` (closed file inside `with _tempdir()`
scope so cleanup is automatic).

At end of task: UC-2 E2E cases turn GREEN.

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/scripts/docx_replace.py`

**Add F5 `_materialise_md_source`:**

```python
def _materialise_md_source(
    md_path: Path, scripts_dir: Path, tmpdir: Path,
) -> Path:
    """Run `node md2docx.js MD OUT` in subprocess; return path to the
    materialised .docx. shell=False, timeout=60, capture_output=True.
    Non-zero rc → raise Md2DocxFailed (exit 1)."""
    md2docx = scripts_dir / "md2docx.js"
    if not md2docx.is_file():
        raise Md2DocxNotAvailable(
            f"md2docx.js not found at {md2docx}",
            code=1, error_type="Md2DocxNotAvailable",
            details={"path": str(md2docx)},
        )
    out_docx = tmpdir / "insert.docx"
    try:
        result = subprocess.run(
            ["node", str(md2docx), str(md_path), str(out_docx)],
            shell=False, timeout=60, capture_output=True, text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        # Node binary not on PATH.
        raise Md2DocxNotAvailable(
            f"node binary not found: {exc}",
            code=1, error_type="Md2DocxNotAvailable",
            details={"detail": str(exc)},
        )
    except subprocess.TimeoutExpired as exc:
        raise Md2DocxFailed(
            "md2docx.js timed out (60s)",
            code=1, error_type="Md2DocxFailed",
            details={"stderr": (exc.stderr or "")[:8192],
                     "returncode": None, "reason": "timeout"},
        )
    if result.returncode != 0:
        raise Md2DocxFailed(
            f"md2docx.js failed (rc={result.returncode})",
            code=1, error_type="Md2DocxFailed",
            details={"stderr": (result.stderr or "")[:8192],
                     "returncode": result.returncode},
        )
    if not out_docx.is_file():
        raise Md2DocxOutputInvalid(
            "md2docx.js produced no output file",
            code=1, error_type="Md2DocxOutputInvalid",
            details={"expected": str(out_docx)},
        )
    return out_docx
```

**Add F5 `_extract_insert_paragraphs`:**

```python
def _extract_insert_paragraphs(
    insert_tree_root: Path,
    *,
    base_has_numbering: bool,
) -> list[etree._Element]:
    """Deep-clone body block children from insert tree's word/document.xml.
    Filter out trailing <w:sectPr> (Q-A3 lock). Emit stderr warnings on
    r:embed/r:id references (R10.b) and on <w:numId> when base doc has
    no numbering.xml (Q-A4 / R10.e)."""
    doc_xml = insert_tree_root / "word" / "document.xml"
    if not doc_xml.is_file():
        raise Md2DocxOutputInvalid(
            "insert docx has no word/document.xml",
            code=1, error_type="Md2DocxOutputInvalid",
            details={"path": str(doc_xml)},
        )
    tree = etree.parse(str(doc_xml))
    body = tree.find(qn("w:body"))
    if body is None:
        raise Md2DocxOutputInvalid(
            "insert docx body element missing",
            code=1, error_type="Md2DocxOutputInvalid",
            details={"path": str(doc_xml)},
        )
    children: list[etree._Element] = []
    saw_relationship_ref = False
    saw_numid = False
    for child in body:
        local = etree.QName(child).localname
        if local == "sectPr":
            continue  # Q-A3 strip.
        clone = _deep_clone(child)
        # Scan for relationship-bearing attributes (R10.b precursor warning).
        for el in clone.iter():
            for attr_name in el.attrib:
                if attr_name.endswith("}embed") or attr_name.endswith("}id"):
                    saw_relationship_ref = True
                    break
            if etree.QName(el).localname == "numId":
                saw_numid = True
        children.append(clone)
    if saw_relationship_ref:
        print(
            "[docx_replace] WARNING: inserted body references "
            "relationships (r:embed/r:id) that are not copied to the "
            "base document — embedded objects may not render. Use "
            "--insert-after with image-free markdown in v1.",
            file=sys.stderr,
        )
    if saw_numid and not base_has_numbering:
        print(
            "[docx_replace] WARNING: inserted body contains "
            "<w:numId> references; base document has no numbering.xml "
            "— list items may render as plain text. Relocate numbering "
            "in a future update.",
            file=sys.stderr,
        )
    return children


def _deep_clone(el: etree._Element) -> etree._Element:
    """Return a deep copy of `el` for cross-tree splicing."""
    import copy
    return copy.deepcopy(el)
```

**Add F5 `_do_insert_after`:**

```python
def _do_insert_after(
    tree_root: Path,
    anchor: str,
    insert_paragraphs: list[etree._Element],
    *,
    anchor_all: bool,
) -> int:
    """Locate matching paragraphs in every searchable part; insert
    deep-cloned `insert_paragraphs` immediately after each match.

    Without --all, stops at first match across all parts. Returns the
    count of anchor paragraphs after which content was inserted.
    """
    match_count = 0
    for part_path, part_root in _iter_searchable_parts(tree_root):
        matches = _find_paragraphs_containing_anchor(part_root, anchor)
        if not matches:
            continue
        for matched_p in matches:
            # Deep-clone the insert list per match (no shared refs).
            clones = [_deep_clone(p) for p in insert_paragraphs]
            # Insert AFTER matched_p: walk reversed and call addnext.
            for clone in reversed(clones):
                matched_p.addnext(clone)
            match_count += 1
            if not anchor_all:
                # Write this part and return.
                with part_path.open("wb") as f:
                    f.write(etree.tostring(
                        part_root, xml_declaration=True,
                        encoding="UTF-8", standalone=True,
                    ))
                return match_count
        # All matches in this part processed; write back.
        with part_path.open("wb") as f:
            f.write(etree.tostring(
                part_root, xml_declaration=True,
                encoding="UTF-8", standalone=True,
            ))
    return match_count
```

**Wire into `_run` (insert-after branch):**

```python
elif args.insert_after is not None:
    scripts_dir = Path(__file__).resolve().parent
    base_has_numbering = (tree_root / "word" / "numbering.xml").is_file()

    if args.insert_after == "-":
        # Stdin path: read with cap; write to tempfile.
        data = _read_stdin_capped()
        if not data.strip():
            raise EmptyInsertSource(
                "Empty stdin for --insert-after",
                code=2, error_type="EmptyInsertSource",
                details={"source": "<stdin>"},
            )
        md_path = tmpdir / "stdin.md"
        md_path.write_bytes(data)
    else:
        md_path = Path(args.insert_after)
        if not md_path.is_file():
            raise FileNotFoundError(args.insert_after)
        if md_path.stat().st_size == 0:
            raise EmptyInsertSource(
                f"Empty insert source: {md_path}",
                code=2, error_type="EmptyInsertSource",
                details={"source": str(md_path)},
            )

    insert_docx = _materialise_md_source(md_path, scripts_dir, tmpdir)
    insert_tree_root = tmpdir / "insert_unpacked"
    insert_tree_root.mkdir()
    unpack(insert_docx, insert_tree_root)

    insert_paragraphs = _extract_insert_paragraphs(
        insert_tree_root, base_has_numbering=base_has_numbering,
    )
    count = _do_insert_after(
        tree_root, args.anchor, insert_paragraphs, anchor_all=args.all,
    )
    action_summary = (
        f"inserted {len(insert_paragraphs)} paragraph(s) after "
        f"anchor {args.anchor!r} ({count} match(es))"
    )
```

#### File: `skills/docx/scripts/tests/test_docx_replace.py`

- **Un-skip and live** `TestInsertAfterAction` (≥ 5 cases):
  - `test_materialise_md_source_subprocess_argv` — patch
    `subprocess.run`; assert argv is `["node", "<scripts>/md2docx.js",
    "<md>", "<out.docx>"]` with `shell=False`.
  - `test_materialise_md_source_failure_raises_md2docx_failed` — patch
    subprocess.run to return rc=2; expect `Md2DocxFailed` with
    `details["stderr"]` and `details["returncode"]`.
  - `test_extract_insert_paragraphs_strips_sectPr` — fixture insert
    docx with body `<w:p><w:p><w:sectPr/>`; result is 2 elements (no
    sectPr).
  - `test_extract_insert_paragraphs_warns_on_relationship_refs` —
    fixture with `r:embed` on `<w:drawing>`; **plan-review MAJ-3 fix:
    THREE assertions, not just warning shape**:
    1. stderr warning captured matches the exact ARCH §8 format.
    2. The returned paragraph is still in the list (warn-and-proceed
       Alt-6).
    3. **R10.b survival check** — after the warning code path, no
       live `r:embed` referencing a relationship that exists in the
       BASE document's `word/_rels/document.xml.rels` survives. Walk
       the returned paragraph's tree:
       ```python
       embed_attr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
       live_embeds = [
           el for el in paragraph.iter()
           if embed_attr in el.attrib
       ]
       # Either md2docx stripped the embed, or the r:id points at a
       # relationship that does NOT exist in the base doc's rels —
       # both outcomes satisfy R10.b "no LIVE r:embed".
       self.assertTrue(
           not live_embeds or all(
               not _rel_exists_in_base(el.attrib[embed_attr])
               for el in live_embeds
           )
       )
       ```
    (Note: the corresponding full E2E regression lock for R10.b lives
    in 006-08; this unit-level check pins the warning-code-path
    behaviour at the function boundary.)
  - `test_do_insert_after_first_match` — base fixture; anchor matches
    one paragraph; insert list of 2 paragraphs; after insert, the
    matched paragraph + 2 new paragraphs appear in order.
  - `test_do_insert_after_all_duplicates` — anchor matches 3
    paragraphs; with `--all`, the insert list is deep-cloned 3 times
    (3 × 2 = 6 new paragraphs total).

#### File: `skills/docx/scripts/tests/test_e2e.sh`

- Un-SKIP UC-2 cases:
  - `T-docx-insert-after-file` — `--insert-after docx_replace_insert_source.md`
    after anchor "Article 5." in `docx_replace_body.docx`. Exit 0; output
    has 2 new paragraphs in correct position.
  - `T-docx-insert-after-stdin` — `cat docx_replace_insert_source.md |
    python3 docx_replace.py ... --insert-after -`. Same output as file
    mode.
  - `T-docx-insert-after-empty-stdin` — empty stdin → exit 2
    `EmptyInsertSource`.
  - `T-docx-insert-after-all-duplicates` — fixture with anchor in 2
    paragraphs; with `--all` → 4 new paragraphs (2 × 2).
  - `T-docx-insert-after-image-warns` — MD source
    `docx_replace_insert_with_image.md` containing `![alt](nonexistent.png)`;
    stderr captures "[docx_replace] WARNING: inserted body references
    relationships..."; exit code 0 (warn-and-proceed Alt-6); inserted
    `<w:p>` contains no live r:embed (refs stripped via md2docx fallback
    OR text-only fallback). R10.b lock.

### Component Integration

The `tmpdir` allocation from `_tempdir()` in `_run` is now shared
between the unpack of the input docx, the materialised insert docx,
and the stdin tempfile. All three are cleaned up via the
`contextmanager` exit handler.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01 (T-docx-insert-after-file):** UC-2 main. Exit 0; output validates.
2. **TC-E2E-02 (T-docx-insert-after-stdin):** stdin path = file path semantically.
3. **TC-E2E-03 (T-docx-insert-after-empty-stdin):** Empty stdin → exit 2.
4. **TC-E2E-04 (T-docx-insert-after-all-duplicates):** N×duplication.
5. **TC-E2E-05 (T-docx-insert-after-image-warns):** stderr warning + exit 0 + no live r:embed in output.

### Unit Tests

1. **TC-UNIT-01..06 (TestInsertAfterAction):** 6 cases above pass.

### Regression Tests

- All G4 (docx-1) + previous docx-6 (006-02, 006-03, 006-04) tests still green.
- All 12 `diff -q` cross-skill replication checks silent.

## Acceptance Criteria

- [ ] `_materialise_md_source` uses `shell=False`, `timeout=60`, `capture_output=True`.
- [ ] `_extract_insert_paragraphs` strips trailing `<w:sectPr>` (Q-A3).
- [ ] R10.b warning string matches the exact format from ARCH §8.
- [ ] R10.e warning string matches the exact format from ARCH §8.
- [ ] Deep-clone is per-match (no shared etree references between
      duplicated paragraphs with `--all`).
- [ ] UC-2 E2E cases (5 listed above) pass.
- [ ] `TestInsertAfterAction` (≥ 6 cases) pass.
- [ ] `wc -l skills/docx/scripts/docx_replace.py` ≤ 500 (F5 ~ 120 LOC pushes total to ~ 500; well within 600).
- [ ] G4 regression: docx-1 E2E block still passes.
- [ ] `validate_skill.py skills/docx` exits 0.
- [ ] All 12 `diff -q` cross-skill replication checks silent.

## Notes

The `addnext(clone)` API of `lxml.etree._Element` inserts `clone` as
the **immediate** next sibling. To preserve order when inserting
multiple paragraphs, iterate the clone list in **reverse** and call
`addnext` for each (this produces the desired forward order in the
resulting tree).

The "warn-and-proceed" semantics for R10.b are critical: the test in
T-docx-insert-after-image-warns asserts BOTH a stderr warning AND
exit 0 with the inserted paragraph present in the output. The
inserted paragraph contains no live `r:embed` (the `md2docx.js`
output may strip the embed reference if the image isn't reachable, OR
emit text-only fallback). Either outcome satisfies R10.b.

Subprocess discipline: `subprocess.run(["node", str(md2docx_path),
str(md_path), str(out_path)], shell=False, ...)` — the argv list
form is mandatory (security R3.2). Never use `f"node {md2docx_path}"`
or `shell=True`. The unit test `test_materialise_md_source_subprocess_argv`
pins this contract.

For the `<w:numId>` check, the cheap implementation is "iterate the
clone tree once and check for `<w:numId>` elements". This is O(n)
per insert and not worth optimising. The `base_has_numbering` check is
a single filesystem stat against `tree_root / "word" / "numbering.xml"`.

RTM coverage: **R2.a, R2.b, R2.c, R2.d, R2.e, R2.f, R2.g, R2.h
(insert path re-assertion), R10.b (warning code; lock test in 006-08),
R10.e (warning code; lock test in 006-08)**.
