#!/usr/bin/env python3
"""Child process for `test_stdout_broken_pipe.py`.

Runs `auto_improve.main()` with the LLM-backed loop and the preflight checks
(agentic backend, provider key/SDK) stubbed out, so the real
`print(json.dumps(...), flush=True)` at the end of `main()` executes on a payload
of a caller-chosen size. Argv: <target_bytes> <workdir>.
"""
import importlib.util
import json
import pathlib
import sys

TARGET_BYTES, WORKDIR = int(sys.argv[1]), pathlib.Path(sys.argv[2])
SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
WORKDIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("under_test", SCRIPTS / "auto_improve.py")
m = importlib.util.module_from_spec(spec)
sys.modules["under_test"] = m
spec.loader.exec_module(m)

iterations, i = [], 0
while len(json.dumps(iterations, indent=2)) < TARGET_BYTES:
    iterations.append({"n": i, "status": "KEEP", "score": 0.5,
                       "note": "n" * 60, "usage": {"total_tokens": 10}})
    i += 1
summary = {"status": "KEEP", "exit_reason": "budget_iterations", "iterations": iterations}

m.run_improvement_loop = lambda *a, **k: summary
m.write_report = lambda *a, **k: WORKDIR / "report.md"
m.build_default_proposer = lambda *a, **k: (lambda ctx: {"proposal": None, "usage": {}})
m.build_default_evaluator = lambda *a, **k: (lambda p: {"score": 0.0, "usage": {}})
m.build_adversarial_reviewer = lambda *a, **k: None
m.detect_vendor = lambda *a, **k: "claude"


class _AvailableBackend:  # the preflight needs an agentic backend for a skill run
    available = True


m.get_backend = lambda *a, **k: _AvailableBackend()
m._locate_validate_skill = lambda: None
import llm_config  # noqa: E402  (preflight: no key/SDK is needed for a stubbed loop)
llm_config.preflight_provider = lambda *a, **k: None

artifact = WORKDIR / "artifact-skill"
artifact.mkdir(exist_ok=True)
(artifact / "SKILL.md").write_text(
    "---\nname: artifact-skill\ndescription: Use when driving auto_improve.main() "
    "for broken-pipe measurement.\n---\n\n# artifact-skill\n")

eval_set = WORKDIR / "evals.json"
eval_set.write_text(json.dumps([{"query": "q", "should_trigger": True}]))

sys.argv = ["auto_improve.py", "--artifact-path", str(artifact),
            "--workspace", str(WORKDIR / "ws"), "--artifact-type", "skill",
            "--eval-set", str(eval_set)]
sys.exit(m.main())
