# Task 019-06 [INTEGRATION]: dogfood on real doc + fixture promotion + final gates

> **Predecessor:** 019-01…05.
> **RTM:** completes [F2][F3]; final verification of DoD-1…9.
> **ARCH:** §11 bead 019-06; TASK §8 dogfooding.

## Goal
Prove the fix resolves the **original pain** on the real document that produced the spec,
promote the dogfood input to a permanent fixture, register the backlog row, and run the
full final gate.

## Steps

### F2 — dogfood (exactly the flow that used to require a manual zip-patch)
```bash
cd skills/docx
node scripts/md2docx.js ../../tmp7/dogfood-integration-arch.md /tmp/dogfood-A4.docx --page-size A4
python3 -c "import zipfile,re; print(re.findall(r'<w:pgSz[^>]*>', zipfile.ZipFile('/tmp/dogfood-A4.docx').read('word/document.xml').decode()))"
# expect: 11906×16838
python3 scripts/office/validate.py /tmp/dogfood-A4.docx           # OK
python3 scripts/preview.py /tmp/dogfood-A4.docx /tmp/dogfood-A4.jpg --cols 2
```
**Acceptance (TASK §8):** zero manual workarounds; all 3 Mermaid diagrams present &
legible (visual `preview.py`); wide tables (ports, availability calc, conformance matrix)
inside A4 margins; `pgSz` + diagram/table count match `tmp7/dogfood-integration-arch-A4.golden.docx`
(byte-equality NOT required — Mermaid PNG non-deterministic); the same `.md` without
`--page-size` ⇒ Letter `12240×15840`.

Golden compare helper (counts + pgSz, not bytes):
```bash
python3 - <<'PY'
import zipfile, re
def info(p):
    xml = zipfile.ZipFile(p).read('word/document.xml').decode()
    z = zipfile.ZipFile(p)
    imgs = [n for n in z.namelist() if n.startswith('word/media/')]
    return (re.findall(r'<w:pgSz[^>]*>', xml), xml.count('<w:tbl>'), len(imgs))
print("A4 :", info('/tmp/dogfood-A4.docx'))
print("GLD:", info('../../tmp7/dogfood-integration-arch-A4.golden.docx'))
PY
```

### F3 — promote fixture (⬜ non-MVP)
- `cp ../../tmp7/dogfood-integration-arch.md examples/fixture-mermaid-a4.md`.
- Reference the golden under `scripts/tests/` (e.g. a small regression test that runs
  `md2docx.js examples/fixture-mermaid-a4.md … --page-size A4` and asserts pgSz +
  tbl/diagram counts vs a committed expectation — NOT byte-equality).
- The permanent test must NOT depend on `tmp7/` (repo-root scratch).

### Backlog + final gate
- Register `docx-9` in `docs/office-skills-backlog.md` → flip to ✅ DONE with this task ref.
- Final validation:
  ```bash
  find skills -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
  diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
  diff -qr skills/docx/scripts/office skills/pptx/scripts/office
  for s in xlsx pptx pdf; do diff -q skills/docx/scripts/_venv_bootstrap.py skills/$s/scripts/_venv_bootstrap.py; diff -q skills/docx/scripts/preview.py skills/$s/scripts/preview.py; done
  for s in xlsx pptx; do diff -q skills/docx/scripts/office_passwd.py skills/$s/scripts/office_passwd.py; done
  for s in docx xlsx pptx pdf; do python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/$s; done
  ```
- Update `scripts/.AGENTS.md` (docx) with the 019 chain summary (Developer single-writer).

## Acceptance Criteria (DoD-1…9 roll-up)
- [ ] DoD-9 dogfood: one-command A4, zero workarounds, golden pgSz + count parity.
- [ ] DoD-1 (A4 pgSz+validate), DoD-2/3 (interpreter), DoD-4 (docs), DoD-5 (install),
  DoD-6 (Letter compat), DoD-7 (replication diffs + 4× validate), DoD-8 (tests) — all green.
- [ ] `examples/fixture-mermaid-a4.md` committed; permanent A4 regression test green and
  `tmp7`-independent.
- [ ] `docs/office-skills-backlog.md` `docx-9` → DONE; `scripts/.AGENTS.md` updated.

## Notes
- If the dogfood preview reveals residual overflow (e.g. an image whose intrinsic width >
  A4 content), that is a real B4 bug → fix in 019-03 and re-run, not a doc caveat.
