"""Bash-specific scanner: detects dangerous shell patterns."""
from scanners.patterns import BASH_PATTERNS


def scan_file_content(content, filename):
    """Scan a single file's content against dangerous bash patterns.

    Args:
        content: The file content as a string.
        filename: Relative path for reporting.

    Returns:
        List of issue dicts.
    """
    issues = []
    for compiled_re, severity, message in BASH_PATTERNS:
        if compiled_re.search(content):
            issues.append({
                "type": severity,
                "message": f"{message} in {filename}",
            })
    return issues
