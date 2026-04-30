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
    m = re.search(r"^Pages:\s*(\d+)", out, re.MULTILINE)
    return int(m.group(1)) if m else 0


def _pdf_text(pdf: Path) -> str:
    return subprocess.run(
        ["pdftotext", str(pdf), "-"],
        capture_output=True, text=True, timeout=60,
    ).stdout


def _sample_needles(text: str, count: int) -> list[str]:
    """Pick `count` distinctive phrases from pdftotext output.

    Strategy: split on linebreaks, drop empty / short / all-numeric /
    all-whitespace lines, sort by length (longest first to favour
    sentences over headings), pick from positions 25%, 50%, 75% into
    the qualifying-line list to get spread across the document, take
    the first ~50 chars of each line as the needle.
    """
    lines = [
        ln.strip() for ln in text.splitlines()
        if ln.strip() and len(ln.strip()) > 20 and not ln.strip().isdigit()
    ]
    if not lines:
        return []
    # Sort by length desc; pick from positions {25%, 50%, 75%} of the
    # sorted list. Long lines first — sentences make better needles
    # than short headings ("On this page" / "Search").
    by_len = sorted(lines, key=len, reverse=True)[:max(count * 5, 15)]
    if len(by_len) < count:
        return [ln[:60] for ln in by_len]
    picks = [by_len[i * len(by_len) // count] for i in range(count)]
    return [ln[:60].strip() for ln in picks]


def _capture_one(src: Path, mode: str) -> dict | None:
    """Render `src` in `mode` ∈ {regular, reader}; return signature dict or None."""
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
        # Tolerance bands.
        page_slack = max(PAGE_SLACK, int(round(pages * PAGE_TOLERANCE_PCT)))
        size_slack = max(5, int(round(size_kb * SIZE_TOLERANCE_PCT)))
        return {
            "min_pages": max(1, pages - page_slack),
            "max_pages": pages + page_slack,
            "min_size_kb": max(1, size_kb - size_slack),
            "max_size_kb": size_kb + size_slack,
            "required_needles": needles,
            "forbidden_needles": [],
        }


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
        sig: dict = {"platform": _platform_guess(f.name)}
        for mode in ("regular", "reader"):
            entry = _capture_one(f, mode)
            if entry is None:
                print(f"  ! {mode}: capture FAILED — entry will be empty",
                      file=sys.stderr)
                sig[mode] = None
            else:
                sig[mode] = entry
                print(
                    f"  {mode}: pages={entry['min_pages']}–{entry['max_pages']}, "
                    f"size={entry['min_size_kb']}–{entry['max_size_kb']}kB, "
                    f"needles={len(entry['required_needles'])}"
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
