# Task 007 — [LIGHT] docx-6.7 — `--scope=body|headers|footers|footnotes|endnotes|all` filter

> **Backlog row:** `docx-6.7` (`docs/office-skills-backlog.md` §docx, just added).
> **Mode:** **`/light`** — fast-track for trivial low-risk CLI addition.
> **Predecessor:** docx-6 v1 (MERGED 2026-05-12). This task closes one of
> three v2 honest-scope deferrals (the others — docx-6.5 image relocator
> and docx-6.6 numbering relocation — stay deferred).

## 0. Meta Information

- **Task ID:** `007`
- **Slug:** `docx-replace-scope-filter`
- **Effort:** **S (~30-50 LOC + 4-6 unit tests + 2 E2E)**
- **Backlog row:** `docx-6.7` (`docs/office-skills-backlog.md`)
- **License:** Proprietary (per `CLAUDE.md` §3 docx skill).
- **Risk:** **LOW** — pure CLI/filter addition. No architecture change. No
  new dependencies. Doesn't touch `office/`, `_soffice.py`, `_errors.py`,
  `preview.py`, `office_passwd.py`. Default behavior unchanged
  (`--scope=all` = current).

## 1. Goal

Add a `--scope` CLI flag to `docx_replace.py` that lets the caller
restrict anchor-search to a subset of OOXML parts. v1 part-walk order
(TASK 006 §9 §11.1) is fixed: document → headers → footers → footnotes
→ endnotes. v2 (this task) makes the SET of walked parts configurable
without changing the order within the set.

## 2. Use Case

**UC-1: Edit body only, leave header/footer boilerplate untouched.**

Typical scenario:
- A contract has "Effective Date: May 2024" both in the body AND as
  page-header boilerplate (logo + meta info repeated on every page).
- Agent wants to update the body date to "April 2025" but leave the
  header alone (it carries a separate template-version stamp that's
  managed elsewhere).
- Today: `docx_replace.py contract.docx out.docx --anchor "May 2024"
  --replace "April 2025"` finds the anchor in `document.xml` first
  (first-match-wins), replaces it, returns 0. Header is untouched —
  works **by accident** because document order is deterministic.
- With `--all`: BOTH locations get replaced (potentially wrong).
- With `--scope=body --all`: ONLY body gets replaced, header untouched
  by design. **This is the user-controlled fix.**

## 3. Requirements (RTM)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R1** | `--scope=<list>` CLI flag | ✅ | R1.a accept comma-separated values from `{body, headers, footers, footnotes, endnotes, all}`; R1.b default = `all` (preserves current behavior); R1.c case-insensitive; R1.d invalid value → exit 2 `UsageError` with envelope listing accepted values; R1.e `all` is mutually exclusive with the specific set OR `all` short-circuits to all roles; R1.f duplicate values dedup'd silently. |
| **R2** | Filter applied in `_iter_searchable_parts` | ✅ | R2.a after Content_Types parse + before yield, drop parts whose role is not in the requested scope; R2.b deterministic order WITHIN the requested set preserved (per TASK 006 R5.g); R2.c if filter yields zero parts (e.g. user said `--scope=footnotes` but no `footnotes.xml` exists) → returns from generator silently → caller raises `AnchorNotFound` (existing path). |
| **R3** | Behavioral parity with v1 | ✅ | R3.a default invocation (no `--scope`) MUST be byte-identical to v1 — same parts walked, same order, same results. Verified by re-running 24 existing T-docx-* E2E cases unchanged; R3.b R10.a-e + Q-U1 + A4 TOCTOU honest-scope locks unchanged. |
| **R4** | Tests | ✅ | R4.a ≥ 4 new unit tests in `TestPartWalker` covering body-only, headers+footers, single-role, invalid value; R4.b ≥ 2 new E2E cases (T-docx-scope-body-only happy + T-docx-scope-invalid-value); R4.c R3.a regression assertion: existing 24 T-docx-* cases still pass unchanged. |
| **R5** | Docs | ✅ | R5.a `--help` text mentions `--scope` with default and accepted values; R5.b SKILL.md §4 Script Contract row updated; R5.c backlog row `docx-6.7` → ✅ DONE with status line; R5.d `.AGENTS.md` (docx scripts) `docx_replace.py` entry mentions `--scope` capability. |

## 4. CLI surface

```
docx_replace.py INPUT OUTPUT --anchor TEXT --replace TEXT [--scope=<list>] [--all] [--json-errors]
docx_replace.py INPUT OUTPUT --anchor TEXT --insert-after PATH [--scope=<list>] [--all] [--json-errors]
docx_replace.py INPUT OUTPUT --anchor TEXT --delete-paragraph [--scope=<list>] [--all] [--json-errors]
docx_replace.py --unpacked-dir TREE --anchor TEXT --replace TEXT [--scope=<list>]
```

`<list>` examples:
- `--scope=all` — default (current behavior; explicit form).
- `--scope=body` — only `word/document.xml`.
- `--scope=body,headers` — body + all header parts.
- `--scope=footnotes,endnotes` — only note parts.

Honest scope: `--scope` controls **which parts are searched**; it does
NOT control **what kinds of edits** are allowed (a `--scope=body
--delete-paragraph` invocation still respects the last-body-paragraph
guard from R10.c).

## 5. Acceptance Criteria

- [ ] `docx_replace.py --help` shows `--scope` with default + accepted values.
- [ ] Default invocation (no `--scope`) produces byte-identical results to v1 — all 24 existing T-docx-* E2E cases pass.
- [ ] `--scope=body` on a fixture with anchor in BOTH body and header replaces ONLY the body occurrence.
- [ ] `--scope=invalid` exits 2 with `UsageError` envelope listing accepted values.
- [ ] ≥ 4 new unit tests + ≥ 2 new E2E cases pass.
- [ ] LOC delta on `docx_replace.py` + `_actions.py` ≤ 60 combined.
- [ ] 100 + N existing unit tests + ≥ 6 new = 106+ total all green.
- [ ] 147 + 2 = 149+ E2E pass.
- [ ] 12 `diff -q` cross-skill replication checks silent.
- [ ] `validate_skill.py skills/docx` exit 0.

## 6. Out of Scope (deferred)

- Smart aliases like `--scope=text` (= body + headers + footers; excludes notes). Not in v2 — explicit roles only.
- Per-part path filter (e.g. `--scope=word/header1.xml` to restrict to a specific header). Not in v2 — role-level only.
- `--scope` ordering control (always document-order within filtered set). Not in v2.

## 7. Implementation Sketch

### File: `skills/docx/scripts/docx_replace.py`

In `build_parser()`, add after `--unpacked-dir`:

```python
_VALID_SCOPES = {"body", "headers", "footers", "footnotes", "endnotes", "all"}

def _parse_scope(raw: str) -> set[str]:
    """Parse --scope value: comma-separated, case-insensitive,
    dedup'd. Returns a set of role names. Raises _AppError on invalid."""
    items = {v.strip().lower() for v in raw.split(",") if v.strip()}
    if not items:
        raise _AppError(
            "--scope must specify at least one value",
            code=2, error_type="UsageError",
            details={"valid": sorted(_VALID_SCOPES)},
        )
    invalid = items - _VALID_SCOPES
    if invalid:
        raise _AppError(
            f"--scope: unknown value(s): {sorted(invalid)}",
            code=2, error_type="UsageError",
            details={"invalid": sorted(invalid),
                     "valid": sorted(_VALID_SCOPES)},
        )
    # "all" expands to the full set excluding "all" itself.
    if "all" in items:
        return _VALID_SCOPES - {"all"}
    return items

parser.add_argument(
    "--scope", type=str, default="all",
    help="Comma-separated parts to search: "
         "body, headers, footers, footnotes, endnotes, all (default: all). "
         "Example: --scope=body,headers to skip notes.",
)
```

In `_dispatch_action`, parse `args.scope` to a `set[str]` once and
pass to `_do_replace`/`_do_insert_after`/`_do_delete_paragraph`:

```python
scope = _parse_scope(args.scope)
if args.replace is not None:
    count = _do_replace(tree_root, args.anchor, args.replace,
                        anchor_all=args.all, scope=scope)
# ...
```

### File: `skills/docx/scripts/_actions.py`

Update `_iter_searchable_parts` signature:

```python
def _iter_searchable_parts(
    tree_root: Path,
    scope: set[str] | None = None,  # None = all roles (back-compat)
) -> Iterator[tuple[Path, etree._Element]]:
    ...
    # After parts_by_role populated, filter:
    if scope is not None:
        parts_by_role = {role: paths for role, paths in parts_by_role.items()
                         if role in scope}
    # ... rest unchanged ...
```

Pass `scope` through `_do_replace`/`_do_insert_after`/`_do_delete_paragraph`:

```python
def _do_replace(tree_root, anchor, replacement, *, anchor_all, scope=None):
    for part_path, part_root in _iter_searchable_parts(tree_root, scope=scope):
        ...
```

Default `scope=None` preserves call-site back-compat for tests that
don't pass scope.

## 8. Reviews

This is a `[LIGHT]` task — single Sarcasmotron code-review pass after
implementation. No separate task-reviewer / plan-reviewer steps.

## 9. References

- TASK 006 §9 §11.1 — original deferral rationale.
- TASK 006 RTM R5 — part-walker scope (now configurable).
- ARCH 006 §F2 — `_iter_searchable_parts` design (now extended with `scope` param).
- backlog row `docx-6.7` — `docs/office-skills-backlog.md`.

---

> **TASK status (2026-05-12):** **DRAFT v1** — pre-implementation.
> Light Mode: skips task-reviewer + architect + planner. Implementer
> goes direct to `/light-02-develop-task`.
