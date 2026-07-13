---
id: DOCX-MERMAID-EXECSYNC
type: known-issue
status: fixed
opened_at: 2026-06-05
resolved_at: 2026-07-13
resolved_by: heal-issues run 2026-07-13 (branch fix/docx-mermaid-execsync)
category: security
severity: LOW
component: docx
slug: docx-mermaid-execsync
auto_fixable: true
---

# DOCX-MERMAID-EXECSYNC (pre-existing; surfaced by TASK 019 vdd-multi)

> **Resolved 2026-07-13 by /heal-issues (manual pilot run #2).** Mermaid rendering now runs
> inside a per-diagram `fs.mkdtempSync(os.tmpdir())` scratch (removed in `finally` on both
> success and failure) and the command is `execFileSync('npx', [...argv])` — no shell string,
> no predictable names, nothing in the CWD. Regression tests:
> `tests/test_md2docx_mermaid_hygiene.py` (failure path via stubbed npx: CWD clean + docx
> still produced). Gates: issue repro green, unit 206 OK, e2e 155/155, validate_skill PASSED;
> success path smoke-verified with a real mermaid render (PNG embedded, CWD clean).

**Status:** DEFERRED (LOW; pre-existing, out of TASK 019 scope).
**Severity:** LOW (not exploitable under the single-tenant local-CLI trust model).
**Location:** [`skills/docx/scripts/md2docx.js`](../../skills/docx/scripts/md2docx.js) Mermaid
branch (`execSync(\`npx -y @mermaid-js/mermaid-cli -i ${mmdFile} -o ${pngFile} ...\`)`).
**Symptom:** Mermaid temp files use predictable sequential names (`temp_1.mmd`,
`temp_1.png`, …) created in the **current working directory**, and the render command is
built as a shell string passed to `execSync`.
**Why LOW / not fixed in TASK 019:** the interpolated values (`mmdFile`/`pngFile`) are
derived from an integer counter — **no user input flows into the shell line**, so there is
no command-injection vector. The predictable-name-in-CWD angle is a symlink-pre-plant
concern only in a shared/multi-tenant CWD, which the office-skills trust model excludes.
The TASK 019 spec (§6) explicitly says **"do not touch the Mermaid rendering logic"**, so
hardening it was out of scope. Flagged by the TASK 019 `/vdd-multi` adversarial pass.
**Fix path (when prioritised):** (1) render into a `mkstemp`/`fs.mkdtemp` scratch dir
instead of CWD; (2) switch the `execSync` string to the argv-array form
(`execFileSync('npx', [...])`) to remove the shell entirely. Both are mechanical and
behaviour-preserving.
**Do-not:** claim Mermaid temp-file hardening until this lands.

## Reproduction

No network, no mermaid-cli: a stubbed failing `npx` is enough — the `.mmd` is written into the
CWD *before* the exec and its `unlinkSync` sits after the exec inside the `try`, so the temp
leaks. Exits non-zero while the leak exists; 0 once rendering uses a scratch dir.

````sh
REPO="$(git rev-parse --show-toplevel)"
cd "$(mktemp -d)"
mkdir stub && printf '#!/bin/sh\nexit 1\n' > stub/npx && chmod +x stub/npx
printf '# t\n\n```mermaid\ngraph TD; A-->B;\n```\n' > t.md
PATH="$PWD/stub:$PATH" node "$REPO/skills/docx/scripts/md2docx.js" t.md out.docx >/dev/null 2>&1 || true
test ! -e temp_1.mmd
````
