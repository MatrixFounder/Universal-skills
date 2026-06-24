#!/usr/bin/env python3
"""html conversion-quality battery — capture / refresh signatures.

Mirrors `skills/pdf/scripts/tests/capture_signatures.py`. Converts each fixture to
whole + reader Markdown and records a structural signature: line / heading / GFM-table-
row / code-fence counts + size, PLUS the conversion-quality INVARIANTS that lock the
GitBook/Mintlify/Fern fixes — `empty_headings == 0` and `stray_chrome == 0`.

Two fixture tiers:
  • committed micro-fixtures under `examples/regression/` (always present, CI-runnable);
  • real gitignored pages under repo `tmp/` (skipped per-fixture when absent).

    ./.venv/bin/python tests/capture_signatures.py --refresh   # regenerate the JSON
    ./.venv/bin/python tests/capture_signatures.py             # dry-run, print only
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

HERE = Path(__file__).resolve().parent          # scripts/tests/
SCRIPTS = HERE.parent                            # scripts/
SKILL = SCRIPTS.parent                           # skills/html/
REPO = SKILL.parents[1]                          # repo root
TMP = REPO / "tmp"
SIG_PATH = HERE / "battery_signatures.json"
SHIM = SCRIPTS / "html"

FIXTURES: dict[str, dict] = {
    # Tier 2 — committed synthetic (always present): exercises every fix.
    "gitbook-style-doc.html": {
        "path": SKILL / "examples" / "regression" / "gitbook-style-doc.html",
        "platform": "synthetic",
        "required": [
            "UNIQUE-BODY-MARKER-ALPHA", "## Parameters", "## Usage",
            "| Name | Type | Description |",
            "| Content-Type | String | application/json |",
            "[Related Doc Link](https://example.com/docs/related)",
        ],
    },
    # Tier 0 — real gitignored pages (skip-if-absent).
    "Hyperliquid_Docs_gitbook.webarchive": {
        "path": TMP / "Hyperliquid_Docs_gitbook.webarchive", "platform": "gitbook",
        "required": ["# Info endpoint", "| Name | Type | Description |"]},
    "OpenRouter Quickstart Guide - fern.webarchive": {
        "path": TMP / "OpenRouter Quickstart Guide - fern.webarchive", "platform": "fern",
        "required": ["OpenRouter"]},
    "OAuth2 and Permissions - Documentation - Discord.webarchive": {
        "path": TMP / "OAuth2 and Permissions - Documentation - Discord.webarchive",
        "platform": "discord", "required": ["OAuth2"]},
    "JetBrains IDEs - Claude Code Docs.webarchive": {
        "path": TMP / "JetBrains IDEs - Claude Code Docs.webarchive", "platform": "mintlify",
        "required": ["JetBrains IDEs"]},
}

_CHROME = {"copy", "copy page", "copy code", "ask ai", "⌘k", "⌘ctrlk", "⌘i",
           "search...", "search…", "was this page helpful?", "yesno"}


def metrics(md: str) -> dict:
    lines = md.split("\n")
    return {
        "lines": sum(1 for ln in lines if ln.strip()),
        "headings": sum(1 for ln in lines if re.match(r"^#{1,6} \S", ln)),
        "table_rows": sum(1 for ln in lines if ln.startswith("| ")),
        "code_fences": sum(1 for ln in lines if ln.strip().startswith("```")),
        "size_kb": round(len(md.encode("utf-8")) / 1024, 1),
        "empty_headings": sum(1 for ln in lines if re.match(r"^#{1,6}[ \t]*$", ln)),
        "stray_chrome": sum(1 for ln in lines if ln.strip().lower() in _CHROME),
    }


def convert(path: Path) -> tuple[str | None, str | None]:
    out = Path(tempfile.mkdtemp(prefix="h2m_battery_"))
    try:
        r = subprocess.run([sys.executable, str(SHIM), str(path), str(out)],
                           cwd=str(SCRIPTS), capture_output=True, text=True)
        if r.returncode != 0:
            return None, None
        mds = list(out.glob("*.md"))
        whole = next((p for p in mds if not p.name.endswith(".reader.md")), None)
        reader = next((p for p in mds if p.name.endswith(".reader.md")), None)
        return (whole.read_text("utf-8") if whole else None,
                reader.read_text("utf-8") if reader else None)
    finally:
        shutil.rmtree(out, ignore_errors=True)


def build() -> dict:
    sig: dict = {}
    for name, spec in FIXTURES.items():
        if not spec["path"].exists():
            print(f"  skip (absent): {name}", file=sys.stderr)
            continue
        whole, reader = convert(spec["path"])
        if whole is None:
            print(f"  FAIL convert: {name}", file=sys.stderr)
            continue
        sig[name] = {
            "platform": spec["platform"],
            "whole": {**metrics(whole), "required_needles": spec.get("required", [])},
            "reader": metrics(reader) if reader else None,
        }
        m = sig[name]["whole"]
        print(f"  captured {name}: lines={m['lines']} headings={m['headings']} "
              f"table_rows={m['table_rows']} empty_headings={m['empty_headings']} "
              f"stray_chrome={m['stray_chrome']}")
    return sig


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="write battery_signatures.json")
    args = ap.parse_args()
    sig = build()
    if args.refresh:
        SIG_PATH.write_text(json.dumps(sig, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {SIG_PATH} ({len(sig)} fixtures)")


if __name__ == "__main__":
    main()
