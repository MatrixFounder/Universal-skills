"""F2 — Rules-file loader (JSON / YAML hardened).

Loads `--rules PATH`, dispatches on file extension, enforces a 1 MiB
pre-parse size cap, and hardens the YAML reader against:

  - **Anchors / aliases** (billion-laughs vector). Rejected at the
    parser-event level BEFORE composition; aliases never expand.
  - **Custom tags** (`!!python/object`, `!Foo`). Rejected via a
    constructor that refuses anything outside the canonical YAML 1.2
    schema.
  - **Duplicate keys** in mappings. Rejected via
    `allow_duplicate_keys=False`.
  - **YAML 1.1 boolean coercion** (`yes`, `no`, `on`, `off` →
    `bool`). Disabled via `YAML.version = (1, 2)` — strings stay
    strings.

Stdlib `yaml.safe_load` is FORBIDDEN: PyYAML's "safe" loader is safe
re: code execution but does NOT block alias expansion. The grep test
in `tests/test_xlsx_check_rules.py::TestRulesLoader::test_no_yaml_safe_load_import`
locks this.

Q7 (architect-review) — missing or non-1 `version` → exit 2
`RulesParseError(VersionMismatch)`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import RULES_FILE_VERSION, RULES_MAX_BYTES
from .exceptions import IOError as XlsxIOError
from .exceptions import RulesFileTooLarge, RulesParseError

__all__ = ["load_rules_file"]


def load_rules_file(path: Path | str) -> dict[str, Any]:
    """Load and validate a rules file. Returns the parsed dict.

    Raises:
        RulesFileTooLarge: file > 1 MiB (size cap pre-parse).
        RulesParseError:   bad version / shape / syntax / hostile YAML.
        IOError (xlsx-7):  file not found / not readable.
    """
    p = Path(path)
    try:
        size = p.stat().st_size
    except FileNotFoundError as e:
        raise XlsxIOError(f"rules file not found: {p}") from e
    except OSError as e:
        raise XlsxIOError(f"rules file unreadable: {p} ({e})") from e
    if size > RULES_MAX_BYTES:
        raise RulesFileTooLarge(
            f"rules file too large: {size} bytes > {RULES_MAX_BYTES}",
            subtype="RulesFileTooLarge", size=size,
        )

    text = p.read_text(encoding="utf-8")
    suffix = p.suffix.lower()
    if suffix == ".json":
        return _validate_version(_load_json(text))
    if suffix in (".yaml", ".yml"):
        return _validate_version(_load_yaml_hardened(text))
    raise RulesParseError(
        f"unrecognised rules-file extension: {p.suffix}",
        subtype="UnrecognisedExtension", extension=p.suffix,
    )


def _load_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RulesParseError(
            f"JSON syntax error: {e.msg} at line {e.lineno}, column {e.colno}",
            subtype="JsonSyntax", line=e.lineno, column=e.colno,
        ) from e


def _load_yaml_hardened(text: str) -> dict[str, Any]:
    """Two-stage YAML load: event-stream pre-scan, then construction.

    Stage 1 — parse the document into events and refuse on any
    `AliasEvent` or non-empty `anchor` attribute. This runs in
    sub-millisecond time on a billion-laughs document because event
    iteration is lazy and aliases expand only at composition.

    Stage 2 — re-load the same text with a constructor that refuses
    custom tags + a YAML 1.2 schema (no yes/no boolean coercion).
    Duplicate-key errors surface from `ruamel.yaml.constructor`.
    """
    try:
        from ruamel.yaml import YAML
        from ruamel.yaml.constructor import DuplicateKeyError
        from ruamel.yaml.events import AliasEvent
        from ruamel.yaml.parser import ParserError
        from ruamel.yaml.scanner import ScannerError
    except ImportError as e:  # pragma: no cover — ruamel is pinned
        raise RulesParseError(
            f"ruamel.yaml not available: {e}",
            subtype="YamlSyntax",
        ) from e

    # Stage 1: alias / anchor pre-scan (O(events), aliases do not expand).
    pre_scan = YAML(typ="safe", pure=True)
    pre_scan.version = (1, 2)
    try:
        for ev in pre_scan.parse(text):
            if isinstance(ev, AliasEvent):
                raise RulesParseError(
                    "YAML aliases not allowed (anchor expansion blocked at parse-time)",
                    subtype="YamlAlias",
                )
            anchor = getattr(ev, "anchor", None)
            if anchor:
                raise RulesParseError(
                    f"YAML anchor declarations not allowed: &{anchor}",
                    subtype="YamlAnchor", anchor=str(anchor),
                )
    except (ParserError, ScannerError) as e:
        raise RulesParseError(
            f"YAML syntax: {e}", subtype="YamlSyntax",
        ) from e

    # Stage 2: full load with custom-tag refusal + YAML 1.2 + dup-key reject.
    yaml = YAML(typ="safe", pure=True)
    yaml.version = (1, 2)
    yaml.allow_duplicate_keys = False

    def _refuse_custom_tag(loader, tag_suffix, node):  # noqa: ARG001 — ruamel signature
        raise RulesParseError(
            f"custom YAML tag not allowed: !{tag_suffix}",
            subtype="YamlCustomTag", tag=str(tag_suffix),
        )

    # `add_multi_constructor` registers a fallback for tags matching a
    # given prefix. `'!'` covers `!Foo` and `!!Foo` style local tags;
    # `'tag:'` covers fully-qualified tag URIs.
    yaml.constructor.add_multi_constructor("!", _refuse_custom_tag)
    yaml.constructor.add_multi_constructor("tag:", _refuse_custom_tag)

    try:
        result = yaml.load(text)
    except DuplicateKeyError as e:
        raise RulesParseError(
            f"YAML duplicate key: {e}",
            subtype="YamlDupKey",
        ) from e
    except (ParserError, ScannerError) as e:
        raise RulesParseError(
            f"YAML syntax: {e}", subtype="YamlSyntax",
        ) from e
    return result if isinstance(result, dict) else {}


def _validate_version(d: Any) -> dict[str, Any]:
    """Q7=hard — missing or non-1 `version` → exit 2 `VersionMismatch`."""
    if not isinstance(d, dict):
        raise RulesParseError(
            "rules root must be a JSON object / YAML mapping",
            subtype="RootShape", got=type(d).__name__,
        )
    v = d.get("version")
    if v != RULES_FILE_VERSION:
        raise RulesParseError(
            f"version: 1 required, got {v!r}",
            subtype="VersionMismatch", got=v,
        )
    rules = d.get("rules")
    if not isinstance(rules, list) or not rules:
        raise RulesParseError(
            "`rules` must be a non-empty list",
            subtype="RulesShape",
        )
    return d
