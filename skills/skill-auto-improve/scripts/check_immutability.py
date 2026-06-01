#!/usr/bin/env python3
"""Immutability gate for skill-auto-improve.

Two responsibilities:

  1. validate_proposal(...)  — structural check of a proposal BEFORE it is
     applied. Rejects proposals that would touch immutable parts or that are
     malformed. This is the primary gate (cheaper + safer than apply-then-check).

  2. compute_immutable_hash(...) — a stable digest of the artifact's immutable
     sections, captured before apply and re-checked after apply as defense in
     depth. A changed digest => IMMUTABILITY_VIOLATION => revert.

Immutability contract by artifact type:
  - skill / full-skill : frontmatter `name`, `tier`; the evals/ directory
  - dataset (evals.json): per-case `id`, `skill_name`, `grader`, file refs
  - prompt              : {{placeholders}} must be preserved
  - workflow            : frontmatter keys + tool-invocation names preserved
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    from scripts.common import (  # type: ignore
        ALLOWED_DIFF_FORMATS, ARTIFACT_DATASET, ARTIFACT_FULL_SKILL, ARTIFACT_PROMPT,
        ARTIFACT_SKILL, ARTIFACT_TEXT, ARTIFACT_WORKFLOW,
        DATASET_IMMUTABLE_FIELDS, DATASET_REF_FIELDS,
        DIFF_DATASET_OP, DIFF_FRONTMATTER_FIELD, DIFF_SECTION_REPLACE, DIFF_TEXT_REPLACE,
        MUTABLE_FRONTMATTER_FIELDS, parse_frontmatter, resolve_dataset_items,
    )
except ImportError:
    from common import (
        ALLOWED_DIFF_FORMATS, ARTIFACT_DATASET, ARTIFACT_FULL_SKILL, ARTIFACT_PROMPT,
        ARTIFACT_SKILL, ARTIFACT_TEXT, ARTIFACT_WORKFLOW,
        DATASET_IMMUTABLE_FIELDS, DATASET_REF_FIELDS,
        DIFF_DATASET_OP, DIFF_FRONTMATTER_FIELD, DIFF_SECTION_REPLACE, DIFF_TEXT_REPLACE,
        MUTABLE_FRONTMATTER_FIELDS, parse_frontmatter, resolve_dataset_items,
    )

_PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}")
_TOOL_RE = re.compile(r"\b([A-Z][a-zA-Z0-9]+)\(")  # crude tool-call fingerprint


def _hash(parts: list[str]) -> str:
    h = hashlib.sha256()
    for p in sorted(parts):
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _artifact_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def immutable_signatures(path: Path, artifact_type: str) -> set[str]:
    """Return the SET of immutable-part signatures for an artifact.

    The orchestrator captures this set before an apply and requires it to be a
    SUBSET of the post-apply set (before ⊆ after). That allows *additions*
    (e.g. new dataset cases, a new placeholder) while still catching any change
    to — or removal of — an existing immutable part. A plain hash-equality
    check would wrongly flag legitimate additions as violations.
    """
    path = Path(path)
    if artifact_type in (ARTIFACT_SKILL, ARTIFACT_FULL_SKILL):
        skill_md = path / "SKILL.md" if path.is_dir() else path
        fm = parse_frontmatter(_artifact_text(skill_md))
        sig = {"name=" + fm.get("name", ""), "tier=" + fm.get("tier", "")}
        # The eval harness is immutable: fingerprint every file under evals/ by
        # content hash. The subset check then forbids changing OR removing any
        # existing eval file (additions, which can only happen via a separate
        # explicit step, would be permitted — but no skill apply-path writes here).
        if path.is_dir():
            evals_dir = path / "evals"
            if evals_dir.is_dir():
                for f in sorted(evals_dir.rglob("*")):
                    if f.is_file():
                        digest = hashlib.sha256(f.read_bytes()).hexdigest()
                        sig.add(f"eval:{f.relative_to(path)}={digest}")
        return sig

    if artifact_type == ARTIFACT_DATASET:
        data = json.loads(_artifact_text(path))
        items, _key = resolve_dataset_items(data)
        sig = set()
        for item in items or []:
            if not isinstance(item, dict):
                continue
            ident = item.get("id")
            if ident in (None, ""):
                continue  # new/unidentified items are additions, not tracked
            # Key by id first so each tracked case is a distinct set element
            # (two cases sharing the same immutable triple can't collapse).
            sig.add(f"case:{ident}:" + "|".join(f"{f}={item.get(f, '')}" for f in DATASET_IMMUTABLE_FIELDS))
            for ref_key in DATASET_REF_FIELDS:
                if ref_key in item:
                    sig.add(f"{ident}:{ref_key}={json.dumps(item[ref_key], sort_keys=True)}")
        return sig

    if artifact_type == ARTIFACT_TEXT:
        # Free-form prose graded against a SEPARATE rubric (--criteria). The
        # rubric is the harness and is never the artifact, so nothing within the
        # text itself is immutable.
        return set()

    if artifact_type == ARTIFACT_PROMPT:
        return set(_PLACEHOLDER_RE.findall(_artifact_text(path)))

    if artifact_type == ARTIFACT_WORKFLOW:
        text = _artifact_text(path)
        fm = parse_frontmatter(text)
        tools = set(_TOOL_RE.findall(text))
        return {"fmkey=" + k for k in fm.keys()} | {"tool=" + t for t in tools}

    raise ValueError(f"unknown artifact type: {artifact_type}")


def immutable_preserved(before: set[str], after: set[str]) -> bool:
    """True iff no existing immutable signature was changed or removed."""
    return before <= after


def compute_immutable_hash(path: Path, artifact_type: str) -> str:
    """Stable digest of the immutable signature set (CLI convenience)."""
    return _hash(sorted(immutable_signatures(path, artifact_type)))


def validate_proposal(artifact_path: Path, artifact_type: str, proposal: dict) -> tuple[bool, str]:
    """Return (ok, reason). Reject malformed or immutability-touching proposals."""
    fmt = proposal.get("diff_format")
    if fmt not in ALLOWED_DIFF_FORMATS:
        return False, f"diff_format not allowed: {fmt!r} (allowed: {ALLOWED_DIFF_FORMATS})"

    if fmt == DIFF_TEXT_REPLACE:
        find = proposal.get("find") or ""
        if not find.strip():
            return False, "text-replace requires a non-empty 'find'"
        if "replace" not in proposal:
            return False, "text-replace requires a 'replace' field"
        # Bound `find`: it is compiled into a fuzzy-ws regex; an unbounded value
        # (from an LLM) would build a huge pattern and waste compile time.
        if len(find) > 4096:
            return False, f"text-replace 'find' too long ({len(find)} chars; cap 4096)"
        return True, "ok"

    if fmt == DIFF_FRONTMATTER_FIELD:
        field = (proposal.get("field") or "").strip()
        if field not in MUTABLE_FRONTMATTER_FIELDS:
            return False, f"frontmatter field not mutable: {field!r} (allowed: {MUTABLE_FRONTMATTER_FIELDS})"
        if not (proposal.get("value") or "").strip():
            return False, "frontmatter-field requires a non-empty value"
        return True, "ok"

    if fmt == DIFF_SECTION_REPLACE:
        target = (proposal.get("target_section") or "").strip()
        content = proposal.get("new_content")
        if not target or content is None:
            return False, "section-replace requires target_section and new_content"
        if not content.strip():
            return False, "empty new_content"
        # No rename: the new content must lead with the same header.
        first_line = content.lstrip().splitlines()[0].strip() if content.strip() else ""
        if first_line.casefold().lstrip("#").strip() != target.casefold().lstrip("#").strip():
            return False, "new_content must start with the same header as target_section (no rename)"
        return True, "ok"

    if fmt == DIFF_DATASET_OP:
        if artifact_type != ARTIFACT_DATASET:
            return False, "dataset-op only valid for dataset artifacts"
        ops = proposal.get("dataset_ops")
        if not isinstance(ops, list) or not ops:
            return False, "dataset_ops must be a non-empty list"
        protected = set(DATASET_IMMUTABLE_FIELDS) | set(DATASET_REF_FIELDS)
        for op in ops:
            if not isinstance(op, dict) or "op" not in op:
                return False, "each dataset op needs an 'op' field"
            if op["op"] == "modify":
                bad = set((op.get("fields") or {}).keys()) & protected
                if bad:
                    return False, f"dataset op modifies immutable fields: {sorted(bad)}"
            elif op["op"] == "add":
                # A NEW case must not smuggle a grader (harness config) and any
                # file refs must stay within the dataset's own directory.
                item = op.get("item")
                if not isinstance(item, dict):
                    return False, "dataset add op requires an 'item' object"
                if "grader" in item or "skill_name" in item:
                    return False, "added eval case may not set 'grader'/'skill_name'"
                ok_refs, why = _safe_dataset_refs(artifact_path, item)
                if not ok_refs:
                    return False, why
            elif op["op"] == "remove":
                return False, "removing existing eval cases is not allowed"
            else:
                return False, f"unsupported dataset op: {op['op']!r}"
        return True, "ok"

    return False, "unhandled format"


def _safe_dataset_refs(dataset_path: Path, item: dict) -> tuple[bool, str]:
    """Reject file refs that escape the dataset's own directory (traversal)."""
    base = Path(dataset_path).resolve().parent
    for key in DATASET_REF_FIELDS:
        if key not in item:
            continue
        refs = item[key]
        for ref in (refs if isinstance(refs, list) else [refs]):
            try:
                resolved = (base / str(ref)).resolve()
                resolved.relative_to(base)
            except (ValueError, OSError):
                return False, f"added eval case file ref escapes dataset dir: {ref!r}"
    return True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="Immutability gate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hash")
    h.add_argument("path")
    h.add_argument("--type", required=True)
    v = sub.add_parser("validate")
    v.add_argument("path")
    v.add_argument("--type", required=True)
    v.add_argument("--proposal", required=True, help="proposal JSON file")
    args = parser.parse_args()

    if args.cmd == "hash":
        print(compute_immutable_hash(Path(args.path), args.type))
        return 0
    proposal = json.loads(Path(args.proposal).read_text(encoding="utf-8"))
    ok, reason = validate_proposal(Path(args.path), args.type, proposal)
    print(json.dumps({"ok": ok, "reason": reason}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
