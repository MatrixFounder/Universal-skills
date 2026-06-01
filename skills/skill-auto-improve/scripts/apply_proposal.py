#!/usr/bin/env python3
"""Apply a validated proposal to an artifact (surgical, never full overwrite).

Supported diff formats (all scoped + structured — no raw diffs):
  * section-replace    : replace one `## Header` section in a markdown body,
                         preserving frontmatter. Used for skill/prompt/workflow.
  * frontmatter-field  : set one mutable frontmatter field (description/version).
  * dataset-op         : structured add/modify ops on an evals.json list.

The caller MUST run check_immutability.validate_proposal() first. This module
re-resolves the target file but does not re-validate immutability.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from scripts.common import (  # type: ignore
        ARTIFACT_DATASET, ARTIFACT_FULL_SKILL, ARTIFACT_SKILL,
        DIFF_DATASET_OP, DIFF_FRONTMATTER_FIELD, DIFF_SECTION_REPLACE, DIFF_TEXT_REPLACE,
        ProposalError, apply_text_replace, replace_section, resolve_dataset_items,
        sanitize_injectable_value, set_frontmatter_field, split_frontmatter,
    )
except ImportError:
    from common import (
        ARTIFACT_DATASET, ARTIFACT_FULL_SKILL, ARTIFACT_SKILL,
        DIFF_DATASET_OP, DIFF_FRONTMATTER_FIELD, DIFF_SECTION_REPLACE, DIFF_TEXT_REPLACE,
        ProposalError, apply_text_replace, replace_section, resolve_dataset_items,
        sanitize_injectable_value, set_frontmatter_field, split_frontmatter,
    )


def resolve_target_file(artifact_path: Path, artifact_type: str) -> Path:
    """The concrete file an edit lands on."""
    artifact_path = Path(artifact_path)
    if artifact_type in (ARTIFACT_SKILL, ARTIFACT_FULL_SKILL) and artifact_path.is_dir():
        return artifact_path / "SKILL.md"
    return artifact_path


def _apply_section_replace(target: Path, proposal: dict) -> None:
    text = target.read_text(encoding="utf-8")
    block, body = split_frontmatter(text)
    new_body = replace_section(body, proposal["target_section"], proposal["new_content"])
    if block:
        target.write_text(f"---\n{block}\n---\n{new_body}", encoding="utf-8")
    else:
        target.write_text(new_body, encoding="utf-8")


def _apply_frontmatter_field(target: Path, proposal: dict) -> None:
    text = target.read_text(encoding="utf-8")
    value = proposal["value"]
    # description is embedded into an agent-readable command context downstream;
    # defang injection markers before writing (see common.sanitize_injectable_value).
    if proposal["field"] == "description":
        value = sanitize_injectable_value(value)
    target.write_text(set_frontmatter_field(text, proposal["field"], value), encoding="utf-8")


def _apply_text_replace(target: Path, proposal: dict) -> None:
    content = target.read_text(encoding="utf-8")
    new_content, how = apply_text_replace(content, proposal["find"], proposal.get("replace", ""))
    if new_content is None:
        raise ProposalError(f"text-replace failed: {how}")
    target.write_text(new_content, encoding="utf-8")


def _apply_dataset_ops(target: Path, proposal: dict) -> None:
    data = json.loads(target.read_text(encoding="utf-8"))
    items, wrapper_key = resolve_dataset_items(data)
    # If a dict had no recognized wrapper key, adopt the canonical 'evals' key
    # and bind `items` to a list that is actually stored in `data` (the old
    # code appended to an orphan list that was never written back).
    if isinstance(data, dict) and wrapper_key is None:
        data["evals"] = items  # items is [] from resolve; now a live reference
    by_id = {it.get("id"): it for it in items if isinstance(it, dict)}

    for op in proposal["dataset_ops"]:
        kind = op["op"]
        if kind == "add":
            item = op.get("item")
            if not isinstance(item, dict):
                raise ProposalError("dataset add op requires an 'item' object")
            items.append(item)
            if item.get("id"):
                by_id[item["id"]] = item
        elif kind == "modify":
            target_item = by_id.get(op.get("id"))
            if target_item is None:
                raise ProposalError(f"dataset modify op: unknown id {op.get('id')!r}")
            for key, value in (op.get("fields") or {}).items():
                target_item[key] = value
        else:
            raise ProposalError(f"unsupported dataset op: {kind!r}")

    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def apply_proposal(artifact_path: Path, artifact_type: str, proposal: dict) -> Path:
    """Apply the proposal in place. Returns the file that was modified."""
    fmt = proposal.get("diff_format")
    target = resolve_target_file(artifact_path, artifact_type)

    if fmt == DIFF_SECTION_REPLACE:
        _apply_section_replace(target, proposal)
    elif fmt == DIFF_FRONTMATTER_FIELD:
        _apply_frontmatter_field(target, proposal)
    elif fmt == DIFF_DATASET_OP:
        _apply_dataset_ops(target, proposal)
    elif fmt == DIFF_TEXT_REPLACE:
        _apply_text_replace(target, proposal)
    else:
        raise ProposalError(f"unknown/unsupported diff_format: {fmt!r}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a validated proposal")
    parser.add_argument("artifact")
    parser.add_argument("--type", required=True)
    parser.add_argument("--proposal", required=True, help="proposal JSON file")
    args = parser.parse_args()
    proposal = json.loads(Path(args.proposal).read_text(encoding="utf-8"))
    try:
        modified = apply_proposal(Path(args.artifact), args.type, proposal)
    except (ProposalError, KeyError, ValueError) as exc:
        print(f"apply failed: {exc}", file=sys.stderr)
        return 1
    print(str(modified))
    return 0


if __name__ == "__main__":
    sys.exit(main())
