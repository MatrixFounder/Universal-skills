"""AI Threat Scanner: Detects prompt injection, harmful instructions, and PII leaks."""
from scanners.patterns import AI_PATTERNS, PII_PATTERNS


def scan_file_content(content, filename):
    """Scan a single file's content against AI threat and PII patterns.

    Args:
        content: The file content as a string.
        filename: Relative path for reporting.

    Returns:
        List of issue dicts.
    """
    issues = []
    
    # Check AI Threat Patterns
    for compiled_re, severity, message in AI_PATTERNS:
        match = compiled_re.search(content)
        if match:
            line_num = content[:match.start()].count('\n') + 1
            issues.append({
                "type": "warning",
                "message": f"{message} in {filename}",
                "line": line_num,
                "category": "AI_SAFETY" 
            })

    # Check PII Patterns
    for compiled_re, severity, message in PII_PATTERNS:
        match = compiled_re.search(content)
        if match:
            line_num = content[:match.start()].count('\n') + 1
            # Redact the match in the report for safety (optional, but good practice)
            # For now, just reporting presence.
            issues.append({
                "type": "warning",
                "message": f"{message} detected in {filename}",
                "line": line_num,
                "category": "DATA_PRIVACY"
            })

    return issues
