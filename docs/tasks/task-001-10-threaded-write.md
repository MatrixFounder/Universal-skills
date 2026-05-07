# Task 2.05 [R3]: [LOGIC IMPLEMENTATION] Threaded write path + personList + workbook rels

## Use Case Connection
- I1.4 (Threaded comment write path).
- M6 (personList rel on `xl/_rels/workbook.xml.rels`, NOT sheet rels).
- m1 (`str.casefold()` for non-ASCII userId).
- Q7 closure (Excel-365 fidelity — `--threaded` writes BOTH parts).
- R9.a (no `parentId` in v1).
- RTM: R3.

## Task Goal
Layer the threaded write path on top of 2.04's legacy path. When `--threaded` is set, the script writes BOTH a legacy stub (per Q7 Option A fidelity) AND a `<threadedComment>` + `<person>` registry. `personList` is workbook-scoped (M6). `userId` uses `str.casefold()` (m1). All threaded comments are top-level (no `parentId` — R9.a).

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

**Function `ensure_threaded_comments_part(tree_root, sheet_name) -> tuple[Path, etree._Element]`:**
- Same shape as `ensure_legacy_comments_part` but for `xl/threadedComments<M>.xml`.
- Logic:
  1. Sheet rels lookup for type `http://schemas.microsoft.com/office/2017/10/relationships/threadedComment`. If present → load and return.
  2. Else allocate `M = next_part_counter(tree, "xl/threadedComments?.xml")`; create `xl/threadedComments<M>.xml` with empty `<ThreadedComments xmlns="http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"/>`; add sheet rel; add `[Content_Types].xml` Override.

**Function `ensure_person_list(tree_root) -> tuple[Path, etree._Element]`:**
- Logic:
  1. Inspect `xl/_rels/workbook.xml.rels` for type `http://schemas.microsoft.com/office/2017/10/relationships/person`. If present → load `xl/persons/personList.xml` and return.
  2. Else create `xl/persons/personList.xml` with `<personList xmlns="..."/>` (empty); add **workbook-scoped** rel to `xl/_rels/workbook.xml.rels` (M6 — NOT a sheet rel); add Override to `[Content_Types].xml`.

**Function `add_person(person_list_root, display_name) -> str`:**
- Logic:
  1. Iterate existing `<person>` children. If any `displayName == display_name` (CASE-SENSITIVE, m5) → return existing `id` attribute.
  2. Else build:
     ```python
     person_id = "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, display_name)).upper() + "}"
     user_id = display_name.casefold()  # m1
     element = etree.SubElement(root, qn("person"),
         displayName=display_name, id=person_id, userId=user_id, providerId="None"
     )
     ```
  3. Return `person_id`.

**Function `add_threaded_comment(threaded_root, ref, person_id, text, date_iso) -> str`:**
- Logic:
  1. `threaded_id = "{" + str(uuid.uuid4()).upper() + "}"` (R9.e — UUIDv4 non-deterministic by design).
  2. Append `<threadedComment ref="A5" dT="{date_iso}" personId="{person_id}" id="{threaded_id}">` with child `<text>{text}</text>` (plain text — no rich runs per R9.b).
  3. Return `threaded_id`.

**Modify `single_cell_main(args, tree_root_dir, all_sheets) -> int`:**
- Branch on `args.threaded`:
  - **If `--threaded`** (Q7 Option A fidelity):
    1. Run the full legacy path (steps 1–8 from 2.04) — Q7 says "both parts".
    2. ALSO call:
       - `pl_root = ensure_person_list(tree)`.
       - `person_id = add_person(pl_root, args.author)`.
       - `tc_root = ensure_threaded_comments_part(tree, sheet_name)`.
       - `add_threaded_comment(tc_root, ref, person_id, args.text, args.date_iso)`.
  - **If `--no-threaded`** (default): legacy path only (2.04 unchanged).
- Final pack/return.

### Component Integration
- Re-uses scanners from 2.03, helpers from 2.04. No new module dependencies.

## Test Cases

### End-to-end Tests
- **TC-E2E-T-threaded:** `clean.xlsx --cell A5 --author "Q" --text "msg" --threaded --date 2026-01-01T00:00:00Z` → produced file has:
  - `xl/comments1.xml` with author "Q" + legacy comment (Q7 fidelity stub).
  - `xl/threadedComments1.xml` with `<threadedComment ref="A5" dT="2026-01-01T00:00:00Z" personId="{...}" id="{...}">msg</threadedComment>`.
  - `xl/persons/personList.xml` with `<person displayName="Q" id="{<UUID>}" userId="q" providerId="None"/>`. The person `id` MUST equal `uuid.uuid5(uuid.NAMESPACE_URL, "Q")` formatted as `{XXXX-...}` — assert exact value for stability.
  - `xl/_rels/workbook.xml.rels` has the `personList` rel.
  - `xl/_rels/sheet1.xml.rels` has the `threadedComment` rel.
- **TC-E2E-T-thread-linkage:** Add 2 comments to same cell with `--threaded` (e.g. via two invocations or a 2-row batch) → `<threadedComment>` appears twice with same `ref`, distinct `id`s, both `personId` resolve to the same `<person>`.
- **TC-E2E-T-threaded-rel-attachment:** Verify `personList` rel is on `xl/_rels/workbook.xml.rels` and the `threadedComment` rel is on `xl/_rels/sheet1.xml.rels` — explicit M6 lock.

### Unit Tests
- Remove `skipTest` from:
  - `TestPersonRecord.test_uuidv5_stable_on_displayName`: `add_person(empty, "Alice")` then `add_person(empty, "Alice")` → second call returns the same `id` as the first; that `id` equals `"{" + str(uuid.uuid5(uuid.NAMESPACE_URL, "Alice")).upper() + "}"`.
  - `TestPersonRecord.test_providerId_literal_None_string`: assert XML attribute string `"None"`, NOT Python `None`.
  - `TestPersonRecord.test_userId_casefold_strasse` (m1): `add_person(empty, "STRAẞE")` → `userId="strasse"`.
  - `TestPersonRecord.test_dedup_case_sensitive_displayName` (m5): `add_person(root, "Alice")`; `add_person(root, "alice")` → two `<person>` records (case-sensitive on displayName).

### Regression Tests
- Tests from 2.04 stay green (legacy path is unchanged when `--no-threaded`).
- Q7 Option A fidelity sanity: `T-clean-no-comments` (no `--threaded`) MUST NOT produce `xl/threadedComments*.xml` or `xl/persons/`.

## Acceptance Criteria
- [ ] 3 TC-E2E above pass.
- [ ] 4 unit tests in `TestPersonRecord` pass.
- [ ] M6: personList rel verified to live on `xl/_rels/workbook.xml.rels`.
- [ ] m1: `casefold()` test on `STRAẞE` → `strasse` passes.
- [ ] Q7 Option A: `--threaded` invocation emits BOTH legacy `<comment>` AND threaded `<threadedComment>` parts.
- [ ] R9.a: produced `<threadedComment>` has NO `parentId` attribute.
- [ ] R9.b: produced threaded body is plain text — no `<r>` / `<rPr>` wrappers.
- [ ] No edits to `skills/docx/scripts/office/`.

## Notes
- The threaded `id` UUIDv4 non-determinism (R9.e) means goldens cannot byte-equal — the canonical-XML diff in 2.10 must mask `<threadedComment id>` and (when `--date` is unpinned) `dT`.
- `displayName="Q"` produces a stable UUIDv5 the developer can hardcode in the test assertion. Quick computation: `python3 -c 'import uuid; print(uuid.uuid5(uuid.NAMESPACE_URL, "Q"))'` — record the value in the test as the expected literal.
- Once 2.05 lands, all of `TestPersonRecord.*` is green; the dependent `T-batch-50` (in 2.06) will exercise dedup at scale.
