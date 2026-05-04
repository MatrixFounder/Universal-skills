#!/usr/bin/env python3
"""Capture html2docx regression signatures.

Walks three fixture directories — `tests/tmp/` (gitignored real-world
fixtures), `examples/regression/` (committed synthetic edge cases),
and `tests/fixtures/platforms/` (committed platform slices) — runs
`html2docx.js` against each in BOTH regular and reader modes, and
emits a JSON snapshot for `test_battery.py`:

  * paragraph count → tolerance band (min/max)
  * file size → tolerance band (min/max kB)
  * `required_needles` — small set of stable text strings sampled
    from the body text (long, distinctive phrases that won't change
    between runs)
  * `forbidden_needles` — empty in the captured baseline; the
    maintainer hand-fills these per platform after capture, listing
    chrome / sidebar / nav / ad strings that MUST NOT appear in the
    output (the high-value chrome-leakage detector)

Mirrors `skills/pdf/scripts/tests/capture_signatures.py` (q-6) with
the `pages → paragraphs` substitution and the source-directory
auto-tagging (`source: "synthetic"` / `"platform"` / default `"tmp"`).

Usage:

    # First run — capture everything currently on disk:
    python3 tests/capture_signatures.py

    # Force a full refresh (use after intentional preprocessing changes):
    python3 tests/capture_signatures.py --refresh

    # Refresh a single fixture only:
    python3 tests/capture_signatures.py --fixture confluence-version-table.html

NB on tolerance: paragraph count uses ±5 % rounded to nearest, with a
hard floor of 2 paragraphs slack each side (one extra `<w:p>` between
blocks is a common no-op drift on minor preprocessing tweaks). File
size uses ±10 % — text density bounces more than paragraph count.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
SKILL_ROOT = SCRIPTS.parent

TMP_DIR = HERE / "tmp"
SYNTHETIC_DIR = SKILL_ROOT / "examples" / "regression"
PLATFORM_DIR = HERE / "fixtures" / "platforms"
SIGNATURES_PATH = HERE / "battery_signatures.json"

INPUT_EXTS = (".html", ".htm", ".mhtml", ".mht", ".webarchive")

CAPTURE_TIMEOUT = 120

# Paragraph count tolerance: ±5 % with at least 2 paragraphs slack each
# side. Two slack vs pdf's one — docx structure is finer-grained: a
# minor preprocessing tweak can add or remove a <w:p> between blocks
# without any visible content change.
PARA_TOLERANCE_PCT = 0.05
PARA_SLACK = 2

# File size tolerance: ±10 %.
SIZE_TOLERANCE_PCT = 0.10
SIZE_SLACK = 5

REQUIRED_NEEDLE_COUNT = 3

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def _platform_guess(fixture_name: str) -> str:
    """Crude platform inference from filename — set once, then user edits."""
    n = fixture_name.lower()
    if "fern" in n:                 return "fern"
    if "mintify" in n or "mintlify" in n: return "mintlify"
    if "gitbook" in n:              return "gitbook"
    if "confluence" in n:           return "confluence"
    if "хабр" in n or "habr" in n:  return "habr"
    if "vc.ru" in n or "vcru" in n: return "vcru"
    if "обзор" in n:                return "mobile-review"
    if "discord" in n:              return "discord"
    if "regression-" in n:          return "synthetic"
    return "unknown"


def _source_for(path: Path) -> str:
    """Return 'synthetic' / 'platform' / 'tmp' based on parent directory."""
    if path.parent == SYNTHETIC_DIR:
        return "synthetic"
    if path.parent == PLATFORM_DIR:
        return "platform"
    return "tmp"


def _run_html2docx(src: Path, dst: Path, *, reader: bool) -> int:
    """Run html2docx.js on src→dst; return exit code."""
    cmd = [
        "node", str(SCRIPTS / "html2docx.js"),
        str(src), str(dst),
        "--json-errors",
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


def _docx_paragraph_count_text_and_images(docx: Path) -> tuple[int, str, int]:
    """Returns (paragraph_count, body_text, image_count). q-7 HIGH-1:
    image count is captured to give the battery a tight signal for
    icon-strip regressions that size/paragraph bands swallow."""
    with zipfile.ZipFile(docx, "r") as zf:
        with zf.open("word/document.xml") as f:
            tree = etree.parse(f)
    root = tree.getroot()
    paras = root.findall(".//w:p", NS)
    runs = root.findall(".//w:t", NS)
    drawings = root.findall(".//w:drawing", NS)
    text = " ".join((r.text or "") for r in runs)
    return len(paras), text, len(drawings)


_NEEDLE_MIN_LEN = 25
_NEEDLE_TARGET_LEN = 60


def _truncate_at_word(line: str, target: int) -> str:
    if len(line) <= target:
        return line.rstrip()
    idx = line.find(" ", target)
    if idx == -1:
        idx = line.rfind(" ", 0, target)
    if idx == -1:
        idx = target
    return line[:idx].rstrip()


def _sample_needles(text: str, count: int) -> list[str]:
    """Pick `count` distinctive phrases from the body text.

    Strategy: split on whitespace runs that look like sentence/paragraph
    boundaries — for docx, paragraphs are concatenated with single spaces
    by `_docx_paragraph_count_text_and_images`, so we can't rely on
    linebreaks. Instead we split on long whitespace runs (already
    collapsed) and on sentence-ending punctuation followed by a capital
    letter or Cyrillic character. Sort qualifying chunks by length,
    pick at 25/50/75 % positions, truncate at word boundary, filter
    ≥ 25 chars.

    q-7 LOW-5 honest scope: the sentence-boundary regex covers Latin
    and Cyrillic capital-letter starts only. CJK / Arabic / Hebrew /
    Greek scripts will fall through to the secondary whitespace-run
    split (`\\s{2,}`), which is degraded but still functional. If a
    future fixture in any of those scripts produces low-quality
    needles, hand-fill `required_needles` in `battery_signatures.json`
    rather than expanding this regex (each script family adds risk
    of false sentence-boundary detection in the others).
    """
    # Split on sentence boundaries: . / ! / ? / : followed by space.
    chunks = re.split(r"(?<=[.!?])\s+(?=[A-ZА-ЯЁ])", text)
    # Also tolerate fixtures with no sentence terminators: split on the
    # whitespace-run-after-double-space, then fallback to whole text.
    if len(chunks) < 3:
        chunks = re.split(r"\s{2,}", text)
    qualifying = [
        ln.strip() for ln in chunks
        if ln.strip() and len(ln.strip()) > 20 and not ln.strip().isdigit()
    ]
    if not qualifying:
        return []
    by_len = sorted(qualifying, key=len, reverse=True)[:max(count * 5, 15)]
    if len(by_len) < count:
        candidates = by_len
    else:
        candidates = [by_len[i * len(by_len) // count] for i in range(count)]
    needles = [_truncate_at_word(ln, _NEEDLE_TARGET_LEN) for ln in candidates]
    return [n for n in needles if len(n) >= _NEEDLE_MIN_LEN]


def _capture_one(src: Path, mode: str, *, prev: dict | None = None) -> dict | None:
    """Render src in mode ∈ {regular, reader}; return signature dict or None.

    Preserves user-curated `forbidden_needles` and any `_`-prefixed
    annotations across `--refresh`.
    """
    with tempfile.TemporaryDirectory() as td:
        docx = Path(td) / f"capture-{mode}.docx"
        rc = _run_html2docx(src, docx, reader=(mode == "reader"))
        if rc != 0 or not docx.exists() or docx.stat().st_size < 1024:
            print(
                f"  ! {mode}: render failed (rc={rc}, "
                f"docx={'missing' if not docx.exists() else f'{docx.stat().st_size}B'})",
                file=sys.stderr,
            )
            return None
        paragraphs, body, images = _docx_paragraph_count_text_and_images(docx)
        size_kb = docx.stat().st_size // 1024
        needles = _sample_needles(body, REQUIRED_NEEDLE_COUNT)
        if len(needles) < 2:
            print(
                f"  ! {mode}: only {len(needles)} stable needle(s) sampled — "
                "fixture has very little body content. Hand-add "
                "`required_needles` in the JSON before relying on this baseline.",
                file=sys.stderr,
            )
        para_slack = max(PARA_SLACK, int(round(paragraphs * PARA_TOLERANCE_PCT)))
        size_slack = max(SIZE_SLACK, int(round(size_kb * SIZE_TOLERANCE_PCT)))
        entry: dict = {
            "min_paragraphs": max(1, paragraphs - para_slack),
            "max_paragraphs": paragraphs + para_slack,
            "min_size_kb": max(1, size_kb - size_slack),
            "max_size_kb": size_kb + size_slack,
            # Image count: exact match (no tolerance). q-7 HIGH-1: rule-6
            # icon strip changed an integer count, not a fuzzy size — and
            # adding even ±1 slack was enough to mask the regression. If
            # a rendering choice legitimately changes image count (e.g. a
            # large diagram split into tiles), bump min/max by hand in
            # the JSON.
            "min_images": images,
            "max_images": images,
            "required_needles": needles,
            "forbidden_needles": [],
        }
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
    ordered = dict(sorted(data.items()))
    SIGNATURES_PATH.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _discover_fixtures() -> list[Path]:
    """Walk all three source directories and return fixture paths."""
    found: list[Path] = []
    for d in (TMP_DIR, SYNTHETIC_DIR, PLATFORM_DIR):
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix.lower() in INPUT_EXTS:
                found.append(f)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--refresh", action="store_true",
        help="Refresh existing baselines (default: only ADD new fixtures).",
    )
    parser.add_argument(
        "--fixture", default=None,
        help="Refresh a single fixture by filename (implies --refresh for that one).",
    )
    args = parser.parse_args(argv)

    if shutil.which("node") is None:
        print("ERROR: node not on PATH — required for html2docx.js.",
              file=sys.stderr)
        return 1

    fixtures = _discover_fixtures()
    if not fixtures:
        print(
            f"No fixtures with extensions {INPUT_EXTS} found under "
            f"{TMP_DIR}, {SYNTHETIC_DIR}, or {PLATFORM_DIR}.",
            file=sys.stderr,
        )
        return 1

    existing = _load_existing()
    print(f"Found {len(fixtures)} fixture(s) on disk")
    print(f"Existing baseline has {len(existing)} entries")
    if args.refresh:
        print("--refresh: ALL existing entries will be regenerated")
    if args.fixture:
        print(f"--fixture: only {args.fixture} will be refreshed")

    to_capture: list[Path] = []
    for f in fixtures:
        if args.fixture and f.name != args.fixture:
            if f.name not in existing:
                print(f"skip   {f.name} (filtered by --fixture)")
            continue
        if f.name in existing and not args.refresh and not args.fixture:
            print(f"skip   {f.name} (already in baseline)")
            continue
        to_capture.append(f)

    if not to_capture:
        print("Nothing to capture.")
        return 0

    for f in to_capture:
        print(f"capture {f.name}  [{_source_for(f)}]")
        prev_full = existing.get(f.name) or {}
        sig: dict = {
            "platform": prev_full.get("platform", _platform_guess(f.name)),
            "source": prev_full.get("source", _source_for(f)),
        }
        for key, val in prev_full.items():
            if key.startswith("_"):
                sig[key] = val
        for mode in ("regular", "reader"):
            prev_mode = prev_full.get(mode) if isinstance(prev_full, dict) else None
            entry = _capture_one(f, mode, prev=prev_mode)
            if entry is None:
                print(f"  ! {mode}: capture FAILED — entry set to null",
                      file=sys.stderr)
                sig[mode] = None
            else:
                sig[mode] = entry
                forbidden_n = len(entry.get("forbidden_needles", []))
                print(
                    f"  {mode}: paras={entry['min_paragraphs']}–{entry['max_paragraphs']}, "
                    f"size={entry['min_size_kb']}–{entry['max_size_kb']}kB, "
                    f"images={entry['min_images']}, "
                    f"needles={len(entry['required_needles'])}"
                    + (f", preserved {forbidden_n} forbidden" if forbidden_n else "")
                )
        # q-7 MED-3: auto-dedupe identical regular/reader signatures.
        # When a fixture doesn't trigger reader-mode-specific behavior,
        # both modes produce byte-identical entries — running the same
        # assertion twice doubles battery time without adding coverage.
        # Set reader=null to mark "not applicable" (test_battery skips
        # null-mode entries instead of failing). User-curated divergence
        # (forbidden_needles in only one mode, manual `_canary` tags)
        # always preserves both — equality check covers all keys.
        if (
            isinstance(sig.get("regular"), dict)
            and isinstance(sig.get("reader"), dict)
            and sig["regular"] == sig["reader"]
        ):
            print(
                "  reader: identical to regular → set null "
                "(MED-3 auto-dedupe; edit JSON by hand if reader-mode "
                "regression coverage is needed for this fixture)"
            )
            sig["reader"] = None
        existing[f.name] = sig

    _save(existing)
    print(f"\nWrote {SIGNATURES_PATH}")
    print("\nNext steps:")
    print("  1. Hand-add `forbidden_needles` per platform (chrome / sidebar / ad strings)")
    print("  2. Run: ./.venv/bin/python -m unittest tests.test_battery")
    print("  3. Commit battery_signatures.json + new committed fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
