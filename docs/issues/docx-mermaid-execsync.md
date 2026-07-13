---
id: DOCX-MERMAID-EXECSYNC
type: known-issue
status: open
opened_at: 2026-06-05
category: security
severity: LOW
component: docx
slug: docx-mermaid-execsync
auto_fixable: true
---

# DOCX-MERMAID-EXECSYNC (pre-existing; surfaced by TASK 019 vdd-multi)

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
