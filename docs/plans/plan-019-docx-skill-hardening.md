# PLAN — TASK 019 `docx-skill-hardening`

> Decomposition of [`docs/TASK.md`](TASK.md) + [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)
> §11 into atomic, Stub-First, RTM-linked beads. One RTM item → checklist item
> (feature-grouping prohibited). Replication is **in-bead** (CLAUDE.md §2 "same commit"):
> any bead editing a replicated master replicates + gates at its own close.

## Execution order & dependencies

```
019-01 (bootstrap helper) ──▶ 019-02 (wire + replicate)  ┐
019-03 (md2docx geometry) ───────────────────────────────┼─▶ 019-04 (install verify) ─▶ 019-05 (docs) ─▶ 019-06 (dogfood + final)
                                                          ┘
```
- 019-01 → 019-02 (helper must exist before wiring).
- 019-03 is independent of 01/02 (Node, separate surface) — but executed in-tree sequentially to keep replication coherent.
- 019-04 (smoke-test) depends on **both** 019-02 (`preview.py` self-bootstrap) and 019-03 (`md2docx.js`).
- 019-05 (docs) depends on 019-03 (final flag names).
- 019-06 (dogfood) depends on all.

## MVP gate

019-01…05 = MVP (the spec's Definition of Done §5 — headline scenario passes with zero
workarounds). 019-06 F3 (fixture promotion) is the only ⬜ non-MVP item.

---

## Phase 1 — Stub + RED tests

- [x] **019-01** `[A1][A2][A5]` Create `scripts/_venv_bootstrap.py` (stdlib-only
  `reexec_into_venv(requires=())`) + `scripts/tests/test_venv_bootstrap.py` (RED→GREEN:
  re-exec, venv-absent friendly-fail, already-in-venv no-op, import-chain idempotency).
  → [task-019-01](tasks/task-019-01-venv-bootstrap-helper.md)

## Phase 2 — Logic (Green) + replication + docs

- [x] **019-02** `[A3][A3b][A4][E1][E2][E3]` Wire the bootstrap prelude into the 10 docx
  **CLI entrypoints** (exclude `_soffice.py` + the 4 import-only helpers); **replicate**
  `_venv_bootstrap.py`+`preview.py` → xlsx/pptx/pdf and `office/*`+`office_passwd.py` →
  xlsx/pptx; `diff` gates + 4× `validate_skill` + per-skill suites.
  → [task-019-02](tasks/task-019-02-wire-bootstrap-replicate.md)
- [x] **019-03** `[B1][B2][B3][B4][B5][F1a][F1d]` `md2docx.js` page geometry: add
  `--page-size`/`--landscape`/`--margins` (+ reject unknown flags); derive
  `PageGeometry`; thread into pgSz/pgMar/table/image/Mermaid. Tests: A4 pgSz, no-overflow,
  Letter regression (pgSz+contentWidthDxa exact), landscape, margins, bad-flag.
  → [task-019-03](tasks/task-019-03-md2docx-page-geometry.md)
- [x] **019-04** `[C1][C2][C3]` `install.sh`: post-install dep-import verify
  (`Pillow`/`lxml`/`defusedxml`) + smoke-test (bare `python3` md2docx→preview→validate in
  a `mktemp` scratch, trap-cleaned; `die` on `ModuleNotFoundError`/non-zero).
  → [task-019-04](tasks/task-019-04-install-verify.md)
- [x] **019-05** `[D1][D2][D3]` Docs: `SKILL.md` (invocation note + page-size flags in
  §4/§7.2/§7.3/§10) + `references/docx-js-gotchas.md` (`--size`→`--page-size`, reconcile
  A4 framing + landscape).
  → [task-019-05](tasks/task-019-05-docs-reconcile.md)

## Phase 3 — Integration

- [x] **019-06** `[F2][F3]` Dogfood on `tmp7/dogfood-integration-arch.md` (one-command A4,
  golden parity), promote `examples/fixture-mermaid-a4.md` (F3), register backlog `docx-9`,
  final DoD-1…9 verification + 4-skill `validate_skill`.
  → [task-019-06](tasks/task-019-06-dogfood-final.md)

---

## RTM coverage check (every TASK requirement is in a bead)

| RTM | Bead | RTM | Bead |
|---|---|---|---|
| A1 | 01 | C1 | 04 |
| A2 | 01 | C2 | 04 |
| A3 | 02 | C3 | 04 |
| A3b | 02 | D1 | 05 |
| A4 | 02 | D2 | 05 |
| A5 | 01 | D3 | 05 |
| B1 | 03 | E1 | 02 |
| B2 | 03 | E2 | 02 |
| B3 | 03 | E3 | 02 |
| B4 | 03 | F1 | 01 (a/d→03, b/c/e→01/02) |
| B5 | 03 | F2 | 06 |
| | | F3 | 06 |

No RTM item is unassigned. F1 sub-features are split: F1a (A4 pgSz) + F1d (Letter
regression) land in 019-03; F1b/F1c/F1e (bootstrap behaviours) land in 019-01/02.

## Per-bead verification commands

- 019-01: `./.venv/bin/python -m unittest tests.test_venv_bootstrap -v`
- 019-02: bootstrap E2E + `diff -qr office` ×2 + `diff -q` preview/_venv_bootstrap ×3 + `office_passwd` ×2 + `validate_skill` ×4 + each skill's suite
- 019-03: `node md2docx.js … --page-size A4` pgSz check + Letter regression + `office/validate.py OK` + new md2docx tests
- 019-04: `bash scripts/install.sh` ends with smoke PASS; simulate a missing wheel → `die`
- 019-05: `validate_skill.py skills/docx` exit 0; grep gotchas has no `--size letter`
- 019-06: dogfood acceptance §8 + golden parity + `validate_skill` ×4
