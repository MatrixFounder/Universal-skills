"""Structure checker: validates SKILL.md frontmatter and directory layout."""
import os


def check_structure(skill_path):
    """Validate the structural integrity and frontmatter of a skill directory.

    Checks:
    - SKILL.md exists and has valid YAML frontmatter with required fields.
    - Standard directories (scripts/, examples/, assets/, references/) are present and non-empty.

    Args:
        skill_path: Absolute path to the skill root directory.

    Returns:
        List of issue dicts with type, message keys.
    """
    issues = []
    skill_md_path = os.path.join(skill_path, "SKILL.md")

    if not os.path.exists(skill_md_path):
        return [{"type": "critical", "message": "Missing SKILL.md"}]

    try:
        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # --- Frontmatter parsing ---
        if content.startswith("---"):
            try:
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter_raw = parts[1]
                    frontmatter = {}
                    for line in frontmatter_raw.splitlines():
                        line = line.strip()
                        if line and ":" in line and not line.startswith("#"):
                            key, val = line.split(":", 1)
                            val = val.strip()
                            # Handle quoted values: strip surrounding quotes
                            if (val.startswith('"') and val.endswith('"')) or \
                               (val.startswith("'") and val.endswith("'")):
                                val = val[1:-1]
                            frontmatter[key.strip()] = val

                    required_fields = ["name", "description", "version"]
                    for field in required_fields:
                        if field not in frontmatter:
                            issues.append({
                                "type": "error",
                                "message": f"Missing frontmatter field: {field}",
                            })
                        elif not frontmatter[field]:
                            issues.append({
                                "type": "error",
                                "message": f"Empty frontmatter field: {field}",
                            })
                else:
                    issues.append({"type": "error", "message": "Invalid frontmatter format"})
            except Exception as e:
                issues.append({"type": "error", "message": f"Error parsing frontmatter: {e}"})
        else:
            issues.append({"type": "error", "message": "Missing YAML frontmatter (must start with ---)"})

    except Exception as e:
        issues.append({"type": "error", "message": f"Error reading SKILL.md: {e}"})

    # --- Directory checks ---
    standard_dirs = ["scripts", "examples", "assets", "references"]
    for dirname in standard_dirs:
        dir_path = os.path.join(skill_path, dirname)
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            entries = [e for e in os.listdir(dir_path) if not e.startswith('.')]
            if not entries:
                issues.append({
                    "type": "warning",
                    "message": f"Directory '{dirname}/' exists but is empty. Cleanup recommended.",
                })
        else:
            issues.append({
                "type": "info",
                "message": f"Optional directory '{dirname}/' is missing.",
            })

    # --- File integrity cross-reference (P7) ---
    # Extract file paths referenced in SKILL.md and check they exist
    issues.extend(_check_referenced_files(skill_path, content))

    return issues


def _check_referenced_files(skill_path, skill_md_content):
    """Cross-reference file paths mentioned in SKILL.md against the filesystem.

    Extracts paths that look like relative file references from:
    - Backtick-quoted paths (e.g., `scripts/validate.py`)
    - Markdown links (e.g., [text](scripts/validate.py))

    Only checks paths that start with known skill directories.
    """
    import re
    issues = []
    known_prefixes = ("scripts/", "examples/", "assets/", "references/")

    # Extract backtick-quoted paths
    backtick_paths = re.findall(r'`([^`]+)`', skill_md_content)
    # Extract markdown link targets
    link_paths = re.findall(r'\]\(([^)]+)\)', skill_md_content)

    candidates = set()
    for path in backtick_paths + link_paths:
        path = path.strip()
        # Only check relative paths that start with known directories
        if any(path.startswith(prefix) for prefix in known_prefixes):
            # Skip if it looks like a URL or placeholder
            if '://' in path or '<' in path or '{{' in path:
                continue
            candidates.add(path)

    for ref_path in sorted(candidates):
        full_path = os.path.join(skill_path, ref_path)
        if not os.path.exists(full_path):
            issues.append({
                "type": "warning",
                "message": f"SKILL.md references '{ref_path}' but it does not exist on disk.",
            })

    return issues

