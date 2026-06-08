# Development Plan: TASK 020 — pptx → Markdown converter (`pptx2md`)

> **Sources:** [`docs/TASK.md`](TASK.md) (RTM) + [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)
> (FC-1…FC-5, Data Model §4, §11 bead skeleton). Both VDD gates APPROVED
> ([task review](reviews/task-020-review.md), [arch review](reviews/architecture-020-review.md)).
> **Methodology:** Stub-First (`tdd-stub-first`) — Phase 1 = frozen surface + RED
> E2E/units that go green on stubs; Phase 2 = logic, assertions tightened.
> **Replication:** **none** (ARCH §9 EMPTY) — all new code under
> `skills/pptx/scripts/pptx2md/`; `_errors.py` + `office/_encryption.py` are imported
> read-only. Every bead asserts the cross-skill `diff -q` matrices stay silent.

---

## Package layout (frozen by 020-01)

```
skills/pptx/scripts/
├── pptx2md.py                 # NEW thin shim: _venv_bootstrap prelude + sys.path + re-export main
└── pptx2md/                   # NEW package (pptx-specific; NOT replicated)
    ├── __init__.py            # closed public surface: main, convert, _AppError subclasses
    ├── model.py               # dataclasses: Deck, Slide, Block union, MediaAsset, PlaceholderAsset, OcrResult
    ├── exceptions.py          # _AppError(CODE) hierarchy
    ├── cli.py                 # build_parser, _resolve_paths/_resolve_media_dir, main
    ├── extract.py             # assert_openable, build_deck (FC-1)
    ├── images.py              # materialise (FC-2)
    ├── ocr.py                 # probe, ocr_asset (FC-3, opt-in, lazy)
    ├── emit.py                # render_deck (FC-4)
    └── tests/                 # unit tests (model/extract/images/emit/ocr)
skills/pptx/scripts/tests/     # E2E (CLI end-to-end + dogfood) — existing dir
```

---

## Task Execution Sequence

### Stage 1 — Structure & Stubs (Phase 1: Red → Green on stubs)

- **Task 020-01 [STUB CREATION]** — package skeleton + shim + exceptions + CLI surface + RED tests
  - RTM: scaffolds Epic A/B/C/D/E; **completes** R-D2 (CLI contract), R-D4a (self-overwrite guard), exit-code map.
  - Use Cases: all (smoke); UC-3 self-overwrite path real.
  - Description File: [`docs/tasks/task-020-01-skeleton-cli-tests.md`](tasks/task-020-01-skeleton-cli-tests.md)
  - Priority: Critical · Dependencies: none

### Stage 2 — Core Logic (Phase 2: stubs → real, MVP)

- **Task 020-02 [LOGIC]** — `extract.py`: deck open + slide/shape/group walk → document model
  - RTM: **completes** R-A1, R-A2, R-A3, R-A4, R-A5 (extract side); R-D1 (notes); R-D3 (encrypted/legacy reject).
  - Use Cases: UC-1, UC-3, UC-5.
  - Description File: [`docs/tasks/task-020-02-extract-document-model.md`](tasks/task-020-02-extract-document-model.md)
  - Priority: Critical · Dependencies: 020-01

- **Task 020-03 [LOGIC]** — `images.py`: blob → sidecar media, sha1 dedup, naming, link base
  - RTM: **completes** R-B1, R-B2, R-B3.
  - Use Cases: UC-1 (+A2).
  - Description File: [`docs/tasks/task-020-03-images-sidecar-dedup.md`](tasks/task-020-03-images-sidecar-dedup.md)
  - Priority: High · Dependencies: 020-02

- **Task 020-04 [LOGIC]** — `emit.py` + `cli.main` glue: model → Markdown + atomic write **(MVP gate)**
  - RTM: **completes** R-A (emit side: headings/bullets/tables/links/notes/placeholders), R-D2 (output modes), R-D4 (atomic + InternalError exit 1).
  - Use Cases: UC-1, UC-5.
  - Description File: [`docs/tasks/task-020-04-emit-cli-glue.md`](tasks/task-020-04-emit-cli-glue.md)
  - Priority: Critical · Dependencies: 020-02, 020-03

### Stage 3 — OCR (Phase 2: opt-in, engine-soft-optional)

- **Task 020-05 [LOGIC]** — `ocr.py`: tesseract probe + per-image subprocess OCR + placement
  - RTM: **completes** R-C1, R-C2, R-C3, R-C4, R-C5.
  - Use Cases: UC-2, UC-4.
  - Description File: [`docs/tasks/task-020-05-ocr-per-image.md`](tasks/task-020-05-ocr-per-image.md)
  - Priority: High · Dependencies: 020-03, 020-04

### Stage 4 — Integration, Docs & Dogfood

- **Task 020-06 [INTEGRATION + DOC]** — SKILL.md, reference, notices, dogfood (6 decks), gates
  - RTM: **completes** R-E1, R-E2, R-E3, R-E4.
  - Use Cases: all (validation).
  - Description File: [`docs/tasks/task-020-06-docs-dogfood-integration.md`](tasks/task-020-06-docs-dogfood-integration.md)
  - Priority: High · Dependencies: 020-04 (MVP); 020-05 (OCR dogfood, engine-gated)

> **MVP gate = 020-01…04** (text + bullets + tables + sidecar images + notes converts
> the 4 text-rich tmp8 decks with zero workarounds). **020-05** is an MVP *flag* but
> engine-soft-optional — an `--ocr` run is engine-gated; if `tesseract` is absent on
> the dev host it is documented as pending (like pdf-4's composition gate).

---

## Use Case Coverage

| Use Case | Tasks |
|----------|-------|
| UC-1 — text-rich deck → md (no OCR) | 020-01, 020-02, 020-03, 020-04, 020-06 |
| UC-2 — `--ocr` recovers image text | 020-01, 020-05, 020-06 |
| UC-3 — encrypted/legacy rejected (exit 3) | 020-01 (guard scaffold), 020-02 (real) |
| UC-4 — OCR engine/lang missing (exit 1) | 020-05 |
| UC-5 — speaker-notes export | 020-02 (extract), 020-04 (emit) |

## RTM → Task Coverage

| RTM | Task | RTM | Task |
|-----|------|-----|------|
| R-A1 | 020-02 | R-C1 | 020-05 |
| R-A2 | 020-02 | R-C2 | 020-05 |
| R-A3 | 020-02 | R-C3 | 020-05 |
| R-A4 | 020-02/04 | R-C4 | 020-05 |
| R-A5 | 020-02/03/04 | R-C5 | 020-05/06 |
| R-B1 | 020-03 | R-D1 | 020-02/04 |
| R-B2 | 020-03/04 | R-D2 | 020-01/04 |
| R-B3 | 020-03 | R-D3 | 020-02 |
| | | R-D4 | 020-04 |
| R-E1 | 020-06 | R-E3 | 020-06 |
| R-E2 | 020-06 | R-E4 | 020-06 |

## Stub-First Phasing

- **Phase 1 (020-01):** frozen public surface (argparse, exit codes, exception
  hierarchy, dataclass shapes, function signatures) + RED E2E/unit scaffolding that
  passes on stubs (`--help` smoke, self-overwrite exit 6, constants locked, lazy-OCR
  import, encrypted-reject scaffold).
- **Phase 2 (020-02…05):** replace stubs module-by-module; **tighten** the 020-01
  assertions per `tdd-stub-first §2.4` (e.g. `main(...) == -999` sentinel → real exit
  codes; `--help`-only → real conversion output).
- **020-06:** docs reconciliation + 6-deck dogfood + `diff -q` + `validate_skill`.

## Global gates (every bead, at close)

```bash
# 1. cross-skill replication untouched (ARCH §9 — shared files imported read-only):
diff -q skills/docx/scripts/_errors.py            skills/pptx/scripts/_errors.py
diff -qr skills/docx/scripts/office               skills/pptx/scripts/office
# 2. structural validation:
python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/pptx   # exit 0
# 3. per-skill tests:
cd skills/pptx/scripts && ./.venv/bin/python -m unittest discover -s pptx2md/tests
cd skills/pptx/scripts && ./.venv/bin/python -m unittest discover -s tests
```
