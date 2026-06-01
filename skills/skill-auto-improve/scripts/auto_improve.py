#!/usr/bin/env python3
"""skill-auto-improve — vendor-neutral orchestrator (CLI entry point).

Iteratively improves an artifact (skill / prompt / workflow / dataset) under
the autoresearch invariant: the eval harness is immutable, the artifact is free
to change, KEEP iff the metric improves beyond noise, otherwise REVERT.

Design for testability: the decision logic lives in `run_improvement_loop`,
which takes injectable `proposer` and `evaluator` callables. Real ones are
built by `build_default_proposer` / `build_default_evaluator`; unit tests inject
deterministic fakes so KEEP/REVERT/NO_SIGNAL/convergence/budget/immutability are
verifiable offline without API keys.

Contracts:
  proposer(context: dict)   -> {"proposal": dict|None, "usage": dict}
  evaluator(artifact_path)  -> {"score": float, "secondary": float|None, "usage": dict}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# --- imports (work as script or module) ------------------------------------
try:
    from scripts.common import (  # type: ignore
        ARTIFACT_DATASET, ARTIFACT_FULL_SKILL, ARTIFACT_PROMPT,
        ARTIFACT_SKILL, ARTIFACT_WORKFLOW,
        DIFF_SECTION_REPLACE,
        STATUS_BASELINE, STATUS_ERROR, STATUS_IMMUTABILITY, STATUS_KEEP,
        STATUS_NO_CHANGE, STATUS_NO_SIGNAL, STATUS_REVERT,
        TIER_LARGE, find_sections, parse_skill_md, split_frontmatter,
    )
    from scripts.check_immutability import immutable_preserved, immutable_signatures, validate_proposal
    from scripts.apply_proposal import apply_proposal
    from scripts.measure_change_size import measure_tier
    from scripts.snapshot import (
        commit_all, create_branch, is_clean, is_git_repo,
        restore_snapshot, save_snapshot,
    )
    from scripts.log_iteration import log_iteration
    from scripts.detect_artifact_type import detect_type
    from scripts.detect_vendor import detect_vendor
    from scripts.grade_dataset import score_dataset
    from scripts.backends import get_backend
except ImportError:
    from common import (
        ARTIFACT_DATASET, ARTIFACT_FULL_SKILL, ARTIFACT_PROMPT,
        ARTIFACT_SKILL, ARTIFACT_WORKFLOW,
        DIFF_SECTION_REPLACE,
        STATUS_BASELINE, STATUS_ERROR, STATUS_IMMUTABILITY, STATUS_KEEP,
        STATUS_NO_CHANGE, STATUS_NO_SIGNAL, STATUS_REVERT,
        TIER_LARGE, find_sections, parse_skill_md, split_frontmatter,
    )
    from check_immutability import immutable_preserved, immutable_signatures, validate_proposal
    from apply_proposal import apply_proposal
    from measure_change_size import measure_tier
    from snapshot import (
        commit_all, create_branch, is_clean, is_git_repo,
        restore_snapshot, save_snapshot,
    )
    from log_iteration import log_iteration
    from detect_artifact_type import detect_type
    from detect_vendor import detect_vendor
    from grade_dataset import score_dataset
    from backends import get_backend


# ---------------------------------------------------------------------------
# Config + loop
# ---------------------------------------------------------------------------
@dataclass
class LoopConfig:
    max_iterations: int = 10
    max_tokens: int | None = None
    max_duration_s: float | None = None
    noise_sigma: float = 0.0
    min_improvement: float = 0.01
    convergence_window: int = 3


@dataclass
class LoopState:
    best_score: float
    best_secondary: float | None
    spent_tokens: int = 0
    history: list[dict] = field(default_factory=list)
    iterations: list[dict] = field(default_factory=list)
    exit_reason: str = "completed"


# A change must beat noise by more than this float-equality epsilon to KEEP, so
# float jitter / exactly-equal scores never count as an improvement.
_KEEP_EPS = 1e-9


def _usage_tokens(usage: dict | None) -> int:
    if not usage:
        return 0
    return int(usage.get("total_tokens") or 0)


def _old_section_lines(artifact_path: Path, artifact_type: str, proposal: dict) -> int:
    """Line count of the section a section-replace will overwrite (0 if N/A).

    Lets the tier classifier see large DELETIONS, not just additions.
    """
    if proposal.get("diff_format") != DIFF_SECTION_REPLACE:
        return 0
    try:
        text = _load_artifact_text(artifact_path, artifact_type)
        _, body = split_frontmatter(text)
        want = (proposal.get("target_section") or "").casefold().lstrip("#").strip()
        for s in find_sections(body):
            if s["header"].casefold().lstrip("#").strip() == want:
                return body[s["char_start"]:s["char_end"]].count("\n")
    except Exception:
        return 0
    return 0


def run_improvement_loop(
    artifact_path: Path,
    artifact_type: str,
    workspace: Path,
    *,
    proposer: Callable[[dict], dict],
    evaluator: Callable[[Path], dict],
    config: LoopConfig,
    git_repo: Path | None = None,
    time_fn: Callable[[], float] = time.monotonic,
    on_large_tier: Callable[[Path], None] | None = None,
) -> dict:
    """Run the propose→evaluate→keep/revert loop. Returns a summary dict."""
    artifact_path = Path(artifact_path)
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    sigma = config.noise_sigma

    base = evaluator(artifact_path)
    state = LoopState(best_score=base["score"], best_secondary=base.get("secondary"))
    state.spent_tokens += _usage_tokens(base.get("usage"))
    log_iteration(
        workspace, iteration=0, score=state.best_score, delta=None,
        status=STATUS_BASELINE, tier="", change_summary="baseline", snapshot_ref="",
    )
    state.iterations.append({"iter": 0, "score": state.best_score, "status": STATUS_BASELINE})

    # Phase 0 short-circuit: already optimal.
    if state.best_score >= 1.0:
        state.exit_reason = "already_optimal"
        return _finalize(state, artifact_path, artifact_type, config, on_large_tier)

    start = time_fn()
    no_improve_streak = 0

    def reject(it, status, summary, tier=""):
        """Log + record a non-productive iteration; return True if we should stop."""
        nonlocal no_improve_streak
        log_iteration(workspace, iteration=it, score=state.best_score, delta=0.0,
                      status=status, tier=tier, change_summary=summary[:120])
        state.iterations.append({"iter": it, "score": state.best_score, "status": status,
                                 "tier": tier, "delta": 0.0, "summary": summary[:120]})
        no_improve_streak += 1
        return no_improve_streak >= config.convergence_window

    def over_budget():
        if config.max_duration_s is not None and (time_fn() - start) > config.max_duration_s:
            return "budget_duration"
        if config.max_tokens is not None and state.spent_tokens >= config.max_tokens:
            return "budget_tokens"
        return None

    for it in range(1, config.max_iterations + 1):
        reason = over_budget()
        if reason:
            state.exit_reason = reason
            break

        context = {
            "artifact_type": artifact_type,
            "best_score": state.best_score,
            "history": state.history[-5:],
            "iteration": it,
        }
        try:
            pres = proposer(context)
        except Exception as exc:  # proposer is external/LLM — never crash the loop
            if reject(it, STATUS_ERROR, f"proposer error: {exc}"):
                state.exit_reason = "stagnation"
                break
            continue

        state.spent_tokens += _usage_tokens(pres.get("usage"))
        proposal = pres.get("proposal")
        if not proposal or not proposal.get("diff_format"):
            if reject(it, STATUS_NO_CHANGE, "empty/invalid proposal"):
                state.exit_reason = "stagnation"
                break
            continue

        summary = str(proposal.get("change_summary", ""))[:120]
        tier = measure_tier(proposal, _old_section_lines(artifact_path, artifact_type, proposal))

        ok, why = validate_proposal(artifact_path, artifact_type, proposal)
        if not ok:
            if reject(it, STATUS_IMMUTABILITY, f"{summary} | {why}", tier):
                state.exit_reason = "stagnation"
                break
            continue

        # Re-check budget AFTER the proposer spend and BEFORE the (often most
        # expensive) evaluator call, so a single iteration cannot blow the cap.
        reason = over_budget()
        if reason:
            state.exit_reason = reason
            break

        ref = save_snapshot(artifact_path, workspace, it)
        sig_before = immutable_signatures(artifact_path, artifact_type)
        try:
            apply_proposal(artifact_path, artifact_type, proposal)
        except Exception as exc:
            restore_snapshot(artifact_path, ref)
            if reject(it, STATUS_ERROR, f"apply error: {exc}", tier):
                state.exit_reason = "stagnation"
                break
            continue

        if not immutable_preserved(sig_before, immutable_signatures(artifact_path, artifact_type)):
            restore_snapshot(artifact_path, ref)
            if reject(it, STATUS_IMMUTABILITY, f"{summary} | post-apply immutable change", tier):
                state.exit_reason = "stagnation"
                break
            continue

        ev = evaluator(artifact_path)
        state.spent_tokens += _usage_tokens(ev.get("usage"))
        score = ev["score"]
        secondary = ev.get("secondary")
        delta = score - state.best_score
        secondary_ok = (
            state.best_secondary is None or secondary is None
            or secondary >= state.best_secondary - sigma
        )

        if delta > sigma + _KEEP_EPS and secondary_ok:
            status = STATUS_KEEP
            state.best_score = score
            state.best_secondary = secondary
            if git_repo is not None:
                commit_all(git_repo, f"auto-improve iter-{it}: {summary}")
            no_improve_streak = 0 if delta >= config.min_improvement else no_improve_streak + 1
        elif abs(delta) <= sigma:
            status = STATUS_NO_SIGNAL
            restore_snapshot(artifact_path, ref)
            no_improve_streak += 1
        else:  # delta < -sigma, secondary regressed, or within the keep-epsilon
            status = STATUS_REVERT
            restore_snapshot(artifact_path, ref)
            no_improve_streak += 1

        log_iteration(workspace, iteration=it, score=score, delta=delta, status=status,
                      tier=tier, change_summary=summary, snapshot_ref=ref)
        state.iterations.append({"iter": it, "score": score, "status": status, "tier": tier,
                                 "delta": delta, "summary": summary})
        state.history.append({"summary": summary, "score": round(score, 3), "status": status})

        if state.best_score >= 1.0 and status == STATUS_KEEP:
            state.exit_reason = "optimal"
            break
        if no_improve_streak >= config.convergence_window:
            state.exit_reason = "stagnation"
            break
    else:
        state.exit_reason = "budget_iterations"

    return _finalize(state, artifact_path, artifact_type, config, on_large_tier)


def _finalize(state, artifact_path, artifact_type, config, on_large_tier) -> dict:
    kept = [i for i in state.iterations if i.get("status") == STATUS_KEEP]
    if on_large_tier and any(i.get("tier") == TIER_LARGE for i in kept):
        try:
            on_large_tier(artifact_path)
        except Exception as exc:  # adversarial review is advisory, never fatal
            print(f"WARNING: large-tier review failed: {exc}", file=sys.stderr)
    return {
        "best_score": state.best_score,
        "best_secondary": state.best_secondary,
        "exit_reason": state.exit_reason,
        "iterations": state.iterations,
        "kept": len(kept),
        "spent_tokens": state.spent_tokens,
    }


# ---------------------------------------------------------------------------
# Real proposer / evaluator factories
# ---------------------------------------------------------------------------
PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "change_summary": {"type": "string"},
        "rationale": {"type": "string"},
        "diff_format": {"type": "string", "enum": ["section-replace", "frontmatter-field", "dataset-op"]},
        "target_section": {"type": "string"},
        "new_content": {"type": "string"},
        "field": {"type": "string"},
        "value": {"type": "string"},
        "dataset_ops": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["change_summary", "diff_format"],
}


def _read_agent_prompt(name: str) -> str:
    p = Path(__file__).resolve().parent.parent / "agents" / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def build_default_proposer(artifact_path: Path, artifact_type: str, *, model: str | None):
    """Real Proposer backed by the vendor-agnostic LLMConfigManager."""
    try:
        from scripts.llm_config import LLMConfigManager  # type: ignore
    except ImportError:
        from llm_config import LLMConfigManager
    manager = LLMConfigManager("proposer")
    if model:
        manager.model_name = model
        manager.model_candidates = [model, *manager.fallback_models]
    system_prompt = _read_agent_prompt("proposer.md") or (
        "You improve software artifacts. Propose exactly ONE focused, safe change. "
        "Respond as JSON matching the requested schema."
    )

    def proposer(context: dict) -> dict:
        # Read fresh each iteration so the Proposer sees prior KEPT changes
        # rather than the stale build-time snapshot.
        artifact_text = _load_artifact_text(artifact_path, artifact_type)
        user = json.dumps({
            "artifact_type": artifact_type,
            "current_artifact": artifact_text[:12000],
            "best_score": context["best_score"],
            "previous_attempts": context["history"],
            "instruction": (
                "Propose ONE focused improvement. Use diff_format 'section-replace' for "
                "markdown skills/prompts/workflows (new_content must start with the same "
                "'## Header'), or 'dataset-op' for evals.json. Do not touch immutable parts."
            ),
        }, ensure_ascii=False)
        result = manager.generate_content_with_meta(system_prompt, user, response_schema=PROPOSAL_SCHEMA)
        proposal = _parse_proposal(result.get("text", ""))
        return {"proposal": proposal, "usage": result.get("usage", {})}

    return proposer


def _parse_proposal(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _load_artifact_text(artifact_path: Path, artifact_type: str) -> str:
    artifact_path = Path(artifact_path)
    if artifact_type in (ARTIFACT_SKILL, ARTIFACT_FULL_SKILL):
        return (artifact_path / "SKILL.md").read_text(encoding="utf-8")
    return artifact_path.read_text(encoding="utf-8")


def build_default_evaluator(
    artifact_type: str,
    *,
    eval_set: list[dict] | None,
    vendor: str,
    runs_per_query: int,
    model: str | None,
):
    """Real Evaluator. Deterministic scripts are called directly (no LLM middle-man)."""
    if artifact_type == ARTIFACT_DATASET:
        def evaluator(path: Path) -> dict:
            return {"score": score_dataset(Path(path))["score"], "secondary": None, "usage": {}}
        return evaluator

    if artifact_type in (ARTIFACT_SKILL, ARTIFACT_FULL_SKILL):
        backend = get_backend(vendor)

        def evaluator(path: Path) -> dict:
            if not getattr(backend, "available", False):
                raise RuntimeError(
                    f"vendor '{vendor}' has no agentic backend; cannot run skill-trigger eval"
                )
            res = backend.trigger_eval(
                Path(path), eval_set or [], runs_per_query=runs_per_query, model=model
            )
            return {"score": res["pass_rate"], "secondary": None, "usage": {}}
        return evaluator

    # prompt / workflow → vendor-agnostic LLM grading against the eval rubric.
    return _build_llm_grader(eval_set, model)


def build_trigger_evaluator(vendor: str, eval_set, runs_per_query, model, holder: dict | None = None):
    """Skill-trigger evaluator (capability B). Optionally stashes the raw
    run_eval output into `holder['raw']` so a description-Proposer can read the
    latest failed/false-trigger detail (improve_description pattern)."""
    backend = get_backend(vendor)

    def evaluator(path: Path) -> dict:
        if not getattr(backend, "available", False):
            raise RuntimeError(f"vendor '{vendor}' has no agentic backend for skill-trigger eval")
        res = backend.trigger_eval(Path(path), eval_set or [], runs_per_query=runs_per_query, model=model)
        if holder is not None:
            holder["raw"] = res.get("raw")
        return {"score": res["pass_rate"], "secondary": None, "usage": {}}

    return evaluator


def build_description_proposer(skill_path: Path, holder: dict, *, model: str | None):
    """Single-shot description optimizer via the vendor-agnostic LLM layer.

    Reuses the improve_description.py prompt strategy (generalize from failed /
    false triggers, ~100-200 words, imperative) but the OUTER loop owns the
    iteration count and budget — we do NOT nest run_loop.py (which would hide a
    second loop's spend from --max-tokens / --max-iterations).
    """
    try:
        from scripts.llm_config import LLMConfigManager  # type: ignore
    except ImportError:
        from llm_config import LLMConfigManager
    manager = LLMConfigManager("proposer")
    if model:
        manager.model_name = model
        manager.model_candidates = [model, *manager.fallback_models]
    name, _desc, body = parse_skill_md(skill_path)

    schema = {
        "type": "object",
        "properties": {
            "diff_format": {"type": "string", "enum": ["frontmatter-field"]},
            "field": {"type": "string", "enum": ["description"]},
            "value": {"type": "string"},
            "change_summary": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": ["diff_format", "field", "value", "change_summary"],
    }
    system = (
        "You optimize a Claude Code skill's frontmatter `description` (the CSO "
        "trigger text). Generalize from failures to broad user intent; do NOT "
        "enumerate specific queries. Keep it imperative, distinctive, ~100-200 "
        "words, under 1024 chars. Respond ONLY with the requested JSON."
    )

    def proposer(context: dict) -> dict:
        current_desc = parse_skill_md(skill_path)[1]
        raw = holder.get("raw") or {}
        results = raw.get("results", [])
        failed = [r for r in results if r.get("should_trigger") and not r.get("pass")]
        false = [r for r in results if not r.get("should_trigger") and not r.get("pass")]
        user = json.dumps({
            "skill_name": name,
            "current_description": current_desc,
            "best_trigger_score": context["best_score"],
            "failed_to_trigger": [r.get("query") for r in failed],
            "false_triggers": [r.get("query") for r in false],
            "previous_attempts": context["history"],
            "skill_body_excerpt": body[:4000],
        }, ensure_ascii=False)
        res = manager.generate_content_with_meta(system, user, response_schema=schema)
        proposal = _parse_proposal(res.get("text", ""))
        return {"proposal": proposal, "usage": res.get("usage", {})}

    return proposer


def _build_llm_grader(eval_set: list[dict] | None, model: str | None):
    try:
        from scripts.llm_config import LLMConfigManager  # type: ignore
    except ImportError:
        from llm_config import LLMConfigManager
    manager = LLMConfigManager("grader")
    if model:
        manager.model_name = model
        manager.model_candidates = [model, *manager.fallback_models]
    system = _read_agent_prompt("evaluator.md") or (
        "You are a strict grader. Given an artifact and rubric cases, return JSON "
        '{"passed": int, "total": int}.'
    )

    def evaluator(path: Path) -> dict:
        text = Path(path).read_text(encoding="utf-8")
        user = json.dumps({"artifact": text[:12000], "cases": eval_set or []}, ensure_ascii=False)
        res = manager.generate_content_with_meta(
            system, user,
            response_schema={"type": "object",
                             "properties": {"passed": {"type": "integer"}, "total": {"type": "integer"}},
                             "required": ["passed", "total"]},
        )
        try:
            verdict = json.loads(res.get("text", "{}"))
            total = max(int(verdict.get("total", 1)), 1)
            score = int(verdict.get("passed", 0)) / total
        except (json.JSONDecodeError, ValueError, TypeError):
            score = 0.0
        return {"score": score, "secondary": None, "usage": res.get("usage", {})}

    return evaluator


def build_adversarial_reviewer(workspace: Path, *, model: str | None):
    """Large-tier safety net: a fresh-context critic reviews the final winner.

    Advisory only — writes adversarial_review.md and never blocks the result.
    Uses the vendor-agnostic LLM layer so it works on any provider.
    """
    def review(artifact_path: Path) -> None:
        try:
            from scripts.llm_config import LLMConfigManager  # type: ignore
        except ImportError:
            from llm_config import LLMConfigManager
        manager = LLMConfigManager("grader")
        if model:
            manager.model_name = model
            manager.model_candidates = [model, *manager.fallback_models]
        ap = Path(artifact_path)
        text = (ap / "SKILL.md").read_text(encoding="utf-8") if ap.is_dir() else ap.read_text(encoding="utf-8")
        system = (
            "You are an adversarial reviewer. The artifact below was changed "
            "substantially (large tier). Find regressions, weakened safety, "
            "ambiguity, or overfitting the automated loop may have introduced. "
            "Be concrete and skeptical. List concerns as a short markdown bullet list."
        )
        out = manager.generate_content(system, text[:12000])
        (Path(workspace) / "adversarial_review.md").write_text(
            f"# Adversarial Review (large-tier)\n\n{out}\n", encoding="utf-8"
        )
    return review


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_report(workspace: Path, summary: dict, artifact_path: Path, artifact_type: str,
                 vendor: str, branch: str | None) -> Path:
    workspace = Path(workspace)
    lines = [
        f"# Improvement Report — {Path(artifact_path).name}",
        "",
        f"- Artifact type: `{artifact_type}`",
        f"- Vendor (agent-eval): `{vendor}`",
        f"- Exit reason: `{summary['exit_reason']}`",
        f"- Best score: **{summary['best_score']:.3f}**",
        f"- KEEP iterations: {summary['kept']}",
        f"- Tokens spent (measured): {summary['spent_tokens']}",
    ]
    if branch:
        lines.append(f"- Git isolation branch: `{branch}` (merge the winner explicitly)")
    lines += ["", "## Score trajectory", "", "| iter | status | tier | score | delta |", "|---|---|---|---|---|"]
    for i in summary["iterations"]:
        d = i.get("delta")
        lines.append(
            f"| {i['iter']} | {i.get('status','')} | {i.get('tier','')} | "
            f"{i['score']:.3f} | {'' if d is None else f'{d:+.3f}'} |"
        )
    report = workspace / "improvement_report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_duration(text: str | None) -> float | None:
    if not text:
        return None
    m = re.fullmatch(r"(\d+)([smh]?)", text.strip())
    if not m:
        raise ValueError(f"bad duration: {text!r}")
    value, unit = int(m.group(1)), m.group(2) or "s"
    return value * {"s": 1, "m": 60, "h": 3600}[unit]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Iteratively improve an artifact")
    parser.add_argument("--artifact-path", required=True)
    parser.add_argument("--artifact-type", default="auto")
    parser.add_argument("--target", default="auto",
                        help="auto|description|instructions|generic — which component to improve")
    parser.add_argument("--eval-set", default=None)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--provider", default="auto", help="auto|gemini|anthropic|openai")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--max-duration", default=None, help="e.g. 30m, 1800s, 1h")
    parser.add_argument("--noise-sigma", type=float, default=0.0)
    parser.add_argument("--runs-per-query", type=int, default=3)
    parser.add_argument("--git-isolation", action="store_true",
                        help="run on a dedicated auto-improve/* branch (requires clean tree)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    artifact_path = Path(args.artifact_path).resolve()
    workspace = Path(args.workspace).resolve()

    artifact_type = args.artifact_type
    if artifact_type == "auto":
        artifact_type = detect_type(artifact_path)

    if args.provider and args.provider != "auto":
        import os
        os.environ["DEFAULT_PROVIDER"] = args.provider

    vendor = detect_vendor(artifact_path.parent)
    eval_set = None
    if args.eval_set:
        raw = json.loads(Path(args.eval_set).read_text())
        if not isinstance(raw, list) or not all(isinstance(x, dict) for x in raw):
            print("ABORT: --eval-set must be a JSON list of objects.", file=sys.stderr)
            return 2
        if len(raw) > 1000:
            print(f"ABORT: --eval-set too large ({len(raw)} cases; cap 1000).", file=sys.stderr)
            return 2
        eval_set = raw

    # Phase 0: git hygiene / isolation
    git_repo = None
    branch = None
    repo_dir = artifact_path if artifact_path.is_dir() else artifact_path.parent
    if args.git_isolation and is_git_repo(repo_dir):
        if not is_clean(repo_dir):
            print("ABORT: uncommitted changes. Stash or commit before --git-isolation.",
                  file=sys.stderr)
            return 2
        branch = f"auto-improve/{artifact_path.name}/run"
        if create_branch(repo_dir, branch):
            git_repo = repo_dir
        else:
            print(f"WARNING: could not create branch {branch}; continuing without git isolation.",
                  file=sys.stderr)

    # Target dispatch. `description` uses the dedicated single-shot optimizer +
    # trigger evaluator sharing a holder; everything else uses the generic pair.
    if args.target == "description" and artifact_type in (ARTIFACT_SKILL, ARTIFACT_FULL_SKILL):
        holder: dict = {"raw": None}
        evaluator = build_trigger_evaluator(
            vendor, eval_set, args.runs_per_query, args.model, holder=holder
        )
        proposer = build_description_proposer(artifact_path, holder, model=args.model)
    else:
        proposer = build_default_proposer(artifact_path, artifact_type, model=args.model)
        evaluator = build_default_evaluator(
            artifact_type, eval_set=eval_set, vendor=vendor,
            runs_per_query=args.runs_per_query, model=args.model,
        )
    config = LoopConfig(
        max_iterations=args.max_iterations,
        max_tokens=args.max_tokens,
        max_duration_s=_parse_duration(args.max_duration),
        noise_sigma=args.noise_sigma,
    )

    summary = run_improvement_loop(
        artifact_path, artifact_type, workspace,
        proposer=proposer, evaluator=evaluator, config=config, git_repo=git_repo,
        on_large_tier=build_adversarial_reviewer(workspace, model=args.model),
    )
    report = write_report(workspace, summary, artifact_path, artifact_type, vendor, branch)
    if args.verbose:
        print(json.dumps(summary, indent=2), file=sys.stderr)
    print(json.dumps({"summary": summary, "report": str(report)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
