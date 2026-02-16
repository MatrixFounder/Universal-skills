# Skill Validator Report (Format Example)

> **Note**: This is a suggested report format for downstream consumers
> (e.g., CI/CD dashboards, Markdown reports). It is NOT consumed by
> `validate.py` directly — use `--json` output and render with your
> preferred template engine.

**Skill**: {{ skill_name }}
**Risk Level**: {{ risk_level }}
**Date**: {{ date }}

---

## Critical Issues
{{ critical_section }}

## Errors
{{ error_section }}

## Warnings
{{ warning_section }}

## Information
{{ info_section }}

---

## Summary
- **Critical**: {{ critical_count }}
- **Errors**: {{ error_count }}
- **Warnings**: {{ warning_count }}
- **Info**: {{ info_count }}

**Risk Level**: {{ risk_level }}

> **Note**: This is a static analysis report. A clean scan does NOT guarantee safety.
> Always perform a manual adversarial review (Phase 2) after scanning.