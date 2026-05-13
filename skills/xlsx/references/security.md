# xlsx-8 / xlsx-8a — Security model & trust boundary

> **office-skills assume trusted workbook input AND non-multi-tenant
> output directory.**

This document is the canonical statement of the security
assumptions, accepted-risk catalogue, and the parent-symlink +
TOCTOU race that this iteration **does not** code-fix. It is
authored by `xlsx-8a-05` (TASK 011) and cross-linked from
[`SKILL.md`](../SKILL.md) and from `docs/ARCHITECTURE.md` §14.7 /
§15.4 of the repository root.

---

## 1. Trust boundary statement

The four office skills (`docx`, `xlsx`, `pptx`, `pdf`) are
**workstation-grade office automation tools**, not multi-tenant
SaaS components. The threat model assumes:

- **Trusted workbook input**: the operator either authored the
  workbook or obtained it from a trusted source (vendor, internal
  pipeline, signed-and-verified upload). Maliciously-crafted
  OOXML payloads (XXE, zip-bomb, fake `<dimension>` declaring
  17B cells, hand-rolled `<mergeCell>` x 1M, etc.) are
  defence-in-depth-mitigated where cheap (caps in
  `xlsx_read/_tables.py` and `xlsx_read/_merges.py`) but the
  primary defence is **input provenance**.
- **Non-multi-tenant output directory**: the path passed to
  `--output` or `--output-dir` is owned by the same user as the
  invoking process, and no other principal on the system has
  write access to its parent chain. Multi-tenant CI runners,
  shared `/tmp` farms, and worker pools where adversarial
  tenants control `output_dir`'s parents are **out of scope**.

If your deployment context violates either of these assumptions —
notably **shared CI runners** or **multi-tenant build farms** —
read §3 below before enabling xlsx-8 / xlsx-8a there.

---

## 2. What is and is not closed by xlsx-8a

xlsx-8a (TASK 011, eight atomic sub-tasks) is a **production
hardening** layer on top of xlsx-8. It closes 5 of 7 catalogued
deferred items, narrows 1, and documents 1 (this section). See
`docs/ARCHITECTURE.md` §15 for the full decision record.

### Closed by xlsx-8a (code-fix landed)

- **Sec-HIGH-3 (DoS — collision-suffix unbounded loop)** —
  `_emit_multi_region` collision-suffix loop in `emit_csv.py`
  bounded at `_MAX_COLLISION_SUFFIX = 1000` per region-set
  (xlsx-8a-01).
- **Sec-MED-3 (memory exhaustion — merge-count unbounded)** —
  `parse_merges(ws)` bounded at `_MAX_MERGES = 100_000` per sheet
  (xlsx-8a-02). Library-level `TooManyMerges` exception; shim
  maps to cross-5 envelope exit 2.
- **Sec-MED-2 (downstream XSS / RCE via `javascript:` / `data:`
  hyperlinks)** — `--hyperlink-scheme-allowlist CSV` defaults to
  `http,https,mailto`. Disallowed-scheme cells drop the URL and
  emit as bare scalar (JSON) or plain text (CSV). One stderr
  warning per distinct blocked scheme (xlsx-8a-03).
- **Sec-MED-1 (CSV formula injection on Excel double-click)** —
  `--escape-formulas {off,quote,strip}` defangs cells whose
  stringified value begins with one of the OWASP-canonical six
  sentinels (`=`, `+`, `-`, `@`, `\t`, `\r`). Default `off`
  preserves backward-compat; users opt-in for shared-spreadsheet
  workflows (xlsx-8a-04).
- **PERF-HIGH-1 (`_gap_detect` 8MB occupancy matrix per sheet)** —
  `_GAP_DETECT_MAX_CELLS` raised 1M → 50M; matrices switched to
  `bytearray` flat buffers (8× memory reduction); early-exit on
  empty claimed set (xlsx-8a-06). The
  [`docs/KNOWN_ISSUES.md`](../../../docs/KNOWN_ISSUES.md) entry
  is deleted by that bead's commit.

### Partially closed by xlsx-8a

- **PERF-HIGH-2 (JSON full-payload materialisation, 3 copies in
  RAM)** —
    - R9 / xlsx-8a-07 drops the `json.dumps` string-buffer copy
      for file output (~300-500 MB savings on 3M-cell payloads).
    - R10 / xlsx-8a-08 streams the emit-side R11.1 single-region
      output (most common large-table case) row-by-row. **Design
      target**: peak RSS ≤ 200 MB on 3M cells vs. 1-1.5 GB in v1.
      **As-shipped honest-scope**: upstream `read_table` +
      `apply_merge_policy` still materialise the row grid (~180 MB
      on 3M cells), so realistic peak is ~400-600 MB — still a
      2-3× win over v1, not the 200 MB design target. Budget is
      unmeasured at the 3M-cell scale in xlsx-8a's test suite;
      tracked in [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md)
      §15.10.6 and [`docs/KNOWN_ISSUES.md`](../../../docs/KNOWN_ISSUES.md)
      PERF-HIGH-2.
    - **Residual**: R11.2-4 multi-sheet / multi-region JSON
      shapes still build the full `shape` dict in memory. Future
      `xlsx-8c-multi-sheet-stream` refactors per-sheet streaming
      if a real R11.2 large-table workload emerges.

### Documented only (NOT code-fixed)

- **Sec-HIGH-1 (TOCTOU race in `_emit_multi_region`)** — this
  document is the deferral carrier. Detail in §3 below.

### Still accepted (not addressed by xlsx-8a, no follow-up ticket)

- **§14.7.1 Unicode-norm bypass in path validator** — sheet names
  with NFKC-folding aliases of `..` (e.g. `․․` U+2024
  one-dot-leader, `．．` U+FF0E fullwidth full stop) can pass
  the ASCII `_FORBIDDEN_NAMES` reject in
  `dispatch._validate_sheet_path_components`. The
  defence-in-depth path-traversal guard
  (`Path.resolve().is_relative_to(output_dir)`) catches the
  resulting path; the first-line defence has a gap. Accepted
  because (a) v1 scope is macOS / Linux desktop, where
  Windows-style filename confusion has reduced exploit utility;
  (b) defence-in-depth still works; (c) workbook authors can
  already produce filename-confused output through other
  channels (zip-bomb attempts, etc.) on hostile inputs.

---

## 3. Sec-HIGH-1 — TOCTOU race in `_emit_multi_region`

### 3.1. Where

[`skills/xlsx/scripts/xlsx2csv2json/emit_csv.py`](../scripts/xlsx2csv2json/emit_csv.py)
function `_emit_multi_region` (around lines 144-181). The
sequence:

```python
output_dir = output_dir.resolve()                       # (1)
output_dir.mkdir(parents=True, exist_ok=True)           # (2)

for i, (sheet_name, region, table_data, hl_map) in enumerate(payloads_list):
    region_name = region.name or f"Table-{i + 1}"
    target = (output_dir / sheet_name / f"{region_name}.csv").resolve()  # (3)
    if not target.is_relative_to(output_dir):
        raise OutputPathTraversal(...)
    # ... collision-suffix loop ...
    target.parent.mkdir(parents=True, exist_ok=True)    # (4)
    with target.open("w", ...) as fp:                   # (5)
        ...
```

### 3.2. The race

Between (1) and (2), and again between (4) and (5), an attacker
with write access to a parent of `output_dir` (the operator's
home dir, `/tmp`, etc.) can plant a symlink that redirects the
write to a different filesystem location.

- (1) → (2): if the resolved `output_dir` does not exist yet,
  `mkdir(parents=True, exist_ok=True)` walks each missing parent
  component and creates it. If an adversary plants a symlink at
  one of those parent positions between (1)'s `.resolve()` and
  (2)'s `mkdir`, the `mkdir` walks the symlink. The follow-up
  `is_relative_to` guard at (3) catches the resulting path
  (because `.resolve()` follows the planted symlink and the
  resolved target falls outside the `output_dir` namespace) —
  but **parent-dir mutation may have already happened** (a new
  directory entry was created via the symlink, with the
  attacker-chosen permissions).
- (4) → (5): same window. The attacker swaps `target.parent`'s
  parent for a symlink between (4)'s second `mkdir` and (5)'s
  `open("w")`. `target.open("w")` follows the swap and writes
  the CSV content to an attacker-chosen location, with the
  invoking user's permissions.

### 3.3. When this becomes critical

- **Multi-tenant CI runner**: tenant A's pre-step plants a
  symlink in `/tmp/xlsx-output/` before tenant B's xlsx-8a run.
  Tenant B's CSV writes land in tenant A's controlled directory.
- **Multi-tenant build farm** with shared `output_dir` between
  jobs.
- **Shared `/tmp`** with multiple users / processes that can
  observe and react to a target's `_emit_multi_region` call
  pattern.

### 3.4. When this is NOT critical

- **Single-tenant desktop**: the operator is the only principal
  with write access to `~/`, `/tmp`, etc. — no adversary in the
  loop. Current documented scope.
- **Per-user CI workdir**: `~/build/.../tmp/xlsx-output/` is
  created fresh per branch / per run; no other principal can
  race against it.
- **Dedicated container with non-shared `/tmp`**: container
  filesystem is private; no cross-tenant write.

### 3.5. Fix recipe (deferred)

The canonical Unix mitigation is `os.open(..., O_NOFOLLOW)`
applied per path component during the walk. Sketch (NOT shipped
in xlsx-8a; tracked as a future ticket — suggested slug:
`xlsx-8d-o-nofollow`):

```python
# Walk each path component, opening with O_NOFOLLOW;
# if any segment is a symlink, fail loud.
import os
from pathlib import Path

def _open_o_nofollow_write(path: Path) -> int:
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
        return os.open(
            parts[-1],
            os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW,
            mode=0o644,
            dir_fd=dir_fd,
        )
    finally:
        os.close(dir_fd)
```

### 3.6. Platform variance

- **POSIX (Linux / macOS)**: `os.O_NOFOLLOW` available; `dir_fd=`
  on `os.open` requires Python 3.3+ and a system call surface
  that all current targets support.
- **Windows**: `O_NOFOLLOW` does not apply. The Windows analogue
  is `CreateFile` with `FILE_FLAG_OPEN_REPARSE_POINT`, accessed
  in Python via `ctypes` or the `pywin32` extension. Implementing
  both branches under one helper roughly doubles the LOC budget
  and the test matrix.

Estimated effort: **~40 LOC core + per-platform conditional +
two unit tests + one CI matrix entry that actually plants
symlinks** (the test matrix is the expensive part — runners
need to be able to plant symlinks and assert that the helper
refuses to walk them, which requires `chmod`-friendly fixtures).

---

## 4. Cross-references

- [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md) §7
  (xlsx-8 threat model) and §14.7 (accepted-risk catalogue).
- [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md) §15
  (xlsx-8a decision record); specifically §15.4 (status table for
  §14.7 closures).
- [`docs/TASK.md`](../../../docs/TASK.md) UC-05 (xlsx-8a-05 task
  spec).
- [`docs/KNOWN_ISSUES.md`](../../../docs/KNOWN_ISSUES.md) —
  perf-axis residuals after xlsx-8a-06/07/08.

---

## 5. Reporting security issues

If you observe behaviour that contradicts the assumptions in §1
on a **legitimate** workload (i.e. trusted workbook + non-multi-
tenant output dir), open a backlog row prefixed `xlsx-sec-*` and
reference this document. If you observe an exploitable issue
that fits inside the §1 trust model (e.g. a path-traversal bypass
that survives `is_relative_to(output_dir)`), treat it as a
priority bug — the trust-boundary assumes those defences hold.
