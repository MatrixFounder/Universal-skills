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

def main():
    parser = argparse.ArgumentParser(description="Full Audit Wrapper for Agents")
    parser.add_argument("skill_path", help="Path to the skill directory")
    args = parser.parse_args()

    skill_path = os.path.abspath(args.skill_path)
    if not os.path.isdir(skill_path):
        print(f"Error: Directory not found: {skill_path}")
        sys.exit(1)

    print(f"🔹 Starting Full Audit for: {os.path.basename(skill_path)}...")
    
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
        print(f"❌ Critical Error running validator: {e}")
        print(result.stderr if 'result' in locals() else "")
        sys.exit(1)

    # 2. Print Summary
    risk = output.get("risk_level", "UNKNOWN")
    summary = output.get("summary", {})
    issues = output.get("issues", [])

    print(f"\n📊 Audit Report")
    print(f"Risk Level: {risk}")
    print(f"Critical: {summary.get('critical', 0)} | Error: {summary.get('error', 0)} | Warning: {summary.get('warning', 0)} | Info: {summary.get('info', 0)}")
    
    if not issues:
        print("\n✅ No issues found. Skill appears clean.")
        sys.exit(0)

    # 3. Print Issues
    print("\n🔎 Findings:")
    for issue in issues:
        type_upper = issue.get('type', 'info').upper()
        print(f"[{type_upper}] {issue.get('message')}")
        if 'line' in issue:
            print(f"    Line: {issue['line']}")

    # 4. Phase 3: Agent-Assisted Verification Prompts
    # If we have warnings/info, we instruct the Agent to verify them.
    if summary.get("warning", 0) > 0 or summary.get("info", 0) > 0:
        print("\n" + "="*60)
        print("🤖 AGENT INSTRUCTION: PHASE 3 VERIFICATION REQUIRED")
        print("="*60)
        print("Some issues require manual verification. Please use the following prompts to analyze the flagged content:\n")

        # Load prompts
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompts_dir = os.path.join(base_dir, "references", "prompts")
        
        try:
            with open(os.path.join(prompts_dir, "jailbreak_check.md"), "r") as f:
                jb_prompt = f.read()
            with open(os.path.join(prompts_dir, "alignment_check.md"), "r") as f:
                align_prompt = f.read()
            
            print(f"👉 IF checking for Jailbreaks/Injection, use this system prompt:\n")
            print("-" * 20)
            print(jb_prompt)
            print("-" * 20)
            print("\n")
            
            print(f"👉 IF checking for Business Scope alignment, use this system prompt:\n")
            print("-" * 20)
            print(align_prompt)
            print("-" * 20)
            
        except Exception as e:
            print(f"⚠️ Could not load verification prompts: {e}")

    if risk == "DANGER":
        sys.exit(1)
    elif risk == "CAUTION":
        sys.exit(0) # Exit 0 to allow Agent to proceed with caution
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
