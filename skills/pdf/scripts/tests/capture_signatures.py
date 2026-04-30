#!/usr/bin/env python3
"""Capture html2pdf regression signatures from `tmp/` fixtures.

Walks the project's `tmp/` directory for `.html` / `.htm` / `.mhtml` /
`.mht` / `.webarchive` files, runs `html2pdf.py` against each in BOTH
regular and reader modes, and emits a JSON snapshot with the values
needed for `test_battery.py` to detect regressions:

  * page count → tolerance band (min/max)
  * file size  → tolerance band (min/max kB)
  * `required_needles` — small set of stable text strings sampled from
    pdftotext output (long, distinctive phrases that won't change
    between runs)
  * `forbidden_needles` — empty in the captured baseline; the
    maintainer hand-fills these per platform after capture, listing
    chrome / sidebar / nav / ad strings that MUST NOT appear in the
    output (the high-value chrome-leakage detector)

Usage:

    # First run — capture everything currently in tmp/:
    python3 tests/capture_signatures.py

    # On rerun — only ADD entries for new fixtures (do not refresh
    # existing baselines without explicit consent):
    python3 tests/capture_signatures.py

    # Force a full refresh (use after intentional preprocessing changes):
    python3 tests/capture_signatures.py --refresh

Output: writes `tests/battery_signatures.json` next to this script.
The .webarchive / .mhtml files themselves stay in `tmp/` (gitignored);
only the JSON is committed.

NB on tolerance: page count uses `±5%` rounded to nearest, with a hard
floor of 1 page slack on each side (small docs swing on font-version
drift). File size uses `±10%` — text density bounces more than page
count.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
SKILL_ROOT = SCRIPTS.parent
REPO_ROOT = SKILL_ROOT.parent.parent          # …/Universal-skills/
TMP_DIR = REPO_ROOT / "tmp"
SIGNATURES_PATH = HERE / "battery_signatures.json"

INPUT_EXTS = (".html", ".htm", ".mhtml", ".mht", ".webarchive")

# Render budget for the capture run. Mirror what test_battery.py uses.
CAPTURE_TIMEOUT = 90

# Page count tolerance: ±5% with at least 1 page slack each side.
PAGE_TOLERANCE_PCT = 0.05
PAGE_SLACK = 1

# File size tolerance: ±10%.
SIZE_TOLERANCE_PCT = 0.10

# How many "needle" phrases to sample per fixture/mode. Distinctive
# 30-80 char chunks scrubbed from pdftotext, picked from positions that
# are likely to land on body content (not edge chrome).
REQUIRED_NEEDLE_COUNT = 3


def _platform_guess(fixture_name: str) -> str:
    """Crude platform inference from filename — set once, then user edits."""
    n = fixture_name.lower()
    if "fern" in n:                 return "fern"
    if "mintify" in n or "mintlify" in n: return "mintlify"
    if "gitbook" in n:              return "gitbook"
    if "confluence" in n:           return "confluence"
    if "хабр" in n or "habr" in n:  return "habr"
    if "vc.ru" in n:                return "vcru"
    if "обзор" in n:                return "mobile-review"
    if "discord" in n:              return "discord"
    if "berachain" in n:            return "berachain"
    if "claude code" in n or "anthropic" in n or "jetbrains" in n:
        return "anthropic-mintlify"
    return "unknown"


def _run_html2pdf(src: Path, dst: Path, *, reader: bool) -> int:
    """Run html2pdf.py on src→dst; return exit code."""
    cmd = [
        sys.executable, str(SCRIPTS / "html2pdf.py"),
        str(src), str(dst),
        "--timeout", str(CAPTURE_TIMEOUT),
    ]
    if reader:
        cmd.append("--reader-mode")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=CAPTURE_TIMEOUT + 30,
        )
        return proc.returncode
    except subprocess.TimeoutExpired:
        return 124


def _pdf_page_count(pdf: Path) -> int:
    out = subprocess.run(
        ["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=30,
    ).stdout
    # No leading-line anchor — some Poppler builds prefix with whitespace.
    m = re.search(r"Pages:\s*(\d+)", out)
    return int(m.group(1)) if m else 0


def _pdf_text(pdf: Path) -> str:
    return subprocess.run(
        ["pdftotext", str(pdf), "-"],
        capture_output=True, text=True, timeout=60,
    ).stdout


# Minimum needle length. Below this, sampling falls back to whatever
# the document offers; the test_battery harness will treat under-needle'd
# fixtures as low-coverage but not auto-fail.
_NEEDLE_MIN_LEN = 25
# Maximum needle length. Pick at the next whitespace boundary AT OR AFTER
# this position so we never cut a word in half (which would produce
# needles like "...прод" that mismatch on the next render).
_NEEDLE_TARGET_LEN = 60


def _truncate_at_word(line: str, target: int) -> str:
    """Trim `line` to roughly `target` chars, ending on a word boundary."""
    if len(line) <= target:
        return line.rstrip()
    # Find next whitespace at or after `target`. If none found, cut at
    # the last whitespace BEFORE `target` (avoids mid-word cut). If still
    # none, fall back to the hard target (single long token).
    idx = line.find(" ", target)
    if idx == -1:
        idx = line.rfind(" ", 0, target)
    if idx == -1:
        idx = target
    return line[:idx].rstrip()


def _sample_needles(text: str, count: int) -> list[str]:
    """Pick `count` distinctive phrases from pdftotext output.

    Strategy: split on linebreaks, drop empty / short / all-numeric /
    all-whitespace lines, sort by length (longest first to favour
    sentences over headings), pick from positions 25%, 50%, 75% into
    the qualifying-line list to get spread across the document. Each
    picked needle is truncated at a WORD BOUNDARY at/after ~60 chars
    (no mid-word cuts → stable across font drift) AND must be at least
    25 chars after truncation (otherwise it's filtered out — too-short
    needles are noise like "1 / 5" page numbers).
    """
    lines = [
        ln.strip() for ln in text.splitlines()
        if ln.strip() and len(ln.strip()) > 20 and not ln.strip().isdigit()
    ]
    if not lines:
        return []
    by_len = sorted(lines, key=len, reverse=True)[:max(count * 5, 15)]
    if len(by_len) < count:
        candidates = by_len
    else:
        candidates = [by_len[i * len(by_len) // count] for i in range(count)]
    needles = [_truncate_at_word(ln, _NEEDLE_TARGET_LEN) for ln in candidates]
    return [n for n in needles if len(n) >= _NEEDLE_MIN_LEN]


def _capture_one(src: Path, mode: str, *, prev: dict | None = None) -> dict | None:
    """Render `src` in `mode` ∈ {regular, reader}; return signature dict or None.

    `prev` is the previous entry for this fixture/mode if one exists in
    the JSON. Used to PRESERVE user-curated fields across `--refresh`:

      * `forbidden_needles` — hand-added chrome / sidebar / ad strings
        that must NOT appear in the rendered output. These are the
        highest-value chrome-leakage detectors per the regression-net
        plan; auto-refresh would silently nuke hours of curation.
      * Any field starting with `_` (e.g. `_canary`) — user annotations
        that the schema treats as opaque. Reserved namespace.

    Bands and `required_needles` ARE refreshed (they're the auto-captured
    parts that drift with content/font changes).
    """
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / f"capture-{mode}.pdf"
        rc = _run_html2pdf(src, pdf, reader=(mode == "reader"))
        if rc != 0 or not pdf.exists() or pdf.stat().st_size < 1024:
            print(
                f"  ! {mode}: render failed (rc={rc}, "
                f"pdf={'missing' if not pdf.exists() else f'{pdf.stat().st_size}B'})",
                file=sys.stderr,
            )
            return None
        pages = _pdf_page_count(pdf)
        size_kb = pdf.stat().st_size // 1024
        text = _pdf_text(pdf)
        needles = _sample_needles(text, REQUIRED_NEEDLE_COUNT)
        if len(needles) < 2:
            print(
                f"  ! {mode}: only {len(needles)} stable needle(s) sampled "
                "from rendered text — fixture has very little body content "
                "(or render failed silently). Hand-add `required_needles` "
                "in the JSON before relying on this baseline.",
                file=sys.stderr,
            )
        # Tolerance bands.
        page_slack = max(PAGE_SLACK, int(round(pages * PAGE_TOLERANCE_PCT)))
        size_slack = max(5, int(round(size_kb * SIZE_TOLERANCE_PCT)))
        entry: dict = {
            "min_pages": max(1, pages - page_slack),
            "max_pages": pages + page_slack,
            "min_size_kb": max(1, size_kb - size_slack),
            "max_size_kb": size_kb + size_slack,
            "required_needles": needles,
            "forbidden_needles": [],
        }
        # Preserve user-curated fields from previous capture (HIGH-4 fix).
        if prev is not None and isinstance(prev, dict):
            preserved_forbidden = prev.get("forbidden_needles", [])
            if preserved_forbidden:
                entry["forbidden_needles"] = preserved_forbidden
            for key, val in prev.items():
                if key.startswith("_"):
                    entry[key] = val
        return entry


def _load_existing() -> dict:
    if not SIGNATURES_PATH.exists():
        return {}
    try:
        return json.loads(SIGNATURES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"WARNING: could not parse existing {SIGNATURES_PATH.name}: {exc}",
              file=sys.stderr)
        return {}


def _save(data: dict) -> None:
    # Sort fixtures by filename for stable diffs.
    ordered = dict(sorted(data.items()))
    SIGNATURES_PATH.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--refresh", action="store_true",
        help="Refresh existing baselines (default: only ADD new fixtures).",
    )
    parser.add_argument(
        "--tmp-dir", default=str(TMP_DIR),
        help=f"Source directory (default: {TMP_DIR}).",
    )
    args = parser.parse_args(argv)

    tmp = Path(args.tmp_dir)
    if not tmp.is_dir():
        print(f"ERROR: tmp dir not found: {tmp}", file=sys.stderr)
        return 1

    if shutil.which("pdfinfo") is None or shutil.which("pdftotext") is None:
        print("ERROR: pdfinfo / pdftotext (Poppler) required.", file=sys.stderr)
        return 1

    fixtures = sorted(
        f for f in tmp.iterdir()
        if f.is_file() and f.suffix.lower() in INPUT_EXTS
    )
    if not fixtures:
        print(f"No fixtures with extensions {INPUT_EXTS} in {tmp}", file=sys.stderr)
        return 1

    existing = _load_existing()
    print(f"Found {len(fixtures)} fixture(s) in {tmp}")
    print(f"Existing baseline has {len(existing)} entries")
    if args.refresh:
        print("--refresh: ALL existing entries will be regenerated")

    new_or_refresh: list[Path] = []
    for f in fixtures:
        if f.name in existing and not args.refresh:
            print(f"skip   {f.name} (already in baseline)")
            continue
        new_or_refresh.append(f)

    if not new_or_refresh:
        print("Nothing to capture.")
        return 0

    for f in new_or_refresh:
        print(f"capture {f.name}")
        # Preserve previous platform field + any user-added top-level
        # `_*` annotations across --refresh (HIGH-4 fix).
        prev_full = existing.get(f.name) or {}
        sig: dict = {"platform": prev_full.get("platform", _platform_guess(f.name))}
        for key, val in prev_full.items():
            if key.startswith("_"):
                sig[key] = val
        for mode in ("regular", "reader"):
            prev_mode = prev_full.get(mode) if isinstance(prev_full, dict) else None
            entry = _capture_one(f, mode, prev=prev_mode)
            if entry is None:
                print(f"  ! {mode}: capture FAILED — entry will be empty",
                      file=sys.stderr)
                sig[mode] = None
            else:
                sig[mode] = entry
                forbidden_n = len(entry.get("forbidden_needles", []))
                print(
                    f"  {mode}: pages={entry['min_pages']}–{entry['max_pages']}, "
                    f"size={entry['min_size_kb']}–{entry['max_size_kb']}kB, "
                    f"needles={len(entry['required_needles'])}"
                    + (f", preserved {forbidden_n} forbidden" if forbidden_n else "")
                )
        existing[f.name] = sig

    _save(existing)
    print(f"\nWrote {SIGNATURES_PATH}")
    print("\nNext steps:")
    print("  1. Hand-add `forbidden_needles` per platform (chrome / sidebar / ad strings)")
    print("  2. Run: python3 -m unittest tests.test_battery")
    print("  3. Commit battery_signatures.json (the .webarchive files stay in tmp/)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
