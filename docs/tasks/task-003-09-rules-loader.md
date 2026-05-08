# Task 003.09: `rules_loader.py` (F2 — JSON + ruamel.yaml hardened)

## Use Case Connection
- **I1.1** (rules file loader with hardening).
- **R1.a–R1.c, R1.h** (JSON/YAML detection, 1 MiB cap, ruamel.yaml event-stream alias-rejection, custom-tag reject, dup-key reject, YAML-1.1 bool-trap disable, Q7 hard `version: 1`).

## Task Goal
Implement F2 — load `--rules PATH`, dispatch on extension, hard-cap at 1 MiB pre-parse, and harden the YAML reader against billion-laughs / custom-tag / dup-key / YAML-1.1 boolean coercion. The Q7=hard exit 2 on missing/wrong `version: 1` is enforced here.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_check_rules/rules_loader.py`

```python
"""F2 — Rules-file loader (JSON / YAML hardened).

YAML reader uses ruamel.yaml YAML(typ='safe', pure=True, version=(1,2))
with allow_duplicate_keys=False. Anchor / alias rejection via
parser-event-stream filter BEFORE composition (so billion-laughs
never expands).

Stdlib `yaml.safe_load` is FORBIDDEN — does not block alias expansion.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .constants import RULES_MAX_BYTES, RULES_FILE_VERSION
from .exceptions import RulesFileTooLarge, RulesParseError, IOError as XlsxIOError

__all__ = ["load_rules_file", "_validate_version"]

def load_rules_file(path: Path | str) -> dict[str, Any]:
    """Load and validate a rules file. Returns the parsed dict.

    Raises:
        RulesFileTooLarge: > 1 MiB.
        RulesParseError: bad version, syntax error, hostile YAML.
        XlsxIOError: file not found / not readable.
    """
    p = Path(path)
    try:
        size = p.stat().st_size
    except FileNotFoundError as e:
        raise XlsxIOError(f"rules file not found: {p}") from e
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
        subtype="UnrecognisedExtension",
    )

def _load_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RulesParseError(f"JSON syntax: {e}", subtype="JsonSyntax") from e

def _load_yaml_hardened(text: str) -> dict:
    """Event-stream filter to reject anchors/aliases pre-composition."""
    from ruamel.yaml import YAML, parser
    yaml = YAML(typ='safe', pure=True)
    yaml.version = (1, 2)
    yaml.allow_duplicate_keys = False
    # Custom-tag rejection: install a constructor that refuses anything
    # outside the canonical YAML 1.2 schema.
    def _refuse_custom_tag(loader, node):
        raise RulesParseError(
            f"custom YAML tag not allowed: {node.tag}",
            subtype="YamlCustomTag",
        )
    yaml.constructor.add_multi_constructor('!', _refuse_custom_tag)
    yaml.constructor.add_multi_constructor('tag:', _refuse_custom_tag)
    # Pre-scan event stream for alias rejection.
    try:
        from ruamel.yaml.parser import Parser
        from ruamel.yaml.events import AliasEvent
        from ruamel.yaml.loader import SafeLoader
        # Use ruamel's parse_event method
        events = list(yaml.parse(text))
        for ev in events:
            if isinstance(ev, AliasEvent):
                raise RulesParseError(
                    "YAML aliases not allowed (anchor expansion blocked)",
                    subtype="YamlAlias",
                )
            anchor = getattr(ev, 'anchor', None)
            if anchor:
                raise RulesParseError(
                    f"YAML anchor declarations not allowed: &{anchor}",
                    subtype="YamlAnchor",
                )
    except parser.ParserError as e:
        raise RulesParseError(f"YAML syntax: {e}", subtype="YamlSyntax") from e
    # Re-load after the event-stream check passed.
    try:
        return yaml.load(text)
    except parser.DuplicateKeyError as e:
        raise RulesParseError(f"YAML duplicate key: {e}", subtype="YamlDupKey") from e

def _validate_version(d: dict) -> dict:
    """Q7=hard — missing or non-1 version => exit 2 RulesParseError."""
    if not isinstance(d, dict):
        raise RulesParseError("rules root must be an object", subtype="RootShape")
    v = d.get("version")
    if v != RULES_FILE_VERSION:
        raise RulesParseError(
            f"version: 1 required, got {v!r}",
            subtype="VersionMismatch", got=v,
        )
    if "rules" not in d or not isinstance(d["rules"], list) or len(d["rules"]) == 0:
        raise RulesParseError(
            "rules: must be a non-empty list",
            subtype="RulesShape",
        )
    return d
```

#### File: `skills/xlsx/scripts/tests/test_xlsx_check_rules.py`

Remove `@unittest.skip` from `TestRulesLoader`. Add tests covering battery fixtures #23–#28 + a positive `_validate_version` smoke. Critical:
- `test_yaml_alias_rejected_pre_composition` (fixture #23) — must complete in ≤ 100 ms (use `time.perf_counter()`); raises `RulesParseError(YamlAlias)`.
- `test_yaml_string_with_ampersand_NOT_rejected` (fixture #23a) — `description: 'see Q1 & Q2'` does NOT raise (negative regression).
- `test_yaml_custom_tag_rejected` (fixture #24) — `!!python/object` raises `RulesParseError(YamlCustomTag)`.
- `test_yaml_11_bool_trap_disabled` (fixture #25) — `value in [yes, no]` parses with strings preserved.
- `test_yaml_dup_keys_rejected` (fixture #26).
- `test_huge_rules_rejected` (fixture #28) — 1.5 MiB file raises `RulesFileTooLarge` in ≤ 100 ms.
- `test_version_one_hard_exit` (Q7) — `{"rules": [...]}` (no version) raises `VersionMismatch`; `{"version": 2, "rules": [...]}` raises `VersionMismatch`.
- `test_no_yaml_safe_load_import` — grep test in CI: `assert "yaml.safe_load" not in <package source>`.

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

Append fixture invocations for #23, #23a, #24, #25, #26, #28. Each asserts exit code 2 (or 0 for #23a) and elapsed time ≤ 100 ms.

## Test Cases
- Unit: ~ 9 new tests; all pass.
- Regression: prior tests stay green.
- Battery: fixtures #23–#28 transition from xfail to xpass for the loader layer.

## Acceptance Criteria
- [ ] `rules_loader.py` complete (≤ 200 LOC).
- [ ] All YAML hardening tests pass within 100 ms each.
- [ ] `yaml.safe_load` not imported anywhere in the xlsx_check_rules package (grep test).
- [ ] Q7=hard enforced.
- [ ] `validate_skill.py` exits 0.

## Notes
- The ruamel.yaml event-stream alias-rejection is the security-critical part. **Do NOT** rely on `Constructor` to block aliases — by the time the constructor sees the node, the alias has been expanded (billion-laughs has already exploded into memory). The check MUST happen at the parser/event level, BEFORE composition.
- ruamel.yaml's exact API for event-stream iteration may differ between versions; if the snippet above doesn't compile, consult `ruamel.yaml`'s docs and adjust. The invariant — "alias check before composition" — is non-negotiable; the implementation detail is.
- Stdlib `yaml.safe_load` is FORBIDDEN — PyYAML's "safe" loader is safe re: code execution but **does not block anchor expansion**. The grep test in `tests/test_xlsx_check_rules.py::TestRulesLoader::test_no_yaml_safe_load_import` enforces this.
- The 1 MiB cap is enforced via `Path.stat().st_size` BEFORE `read_text` — never load the bytes into memory before the cap check.
