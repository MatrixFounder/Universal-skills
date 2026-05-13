# Task 011.05 — [R5] Trust-boundary documentation (`references/security.md`)

## Use Case Connection
- UC-05: Trust-boundary docs landed (`xlsx-8a-05`)

## Task Goal
Ship a new `skills/xlsx/references/security.md` that documents the
trust-boundary assumptions of `xlsx-8` and `xlsx-8a`, with explicit
honest-scope on the parent-symlink + TOCTOU race in
`_emit_multi_region` (ARCH §14.7.5 / Sec-HIGH-1) that this task
**does NOT** code-fix.

This is a **docs-only bead** — no code change, no test change.
The fix recipe (`os.open(..., O_NOFOLLOW)` per path component) is
sketched in the doc; the actual implementation is deferred to a
future ticket. Goal: make the limitation **visible** so a deployer
can decide whether to deploy in multi-tenant CI today.

## Changes Description

### New Files

- **`skills/xlsx/references/security.md`** — ≥ 80 lines of
  Markdown:
  - **Trust-boundary statement (verbatim)**: "office-skills assume
    **trusted workbook input AND non-multi-tenant output directory**."
    This sentence MUST appear (grep-gated).
  - **Section: "What is and is not closed by xlsx-8a"** —
    summarises:
    - Closed: Sec-HIGH-3 (collision-suffix DoS), Sec-MED-1 (CSV
      injection), Sec-MED-2 (hyperlink scheme abuse), Sec-MED-3
      (merge-count DoS), PERF-HIGH-1 (gap-detect matrix size).
    - Closed for R11.1: PERF-HIGH-2 (JSON full-payload).
    - Narrowed: PERF-HIGH-2 for R11.2-4 (multi-sheet shapes).
    - Documented only: Sec-HIGH-1 (this doc).
    - Still accepted: ARCH §14.7.1 Unicode-norm bypass in path
      validator.
  - **Section: "Sec-HIGH-1 TOCTOU race — narrative"** — explains:
    - Where: [`emit_csv._emit_multi_region`](../../skills/xlsx/scripts/xlsx2csv2json/emit_csv.py#L144).
    - The sequence: `output_dir.resolve()` →
      `output_dir.mkdir(parents=True, exist_ok=True)` →
      per-region `target.resolve()` → `target.is_relative_to(output_dir)`
      check → `target.parent.mkdir(parents=True, exist_ok=True)`
      → `target.open("w")`.
    - The race: a local attacker with write access to a parent
      of `output_dir` can plant a symlink between the
      `output_dir.resolve()` and the `mkdir(parents=True)` calls.
      The `mkdir` walks the symlink; subsequent `is_relative_to`
      catches the result, but parent-dir mutation may already have
      happened.
  - **Section: "When this becomes critical"** — names the
    deployment scenarios:
    - Shared CI runner (e.g. self-hosted GitHub Actions box where
      tenant A's pre-step plants a symlink in `/tmp/xlsx-output/`
      before tenant B's xlsx-8a run).
    - Multi-tenant build farm with shared `output_dir`.
    - **NOT critical**: single-tenant desktop / per-user CI workdir
      (`~/build/.../tmp/xlsx-output/` per branch) — current
      documented scope.
  - **Section: "Fix recipe (deferred)"** — sketches the
    `os.open(..., O_NOFOLLOW)` per-component approach:
    ```python
    # Sketch — NOT shipped in xlsx-8a; tracked as a future ticket.
    import os
    def _open_o_nofollow(path: Path, mode: int = 0o644) -> int:
        # Walk each path component, opening with O_NOFOLLOW;
        # if any segment is a symlink, fail loud.
        parts = path.parts
        dir_fd = os.open(parts[0], os.O_RDONLY)
        try:
            for part in parts[1:-1]:
                try:
                    new_fd = os.open(
                        part,
                        os.O_RDONLY | os.O_NOFOLLOW,
                        dir_fd=dir_fd,
                    )
                except OSError as exc:
                    raise OutputPathTraversal(
                        f"O_NOFOLLOW failed at {part!r}"
                    ) from exc
                os.close(dir_fd)
                dir_fd = new_fd
            # Open the final file relative to the verified dir_fd.
            return os.open(
                parts[-1],
                os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW,
                mode=mode,
                dir_fd=dir_fd,
            )
        finally:
            os.close(dir_fd)
    ```
    Platform variance: `O_NOFOLLOW` is POSIX (Linux/macOS); Windows
    has its own `FILE_FLAG_OPEN_REPARSE_POINT`. Estimated ~40 LOC
    + platform-conditional branch + 2 tests + a CI matrix that
    actually plants symlinks (not trivial).
  - **Section: "Cross-references"** —
    - [`docs/ARCHITECTURE.md` §14.7.5](../../../docs/ARCHITECTURE.md)
      (the canonical accepted-risk entry).
    - [`docs/TASK.md` UC-05](../../../docs/TASK.md) (the task
      requirement).

### Changes in Existing Files

#### File: `skills/xlsx/SKILL.md`

**Add cross-link line** — in the xlsx-8 section (or near the
top of the file if no dedicated section exists), append a one-line
cross-link:
- `> **Security**: see [`references/security.md`](references/security.md)
  for trust-boundary, accepted-risk catalogue, and the TOCTOU
  race honest-scope.`

#### File: `docs/ARCHITECTURE.md`

**Add cross-link in §14.7.5 row** (the TOCTOU accepted-risk item)
and §15.4 status table — append " See [`skills/xlsx/references/security.md`](../skills/xlsx/references/security.md)."
to the existing narrative.

### Component Integration
None (docs-only).

## Test Cases

### End-to-end Tests
None applicable (docs-only).

### Unit Tests
None applicable.

### Regression / Grep Gates

1. **TC-GREP-01:**
   ```bash
   grep -F "trusted workbook input AND non-multi-tenant" \
       skills/xlsx/references/security.md
   ```
   Must return exactly 1 line (the verbatim trust-boundary sentence).

2. **TC-GREP-02:**
   ```bash
   wc -l skills/xlsx/references/security.md
   ```
   Must report ≥ 80 lines.

3. **TC-GREP-03:**
   ```bash
   grep -F "references/security.md" skills/xlsx/SKILL.md
   ```
   Must return ≥ 1 line (cross-link presence).

4. **TC-GREP-04:**
   ```bash
   grep -F "references/security.md" docs/ARCHITECTURE.md
   ```
   Must return ≥ 1 line.

5. **TC-MD-LINT:**
   ```bash
   markdown-lint skills/xlsx/references/security.md
   ```
   (Optional — only if markdownlint is wired into CI; otherwise
   skip.)

## Acceptance Criteria
- [ ] `skills/xlsx/references/security.md` exists, ≥ 80 lines.
- [ ] All 4 mandatory grep-gates green.
- [ ] `SKILL.md` cross-link line present.
- [ ] `ARCHITECTURE.md` §14.7.5 + §15.4 cross-link line present.
- [ ] `validate_skill.py skills/xlsx` exit 0.
- [ ] 12-line cross-skill `diff -q` gate from ARCH §9.4 silent
  (auto-satisfied; no files in the replicated set —
  `office/`, `_soffice.py`, `_errors.py`, `preview.py`,
  `office_passwd.py` — are touched by this bead).

## Stub-First Pass Breakdown

This bead has no real "stub phase" — it's a docs write. The
two-pass collapses to one:

1. **Write the document** in full (use the structure above as the
   spec).
2. **Add the cross-links** to SKILL.md and ARCHITECTURE.md.
3. **Run all 4 grep-gates** locally before committing.

## Notes
- Effort: S (≤ 1.5 hours). Diff size: ~120 LOC new doc + 4 LOC
  cross-link additions across 2 files.
- The fix recipe code-sketch is **deliberately not runnable**
  Python — it's illustrative. The real implementation faces
  platform-variance issues that justify the deferral.
- Future ticket name: `xlsx-8d-o-nofollow` (suggested; not
  required to commit a backlog stub in this task — the
  `references/security.md` "Fix recipe (deferred)" section is the
  carrier).
