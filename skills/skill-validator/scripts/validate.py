"""Skill Validator: Security & Compliance Audit.

Main entry point that orchestrates structure checks, bash scanning,
static analysis, and Base64 payload inspection in a single file pass.
"""
import sys
import os
import argparse
import json

# Add current directory to path so we can import scanners
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from scanners import structure_check, bash_scanner, static_analyzer, ai_scanner
except ImportError as e:
    # Defer error reporting until we know the output format
    _import_error = str(e)
    structure_check = None
    bash_scanner = None
    static_analyzer = None
    ai_scanner = None
else:
    _import_error = None

# Version must match SKILL.md frontmatter
VERSION = "1.3"

# Binary file extensions to skip during scanning
BINARY_EXTENSIONS = frozenset((
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.bmp', '.webp',
    '.pdf', '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.mp3', '.mp4', '.wav', '.avi', '.mov',
    '.pyc', '.pyo', '.so', '.dylib', '.dll',
))

# Maximum file size to scan (10 MB). Files larger than this are skipped.
MAX_FILE_SIZE = 10 * 1024 * 1024

# P6: Magic number signatures for polyglot detection.
# Maps binary magic bytes to their file type description.
MAGIC_SIGNATURES = {
    b'\x7fELF':      'ELF executable',
    b'MZ':           'PE/Windows executable',
    b'\xfe\xed\xfa': 'Mach-O binary',
    b'\xcf\xfa\xed': 'Mach-O 64-bit binary',
    b'PK':           'ZIP archive',
    b'\x1f\x8b':     'GZIP compressed',
    b'\x89PNG':      'PNG image',
    b'\xff\xd8\xff': 'JPEG image',
    b'GIF8':         'GIF image',
    b'%PDF':         'PDF document',
}

# Extensions that should contain text, not binary data
TEXT_EXTENSIONS = frozenset((
    '.py', '.sh', '.bash', '.js', '.ts', '.rb', '.pl',
    '.md', '.txt', '.yml', '.yaml', '.json', '.toml',
    '.html', '.css', '.xml', '.csv', '.cfg', '.ini',
))


def check_polyglot(file_path, rel_path):
    """Check if a text-extension file has a binary magic number (polyglot attack)."""
    _, ext = os.path.splitext(file_path)
    if ext.lower() not in TEXT_EXTENSIONS:
        return []

    try:
        with open(file_path, 'rb') as f:
            header = f.read(8)
    except Exception:
        return []

    for magic, description in MAGIC_SIGNATURES.items():
        if header.startswith(magic):
            return [{
                "type": "critical",
                "message": f"Polyglot file detected: {rel_path} has text extension but contains {description} magic bytes",
            }]
    return []


def print_result(result):
    """Print a single issue with color-coded severity prefix."""
    type_color = {
        "critical": "\033[91m[CRITICAL]\033[0m",
        "error":    "\033[91m[ERROR]\033[0m",
        "warning":  "\033[93m[WARNING]\033[0m",
        "info":     "\033[94m[INFO]\033[0m",
    }
    prefix = type_color.get(result.get("type", "info"), "[UNKNOWN]")
    print(f"{prefix} {result.get('message')}")
    if "line" in result:
        print(f"    Line: {result['line']}")


def load_scanignore(skill_path, honor_scanignore):
    """Load .scanignore file and return a set of relative paths to skip.

    Args:
        skill_path: Path to skill directory.
        honor_scanignore: If False, .scanignore is ignored entirely.

    Returns:
        Set of relative paths to exclude from content scanning.
    """
    if not honor_scanignore:
        return set()

    ignore_path = os.path.join(skill_path, ".scanignore")
    ignored = set()
    if os.path.exists(ignore_path):
        try:
            with open(ignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        ignored.add(line)
        except Exception as e:
            # M3: Report the error instead of swallowing it
            print(f"\033[93m[WARNING] Could not read .scanignore: {e}\033[0m",
                  file=sys.stderr)
    return ignored


def walk_and_scan(skill_path, honor_scanignore, enable_ai_scan=False):
    """Single os.walk pass that feeds each file to all scanners.

    Respects .scanignore only when honor_scanignore is True.
    Enforces MAX_FILE_SIZE limit per file.

    Returns:
        List of issue dicts from bash_scanner, static_analyzer, and optionally ai_scanner.
    """
    ignored_paths = load_scanignore(skill_path, honor_scanignore)
    all_issues = []
    for root, dirs, files in os.walk(skill_path):
        # Skip hidden directories and __pycache__
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']

        for filename in files:
            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, skill_path)

            # Skip files listed in .scanignore
            if rel_path in ignored_paths:
                continue

            # Skip binary files by extension
            _, ext = os.path.splitext(filename)
            if ext.lower() in BINARY_EXTENSIONS:
                continue

            # M1: Skip oversized files to prevent OOM
            try:
                file_size = os.path.getsize(file_path)
            except OSError:
                file_size = 0
            if file_size > MAX_FILE_SIZE:
                all_issues.append({
                    "type": "warning",
                    "message": f"Skipped oversized file ({file_size // 1024 // 1024}MB): {rel_path}",
                })
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                all_issues.append({
                    "type": "error",
                    "message": f"Unreadable file: {rel_path}: {e}",
                })
                continue

            # P6: Check for polyglot files (magic number vs text extension)
            all_issues.extend(check_polyglot(file_path, rel_path))

            # Feed content to scanners
            all_issues.extend(bash_scanner.scan_file_content(content, rel_path))
            all_issues.extend(static_analyzer.scan_file_content(content, rel_path))
            
            if enable_ai_scan:
                all_issues.extend(ai_scanner.scan_file_content(content, rel_path))

    return all_issues


def compute_risk_level(issues):
    """Compute a risk level based on the scan results.

    Returns:
        A string: "SAFE", "CAUTION", or "DANGER".
        SAFE    = no critical/error issues, scanner coverage was complete.
        CAUTION = errors (e.g., unreadable files) but no critical threats.
        DANGER  = critical security issues detected.
    """
    has_critical = any(i.get("type") == "critical" for i in issues)
    has_error = any(i.get("type") == "error" for i in issues)
    if has_critical:
        return "DANGER"
    if has_error:
        return "CAUTION"
    return "SAFE"


def main():
    parser = argparse.ArgumentParser(description="Skill Validator: Security & Compliance Audit")
    parser.add_argument("skill_path", help="Path to the skill directory to validate")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--version", action="version", version=f"skill-validator {VERSION}")
    parser.add_argument(
        "--no-scanignore", action="store_true",
        help="Ignore .scanignore files (recommended for untrusted skills)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit with code 2 if warnings are found (useful for CI/CD)",
    )
    parser.add_argument(
        "--ai-scan", action="store_true",
        help="Enable AI threat detection (prompt injection, jailbreaks)",
    )
    args = parser.parse_args()

    # Handle import errors in the correct output format
    if _import_error:
        err = {"type": "error", "message": f"Scanner import failed: {_import_error}"}
        if args.json:
            print(json.dumps({"error": err}, indent=2))
        else:
            print(f"\033[91m[ERROR] {err['message']}\033[0m")
        sys.exit(1)

    skill_path = os.path.abspath(args.skill_path)
    if not os.path.isdir(skill_path):
        err = {"type": "error", "message": f"Directory not found: {skill_path}"}
        if args.json:
            print(json.dumps({"error": err}, indent=2))
        else:
            print(f"\033[91m[ERROR] {err['message']}\033[0m")
        sys.exit(1)

    all_issues = []

    # 1. Structure Check
    all_issues.extend(structure_check.check_structure(skill_path))

    # 2. Single-pass file scanning (bash + static analysis + optional AI scan)
    # .scanignore from the scanned skill is honored by default.
    # Use --no-scanignore to disable it when scanning untrusted skills.
    honor_scanignore = not args.no_scanignore
    all_issues.extend(walk_and_scan(skill_path, honor_scanignore, args.ai_scan))

    # 3. Compute risk level
    risk_level = compute_risk_level(all_issues)

    critical_count = len([i for i in all_issues if i.get("type") == "critical"])

    error_count = len([i for i in all_issues if i.get("type") == "error"])
    warning_count = len([i for i in all_issues if i.get("type") == "warning"])
    info_count = len([i for i in all_issues if i.get("type") == "info"])

    if args.json:
        output = {
            "skill": os.path.basename(skill_path),
            "risk_level": risk_level,
            "issues": all_issues,
            "summary": {
                "critical": critical_count,
                "error": error_count,
                "warning": warning_count,
                "info": info_count,
            },
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\n==========================================")
        print(f"Skill Validator Report for: {os.path.basename(skill_path)}")
        print(f"Risk Level: {risk_level}")
        print(f"==========================================")

        if not all_issues:
            print("\n\033[92m[SUCCESS] No issues found!\033[0m")
            sys.exit(0)  # L2: Early exit for clean path

        sorted_issues = sorted(
            all_issues,
            key=lambda x: {"critical": 0, "error": 1, "warning": 2, "info": 3}.get(
                x.get("type", "info"), 4
            ),
        )
        for issue in sorted_issues:
            print_result(issue)

        print(f"\nSummary: {critical_count} Critical, {error_count} Errors, "
              f"{warning_count} Warnings, {info_count} Info")

        if critical_count > 0:
            print("\033[91mFAILED: Critical security issues detected.\033[0m")
            sys.exit(1)
        elif error_count > 0:
            print("\033[91mFAILED: Structural errors detected.\033[0m")
            sys.exit(1)
        elif warning_count > 0 and args.strict:
            print("\033[93mFAILED (strict): Warnings treated as errors.\033[0m")
            sys.exit(2)  # L3: Distinct exit code for warnings in strict mode
        else:
            print("\033[93mPASSED with Warnings.\033[0m" if warning_count > 0
                  else "\033[92mPASSED.\033[0m")

    sys.exit(0)


if __name__ == "__main__":
    main()
