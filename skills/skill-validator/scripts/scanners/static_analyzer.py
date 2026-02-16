"""Static analysis scanner: keywords, obfuscation, and Base64 payload inspection."""
import re
import math
import base64
from collections import Counter

from scanners.patterns import KEYWORD_PATTERNS, BASH_PATTERNS

# Regex to find Base64-encoded strings:
#   - Must be at a word boundary
#   - 20+ chars from the Base64 alphabet
#   - Length must be a multiple of 4 (valid Base64 padding)
#   - Optional trailing = or == padding
_B64_RE = re.compile(r'\b(?:[A-Za-z0-9+/]{4}){5,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?\b')

# Regex to find hex-encoded strings: 4+ consecutive \xNN sequences
_HEX_RE = re.compile(r'(?:\\x[0-9a-fA-F]{2}){4,}')


def calculate_entropy(s):
    """Calculate Shannon entropy of a string using collections.Counter (O(n))."""
    if not s:
        return 0.0
    length = len(s)
    counts = Counter(s)
    entropy = 0.0
    for count in counts.values():
        p = count / length
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def scan_obfuscation(content, filename):
    """Scan for obfuscation indicators: long lines and high-entropy strings."""
    issues = []
    lines = content.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Check for very long lines (often minified code or payloads)
        if len(stripped) > 500:
            issues.append({
                "type": "warning",
                "message": f"Long line detected ({len(stripped)} chars) at line {i+1} in {filename}. Possible obfuscation.",
                "line": i + 1,
            })

        # Check for high entropy (random-looking strings)
        if len(stripped) > 50 and calculate_entropy(stripped) > 5.8:
            issues.append({
                "type": "info",
                "message": f"High entropy string detected at line {i+1} in {filename}. Possible encrypted payload.",
                "line": i + 1,
            })
    return issues


def scan_keywords(content, filename):
    """Scan for high-risk keywords using pre-compiled regex patterns."""
    issues = []
    for compiled_re, message in KEYWORD_PATTERNS:
        if compiled_re.search(content):
            issues.append({
                "type": "info",
                "message": f"{message} in {filename}",
            })
    return issues


def scan_base64_payloads(content, filename):
    """Detect Base64-encoded strings, decode them, and re-scan the decoded content.

    This catches attackers who hide malicious code inside Base64 payloads.
    Uses KEYWORD_PATTERNS and BASH_PATTERNS from the shared patterns module.
    """
    issues = []
    for match in _B64_RE.finditer(content):
        candidate = match.group(0)
        try:
            decoded = base64.b64decode(candidate).decode("utf-8", errors="strict")
        except Exception:
            continue  # Not valid Base64 or not valid UTF-8

        # Only re-scan if the decoded content looks like it could contain code
        if len(decoded) < 5 or not decoded.isprintable():
            continue

        # Re-scan decoded content against keyword patterns
        for compiled_re, message in KEYWORD_PATTERNS:
            if compiled_re.search(decoded):
                issues.append({
                    "type": "warning",
                    "message": f"Hidden {message} found inside Base64 payload at offset {match.start()} in {filename}",
                    "line": content[:match.start()].count('\n') + 1,
                })

        # Re-scan decoded content against bash dangerous patterns
        for compiled_re, severity, msg in BASH_PATTERNS:
            if compiled_re.search(decoded):
                issues.append({
                    "type": "critical",
                    "message": f"Hidden {msg} found inside Base64 payload at offset {match.start()} in {filename}",
                    "line": content[:match.start()].count('\n') + 1,
                })

    return issues


def scan_hex_encoded(content, filename):
    """Detect hex-encoded strings (\\xNN sequences) and re-scan decoded content.

    Catches attackers who hide malicious code inside hex-escaped strings.
    """
    issues = []
    for match in _HEX_RE.finditer(content):
        hex_str = match.group(0)
        try:
            # Convert \\x41\\x42 -> AB
            decoded = bytes(
                int(h, 16) for h in re.findall(r'\\x([0-9a-fA-F]{2})', hex_str)
            ).decode("utf-8", errors="strict")
        except Exception:
            continue

        if len(decoded) < 4 or not decoded.isprintable():
            continue

        line_num = content[:match.start()].count('\n') + 1

        # Re-scan decoded content against keyword patterns
        for compiled_re, message in KEYWORD_PATTERNS:
            if compiled_re.search(decoded):
                issues.append({
                    "type": "warning",
                    "message": f"Hidden {message} found inside hex-encoded string at line {line_num} in {filename}",
                    "line": line_num,
                })

        # Re-scan decoded content against bash dangerous patterns
        for compiled_re, severity, msg in BASH_PATTERNS:
            if compiled_re.search(decoded):
                issues.append({
                    "type": "critical",
                    "message": f"Hidden {msg} found inside hex-encoded string at line {line_num} in {filename}",
                    "line": line_num,
                })

    return issues


def scan_file_content(content, filename):
    """Run all static analysis checks on a single file's content.

    Args:
        content: The file content as a string.
        filename: Relative path for reporting.

    Returns:
        List of issue dicts.
    """
    issues = []
    issues.extend(scan_keywords(content, filename))
    issues.extend(scan_obfuscation(content, filename))
    issues.extend(scan_base64_payloads(content, filename))
    issues.extend(scan_hex_encoded(content, filename))
    return issues
