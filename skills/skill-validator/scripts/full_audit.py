"""Full Audit Wrapper: Runs validation and prompts Agent for Phase 3 verification.

This script is designed for AI Agents to run. It performs a full static scan
and then *automatically constructs* the "Phase 3" verification instructions
if suspicious content is found.

Usage:
    python3 scripts/full_audit.py <skill_path>
"""
import sys
import os
import json
import subprocess
import argparse

# `validate.py` is this skill's stdlib-only helper module and sits beside
# this file; it carries the locale-tolerant writers (Apache-2.0 copy — the
# office skills' `_errors.py` is proprietary and cannot be imported here).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate import HumanArgumentParser, say  # noqa: E402

def main():
    parser = HumanArgumentParser(description="Full Audit Wrapper for Agents")
    parser.add_argument("skill_path", help="Path to the skill directory")
    args = parser.parse_args()

    skill_path = os.path.abspath(args.skill_path)
    if not os.path.isdir(skill_path):
        say(f"Error: Directory not found: {skill_path}")
        sys.exit(1)

    say(f"🔹 Starting Full Audit for: {os.path.basename(skill_path)}...")
    
    # 1. Run validate.py with all checks enabled
    cmd = [
        sys.executable,
        os.path.join(os.path.dirname(__file__), "validate.py"),
        skill_path,
        "--ai-scan",
        "--no-scanignore",
        "--json"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = json.loads(result.stdout)
    except Exception as e:
        say(f"❌ Critical Error running validator: {e}")
        say(result.stderr if 'result' in locals() else "")
        sys.exit(1)

    # 2. Print Summary
    risk = output.get("risk_level", "UNKNOWN")
    summary = output.get("summary", {})
    issues = output.get("issues", [])

    say(f"\n📊 Audit Report")
    say(f"Risk Level: {risk}")
    say(f"Critical: {summary.get('critical', 0)} | Error: {summary.get('error', 0)} | Warning: {summary.get('warning', 0)} | Info: {summary.get('info', 0)}")
    
    if not issues:
        say("\n✅ No issues found. Skill appears clean.")
        sys.exit(0)

    # 3. Print Issues
    say("\n🔎 Findings:")
    for issue in issues:
        type_upper = issue.get('type', 'info').upper()
        say(f"[{type_upper}] {issue.get('message')}")
        if 'line' in issue:
            say(f"    Line: {issue['line']}")

    # 4. Phase 3: Agent-Assisted Verification Prompts
    # If we have warnings/info, we instruct the Agent to verify them.
    if summary.get("warning", 0) > 0 or summary.get("info", 0) > 0:
        say("\n" + "="*60)
        say("🤖 AGENT INSTRUCTION: PHASE 3 VERIFICATION REQUIRED")
        say("="*60)
        say("Some issues require manual verification. Please use the following prompts to analyze the flagged content:\n")

        # Load prompts
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompts_dir = os.path.join(base_dir, "references", "prompts")
        
        try:
            with open(os.path.join(prompts_dir, "jailbreak_check.md"), "r") as f:
                jb_prompt = f.read()
            with open(os.path.join(prompts_dir, "alignment_check.md"), "r") as f:
                align_prompt = f.read()
            
            say(f"👉 IF checking for Jailbreaks/Injection, use this system prompt:\n")
            say("-" * 20)
            say(jb_prompt)
            say("-" * 20)
            say("\n")
            
            say(f"👉 IF checking for Business Scope alignment, use this system prompt:\n")
            say("-" * 20)
            say(align_prompt)
            say("-" * 20)
            
        except Exception as e:
            say(f"⚠️ Could not load verification prompts: {e}")

    if risk == "DANGER":
        sys.exit(1)
    elif risk == "CAUTION":
        sys.exit(0) # Exit 0 to allow Agent to proceed with caution
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
