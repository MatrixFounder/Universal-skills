"""Claude Code agent-eval backend (validated).

Wraps skill-creator's run_eval.py — the proven `claude -p --output-format
stream-json` trigger detector — as a subprocess. We locate run_eval.py via:

    1. AUTO_IMPROVE_RUN_EVAL env var (explicit path), else
    2. the sibling skill-creator in the same repo:
       <skill-auto-improve>/../skill-creator/scripts/run_eval.py

If run_eval.py is not found, `available` is False and the orchestrator falls
back to LLM-only grading for generic artifacts (and skips skill-trigger eval).

The eval set for trigger evaluation is a JSON list of {query, should_trigger}.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _locate_run_eval() -> Path | None:
    # NOTE on trust: AUTO_IMPROVE_RUN_EVAL points at a script executed via the
    # Python interpreter. The process environment is part of the trust boundary
    # (like {PROVIDER}_API_KEY). We additionally require a .py file to reduce the
    # chance of pointing at an arbitrary executable by accident.
    env = os.environ.get("AUTO_IMPROVE_RUN_EVAL")
    if env:
        p = Path(env)
        if p.suffix == ".py" and p.is_file():
            return p
    # scripts/backends/claude.py -> skill root -> skills/ -> skill-creator
    skill_root = Path(__file__).resolve().parent.parent.parent
    candidate = skill_root.parent / "skill-creator" / "scripts" / "run_eval.py"
    return candidate if candidate.exists() else None


def _default_workers() -> int:
    return min(10, (os.cpu_count() or 4))


class ClaudeBackend:
    name = "claude"

    def __init__(self) -> None:
        self._run_eval = _locate_run_eval()

    @property
    def available(self) -> bool:
        return self._run_eval is not None

    def trigger_eval(
        self,
        skill_path: Path,
        eval_set: list[dict],
        *,
        runs_per_query: int = 3,
        timeout: int = 30,
        model: str | None = None,
        num_workers: int | None = None,
    ) -> dict:
        if not self.available:
            raise RuntimeError("run_eval.py not found; claude backend unavailable")

        workers = num_workers if num_workers and num_workers > 0 else _default_workers()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(eval_set, tmp)
            eval_path = tmp.name

        cmd = [
            sys.executable, str(self._run_eval),
            "--eval-set", eval_path,
            "--skill-path", str(skill_path),
            "--runs-per-query", str(runs_per_query),
            "--timeout", str(timeout),
            "--num-workers", str(workers),
        ]
        if model:
            cmd.extend(["--model", model])

        # Outer wall-clock so a hung run_eval can never block the loop forever.
        # Budget = per-query timeout * queries * runs, plus generous slack.
        outer_timeout = max(60, timeout * max(len(eval_set), 1) * max(runs_per_query, 1) + 60)
        try:
            res = subprocess.run(
                cmd, capture_output=True, text=True, check=False, timeout=outer_timeout
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"run_eval.py timed out after {outer_timeout}s") from exc
        finally:
            Path(eval_path).unlink(missing_ok=True)

        if res.returncode != 0:
            raise RuntimeError(f"run_eval.py failed: {res.stderr.strip()[:500]}")

        output = json.loads(res.stdout)
        summary = output.get("summary", {})
        passed = int(summary.get("passed", 0))
        total = int(summary.get("total", 0)) or 1
        return {
            "passed": passed,
            "total": total,
            "pass_rate": passed / total,
            "raw": output,
        }
