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
  - any markdown type   : `## Header` sections named with --protect (whole
                          section text is fingerprinted)

  3. shrink_violation(...) — the deletion guard: an edit may not shrink a
     section by more than half or drop lines carrying MUST / NEVER, unless the
     run passes --allow-deletions. Content no eval case measures can otherwise
     be cut without any score moving.
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
        MUTABLE_FRONTMATTER_FIELDS, emit_json, find_sections, install_human_channel,
        parse_frontmatter, resolve_dataset_items, split_frontmatter,
    )
except ImportError:
    from common import (
        ALLOWED_DIFF_FORMATS, ARTIFACT_DATASET, ARTIFACT_FULL_SKILL, ARTIFACT_PROMPT,
        ARTIFACT_SKILL, ARTIFACT_TEXT, ARTIFACT_WORKFLOW,
        DATASET_IMMUTABLE_FIELDS, DATASET_REF_FIELDS,
        DIFF_DATASET_OP, DIFF_FRONTMATTER_FIELD, DIFF_SECTION_REPLACE, DIFF_TEXT_REPLACE,
        MUTABLE_FRONTMATTER_FIELDS, emit_json, find_sections, install_human_channel,
        parse_frontmatter, resolve_dataset_items, split_frontmatter,
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


def immutable_signatures(path: Path, artifact_type: str,
                         protected_sections: tuple[str, ...] | list[str] = ()) -> set[str]:
    """Return the SET of immutable-part signatures for an artifact.

    `protected_sections` (from --protect) adds one signature per named
    `## Header` section — its full text — so any edit to it fails the subset
    check, whatever edit format made it.

    The orchestrator captures this set before an apply and requires it to be a
    SUBSET of the post-apply set (before ⊆ after). That allows *additions*
    (e.g. new dataset cases, a new placeholder) while still catching any change
    to — or removal of — an existing immutable part. A plain hash-equality
    check would wrongly flag legitimate additions as violations.
    """
    sig = _type_signatures(Path(path), artifact_type)
    if protected_sections and artifact_type != ARTIFACT_DATASET:
        sig |= protected_section_signatures(_markdown_text(Path(path), artifact_type),
                                            protected_sections)
    return sig


def _markdown_text(path: Path, artifact_type: str) -> str:
    if artifact_type in (ARTIFACT_SKILL, ARTIFACT_FULL_SKILL) and path.is_dir():
        return _artifact_text(path / "SKILL.md")
    return _artifact_text(path)


def _norm_header(header: str) -> str:
    return header.lstrip("#").strip().casefold()


def protected_section_signatures(text: str, headers) -> set[str]:
    """One `section:<header>=<sha256>` per protected header found in `text`."""
    wanted = {_norm_header(h) for h in headers}
    _, body = split_frontmatter(text)
    sig = set()
    for s in find_sections(body):
        key = _norm_header(s["header"])
        if key in wanted:
            digest = hashlib.sha256(body[s["char_start"]:s["char_end"]].encode("utf-8")).hexdigest()
            sig.add(f"section:{key}={digest}")
    return sig


def missing_protected_sections(path: Path, artifact_type: str, headers) -> list[str]:
    """Headers named with --protect that the artifact does not contain."""
    _, body = split_frontmatter(_markdown_text(Path(path), artifact_type))
    present = {_norm_header(s["header"]) for s in find_sections(body)}
    return [h for h in headers if _norm_header(h) not in present]


def _type_signatures(path: Path, artifact_type: str) -> set[str]:
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
        # text itself is immutable (unless --protect names a `##` section).
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


# ----------------------------- deletion guard -------------------------------
_RULE_LINE_RE = re.compile(r"\b(?:MUST|NEVER)\b")
SHRINK_MAX_FRACTION = 0.5


def _segments(body: str) -> list[tuple[str, int]]:
    """(name, non-blank content lines) for the preamble and every `##` section.

    A document with no `##` sections is one segment, "(document)". A section's
    own header line is not counted as content.
    """
    sections = find_sections(body)
    if not sections:
        return [("(document)", sum(1 for ln in body.splitlines() if ln.strip()))]
    out = []
    preamble = body[: sections[0]["char_start"]]
    if preamble.strip():
        out.append(("(preamble)", sum(1 for ln in preamble.splitlines() if ln.strip())))
    for s in sections:
        lines = [ln for ln in body[s["char_start"]:s["char_end"]].splitlines() if ln.strip()]
        out.append((s["header"], max(len(lines) - 1, 0)))
    return out


def shrink_violation(old_text: str, new_text: str,
                     max_fraction: float = SHRINK_MAX_FRACTION) -> str | None:
    """Reason string if an edit deletes too much, else None.

    Two rules, applied to the document body (frontmatter excluded) before vs
    after the edit:
      1. The number of lines containing the word MUST or NEVER may not drop.
         Rewording such a line is allowed; removing one is not.
      2. No segment (the preamble or a `## Header` section) may lose more than
         `max_fraction` of its non-blank lines, and no segment may disappear.

    Why: a test case only protects what it measures. Content no case touches
    can be cut without moving the score, and a loop that optimizes the score
    will eventually cut it. `--allow-deletions` turns the guard off.
    """
    def rule_lines(body: str) -> int:
        return sum(1 for ln in body.splitlines() if _RULE_LINE_RE.search(ln))

    # Body only: the frontmatter `description` is the trigger text the CSO
    # optimizer exists to rewrite, and a MUST in it is not an instruction rule.
    _, old_body = split_frontmatter(old_text)
    _, new_body = split_frontmatter(new_text)
    old_rules, new_rules = rule_lines(old_body), rule_lines(new_body)
    if new_rules < old_rules:
        return f"drops {old_rules - new_rules} MUST/NEVER line(s)"

    after = {_norm_header(name): n for name, n in _segments(new_body)}
    for name, old_n in _segments(old_body):
        if old_n == 0:
            continue
        new_n = after.get(_norm_header(name))
        if new_n is None:
            return f"removes segment {name!r}"
        if new_n < old_n * (1.0 - max_fraction):
            return (f"shrinks {name!r} from {old_n} to {new_n} lines "
                    f"(more than {int(max_fraction * 100)}% deleted)")
    return None


def compute_immutable_hash(path: Path, artifact_type: str) -> str:
    """Stable digest of the immutable signature set (CLI convenience)."""
    return _hash(sorted(immutable_signatures(path, artifact_type)))


def validate_proposal(artifact_path: Path, artifact_type: str, proposal: dict,
                      protected_sections: tuple[str, ...] | list[str] = ()) -> tuple[bool, str]:
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
        if _norm_header(target) in {_norm_header(h) for h in protected_sections}:
            return False, f"section is protected (--protect): {target!r}"
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
    install_human_channel()
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
    emit_json({"ok": ok, "reason": reason}, indent=None)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
