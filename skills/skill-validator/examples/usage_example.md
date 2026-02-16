# Usage Example: skill-validator

## Scanning a Third-Party Skill

```bash
# For untrusted skills, always use --no-scanignore:
python3 scripts/validate.py /path/to/downloaded-skill --no-scanignore

# Example output (clean skill):
# ==========================================
# Skill Validator Report for: my-clean-skill
# Risk Level: SAFE
# ==========================================
# [INFO] Optional directory 'references/' is missing.
#
# Summary: 0 Critical, 0 Errors, 0 Warnings, 1 Info
# PASSED.
```

## Scanning a Malicious Skill

```bash
python3 scripts/validate.py /path/to/suspicious-skill --no-scanignore

# Example output (malicious skill):
# ==========================================
# Skill Validator Report for: suspicious-skill
# Risk Level: DANGER
# ==========================================
# [CRITICAL] Critical: Piping curl to bash-shell in scripts/install.sh
# [CRITICAL] Critical: Recursive root deletion detected in scripts/cleanup.sh
# [WARNING] Warning: Usage of sudo in scripts/setup.sh
# [INFO] Control Flow: Use of eval() in scripts/main.py
#
# Summary: 2 Critical, 0 Errors, 1 Warnings, 1 Info
# FAILED: Critical security issues detected.
```

## JSON Output for CI/CD

```bash
python3 scripts/validate.py /path/to/skill --json --no-scanignore
```

```json
{
  "skill": "my-skill",
  "risk_level": "SAFE",
  "issues": [
    {
      "type": "info",
      "message": "Optional directory 'references/' is missing."
    }
  ],
  "summary": {
    "critical": 0,
    "error": 0,
    "warning": 0,
    "info": 1
  }
}
```

## Strict Mode for CI/CD

```bash
# Exit code 2 if any warnings found — useful for pipeline gating
python3 scripts/validate.py /path/to/skill --strict --no-scanignore
```

## CLI Flags

| Flag | Description |
| :--- | :--- |
| `--json` | Structured JSON output. |
| `--no-scanignore` | Ignore `.scanignore` (use for untrusted skills). |
| `--strict` | Exit 2 on warnings. |
| `--version` | Print version. |

## Risk Levels

| Level | Meaning |
| :--- | :--- |
| **SAFE** | No critical or error issues. Scanner ran cleanly. |
| **CAUTION** | Some errors (e.g., unreadable files) but no critical threats. |
| **DANGER** | Critical security issues detected. **Do NOT use the skill.** |