"""xlsx-3 F7 — sheet-name resolution algorithm.

task-005-07: full body for the 9-step sanitisation algorithm
(TASK §0/D2). M1 + M3 review-fix locks: `_truncate_utf16` and
`_dedup_step8` both honour Excel's 31 UTF-16-code-unit hard limit.

The 9-step algorithm:
  1. Strip inline markdown from heading → `raw`.
  2. Replace forbidden chars `[]:*?/\\` with `_`.
  3. Collapse runs of whitespace.
  4. Strip leading / trailing whitespace and `'`.
  5. If empty → `Table-N` (N = empty-counter, 1-indexed).
  6. UTF-16 truncate to 31 code units (m1 review-fix).
  7. Reserved-name `History` guard: append `_` and re-truncate.
  8. Workbook-wide dedup via `-2`..`-99`; prefix re-truncation uses
     `_truncate_utf16` (M3 review-fix — NOT Python `str[:N]`).
  9. Add winning name's lowercase form to `used_lower` before
     returning.

`--sheet-prefix` mode (ARCH m12 lock): when `sheet_prefix is not
None`, `resolve(heading)` ignores `heading` and returns
`f"{sanitised_prefix}-{counter}"` where counter increments per-call.
"""
from __future__ import annotations

import re

from .exceptions import InvalidSheetName
from .inline import strip_inline_markdown


_FORBIDDEN_RE = re.compile(r"[\[\]:*?/\\]")
# vdd-multi M1 review-fix: Excel rejects control chars in sheet names.
# `_WS_RE` collapses tab/newline/CR/FF/VT (which `\s` matches), but
# C0/DEL controls `\x00`-`\x08`, `\x0E`-`\x1F`, `\x7F` slip through.
# A heading like `## foo&#1;bar` decodes to `foo\x01bar` and corrupts
# the workbook ("Excel found a problem with content"). Strip them.
_CONTROL_RE = re.compile(r"[\x00-\x1F\x7F]")
_WS_RE = re.compile(r"\s+")


def _truncate_utf16(name: str, limit: int = 31) -> str:
    """Truncate `name` to at most `limit` UTF-16 code units (Excel's
    sheet-name hard limit — m1 review-fix).

    BMP characters are 1 UTF-16 unit; supplementary-plane characters
    (e.g. emoji like `😀` at U+1F600) are 2 UTF-16 units. A naive
    Python `name[:limit]` slice indexes by code points and can yield
    a > `limit`-UTF-16-unit string. Sliced mid-surrogate-pair → drop
    the orphan via `errors="ignore"`.
    """
    if limit <= 0:
        return ""
    encoded = name.encode("utf-16-le")
    return encoded[: 2 * limit].decode("utf-16-le", errors="ignore")


def _sanitise_step2(name: str) -> str:
    """Step 2: replace forbidden chars `[ ] : * ? / \\` with `_`,
    plus C0/DEL control characters (vdd-multi M1 review-fix).
    """
    name = _FORBIDDEN_RE.sub("_", name)
    name = _CONTROL_RE.sub("_", name)
    return name


def _sanitise_step3(name: str) -> str:
    """Step 3: collapse runs of whitespace to single space."""
    return _WS_RE.sub(" ", name)


def _sanitise_step4(name: str) -> str:
    """Step 4: strip leading/trailing whitespace and apostrophes."""
    return name.strip().strip("'")


class SheetNameResolver:
    """Stateful resolver for one workbook conversion.

    One instance per CLI invocation. Holds `_used_lower` (workbook-
    wide dedup set; case-insensitive), `_fallback_counter` (Table-N
    counter for empty-after-sanitise headings) and `_prefix_counter`
    (for `--sheet-prefix` mode).
    """

    def __init__(self, sheet_prefix: str | None = None) -> None:
        self.sheet_prefix = sheet_prefix
        self._used_lower: set[str] = set()
        self._fallback_counter = 0
        self._prefix_counter = 0
        # Cache the sanitised prefix once (no need to re-run per call).
        self._sanitised_prefix: str | None = None
        if sheet_prefix is not None:
            p = strip_inline_markdown(sheet_prefix)
            p = _sanitise_step2(p)
            p = _sanitise_step3(p)
            p = _sanitise_step4(p)
            if not p:
                p = "Sheet"  # last-ditch fallback for empty prefix
            p = _truncate_utf16(p, limit=31)
            self._sanitised_prefix = p

    def resolve(self, heading: str | None) -> str:
        """Run the 9-step pipeline on `heading`. Returns a unique
        Excel-valid sheet name and adds its lowercase form to
        `_used_lower`.

        When `self.sheet_prefix is not None` (ARCH m12 lock), the
        `heading` argument is ignored and the resolver returns
        sequential `{sanitised_prefix}-1`, `{sanitised_prefix}-2`, …
        (dedup step 8 is a no-op in this mode — counter cannot
        collide unless N > 99, in which case `InvalidSheetName`
        is raised by `_dedup_step8` semantics anyway).
        """
        # --sheet-prefix mode short-circuits (ARCH m12 lock).
        if self._sanitised_prefix is not None:
            self._prefix_counter += 1
            suffix = f"-{self._prefix_counter}"
            # Truncate the prefix to make room for the suffix.
            base = _truncate_utf16(self._sanitised_prefix, limit=31 - len(suffix))
            candidate = base + suffix
            self._used_lower.add(candidate.lower())
            return candidate

        # Step 1: strip inline markdown.
        raw = strip_inline_markdown(heading) if heading else ""
        # Steps 2-4: forbidden chars, whitespace collapse, strip.
        raw = _sanitise_step2(raw)
        raw = _sanitise_step3(raw)
        raw = _sanitise_step4(raw)
        # Step 5: fallback to Table-N if empty.
        if not raw:
            self._fallback_counter += 1
            raw = f"Table-{self._fallback_counter}"
        # Step 6: UTF-16 truncate to 31 code units.
        base = _truncate_utf16(raw, limit=31)
        # Step 7: reserved-name `History` guard.
        if base.lower() == "history":
            base = _truncate_utf16(base + "_", limit=31)
        # Step 8 + 9: workbook-wide dedup + add to used_lower.
        return self._dedup_step8(base)

    def _dedup_step8(self, base: str) -> str:
        """Workbook-wide case-insensitive dedup with UTF-16-aware
        prefix re-truncation (M3 review-fix — supersedes TASK §0/D2
        pseudocode `base[:31-len(S)] + S` which would leak emojis).
        """
        if base.lower() not in self._used_lower:
            self._used_lower.add(base.lower())
            return base
        for n in range(2, 100):  # -2 .. -99 inclusive
            suffix = f"-{n}"
            candidate = _truncate_utf16(base, limit=31 - len(suffix)) + suffix
            if candidate.lower() not in self._used_lower:
                self._used_lower.add(candidate.lower())
                return candidate
        raise InvalidSheetName(
            f"Sheet name dedup exhausted retries: {base!r}",
            code=2,
            error_type="InvalidSheetName",
            details={
                "original": base,
                "retry_cap": 99,
                "first_collisions": sorted(self._used_lower)[:10],
            },
        )
