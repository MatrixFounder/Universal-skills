# Task 019-05 [DOC]: `SKILL.md` + `docx-js-gotchas.md` reconciliation

> **Predecessor:** 019-03 (final flag names).
> **RTM:** completes [D1][D2][D3].
> **ARCH:** §2.1 FC-4, §5.4, §12 D-A4.

## Goal
Make the written contract match the code: align the Python invocation form, advertise the
new `md2docx.js` page-size flags, and fix the false `--size letter` claim in the gotchas
reference.

## Steps

### `SKILL.md`
1. **§7.2 (Install).** Add one line after the `install.sh` bullet (D-A4):
   > Python CLIs **self-bootstrap into `scripts/.venv`** — bare `python3 scripts/X.py` and
   > `./.venv/bin/python scripts/X.py` are equivalent; on a host where `python3` is not the
   > venv, the script re-execs itself into it. (If `.venv` is missing, the script prints
   > `run: bash scripts/install.sh` instead of a `ModuleNotFoundError`.)
   Keep the existing `python3 scripts/...` examples (now safe) — do NOT churn them to
   `.venv/bin/python` (D-A4).
2. **§4 Script Contract.** Add the `md2docx.js` flags to its command line:
   `node scripts/md2docx.js INPUT.md OUTPUT.docx [--header …] [--footer …] [--page-size A4|Letter] [--landscape] [--margins T,R,B,L]`.
3. **§7.3 (Creating .docx).** Replace the paragraph that says *"Page size and orientation
   are fixed (US Letter, portrait) — md2docx.js does not currently expose --size or
   --landscape flags. If the user needs A4 / landscape / custom margins, drop down to
   python-docx or unpack/edit…"* with the real capability: `--page-size A4` (default
   Letter, backward-compatible), `--landscape`, `--margins T,R,B,L` (dxa, optional `mm`),
   noting tables/images auto-fit the chosen page.
4. **§10 Quick Reference.** Add a row: `Markdown → A4 .docx | node scripts/md2docx.js in.md out.docx --page-size A4`.

### `references/docx-js-gotchas.md`
5. **Line 27** — replace the false *"`md2docx.js` accepts `--size letter`"* with
   *"`md2docx.js` accepts `--page-size A4|Letter` (default Letter) and sets `<w:pgSz>`
   accordingly."*
6. **Lines 9-13** ("Page size defaults to A4") — keep the *library* fact (raw `docx-js`
   defaults to A4) but clarify that `md2docx.js` explicitly emits **Letter by default** and
   exposes `--page-size` to switch.
7. **Lines 29-51** (Landscape) — align with the implemented `--landscape` (swaps pgSz dims;
   margins as-authored).

## Verification
```bash
grep -n "size letter" skills/docx/references/docx-js-gotchas.md   # → no match
grep -n "page-size"   skills/docx/SKILL.md skills/docx/references/docx-js-gotchas.md
python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/docx   # exit 0
```

## Acceptance Criteria
- [ ] `SKILL.md` §7.2 documents self-bootstrap; §4/§7.3/§10 document the page-size flags.
- [ ] `docx-js-gotchas.md` no longer claims a `--size` flag; the A4/landscape framing
  matches the implementation.
- [ ] `validate_skill.py skills/docx` exit 0 (frontmatter/sections/examples intact).
- [ ] No contradiction remains between `SKILL.md`, `install.sh`, and the code.

## Notes
- `SKILL.md` / `gotchas.md` are **docx-only** (not replicated).
