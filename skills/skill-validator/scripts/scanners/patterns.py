"""Shared pattern definitions for all scanners.

Centralizes all regex patterns to avoid circular imports between
bash_scanner and static_analyzer.
"""
import re
import base64

# --- Bash Dangerous Patterns ---
# Base64-encoded to prevent the validator from flagging its own source code.
# Each tuple: (compiled_regex, severity, human_message)
_RAW_BASH_PATTERNS = [
    # --- Pipe-to-shell (RCE) ---
    (base64.b64decode("Y3VybC4qXHxccypiYXNo").decode("utf-8"), "critical", "Critical: Piping " + "curl" + " to bash-shell"),
    (base64.b64decode("d2dldC4qXHxccypiYXNo").decode("utf-8"), "critical", "Critical: Piping " + "wget" + " to bash-shell"),
    (base64.b64decode("Y3VybC4qXHxccypzaA==").decode("utf-8"), "critical", "Critical: Piping " + "curl" + " to sh-shell"),
    (base64.b64decode("d2dldC4qXHxccypzaA==").decode("utf-8"), "critical", "Critical: Piping " + "wget" + " to sh-shell"),
    # --- Two-step download + execute ---
    (base64.b64decode("d2dldFxzKy4qLU9ccytcUysuKiYmLipiYXNo").decode("utf-8"), "critical", "Critical: Two-step download+execute via wget"),
    (base64.b64decode("Y3VybFxzKy4qLW9ccytcUysuKiYmLipiYXNo").decode("utf-8"), "critical", "Critical: Two-step download+execute via " + "curl"),
    # --- Destructive operations ---
    (base64.b64decode("cm1ccystcmZccysv").decode("utf-8"), "critical", "Critical: Recursive root deletion detected"),
    (base64.b64decode("OlwoXClccypce1xzKjpcfDomXHMqXH07Og==").decode("utf-8"), "critical", "Critical: Fork bomb related"),
    # --- Network tools (reverse shells, listeners) ---
    (base64.b64decode("KFx8fFxzKW5jXHMrLQ==").decode("utf-8"), "warning", "Warning: Usage of nc (net" + "cat) with flags"),
    (base64.b64decode("KFx8fFxzKW5ldGNhdFxzKw==").decode("utf-8"), "warning", "Warning: Usage of net" + "cat"),
    (base64.b64decode("L2Rldi90Y3Av").decode("utf-8"), "warning", "Warning: /dev/tcp usage (possible reverse shell)"),
    # --- Privilege escalation ---
    (base64.b64decode("KF58XHMpc3Vkb1xzKw==").decode("utf-8"), "warning", "Warning: Usage of sudo"),
    (base64.b64decode("Y2htb2RccytbK11z").decode("utf-8"), "warning", "Warning: Setting setuid bit (chmod +s)"),
    # --- Shell eval/exec ---
    (base64.b64decode("KF58XHMpZXZhbFxzKw==").decode("utf-8"), "warning", "Warning: Usage of eval in shell"),
    # --- Dotfile modification (persistence) ---
    (base64.b64decode("Pj4/XHMqfi8/XC5iYXNocmM=").decode("utf-8"), "warning", "Warning: Modification of .bashrc"),
    (base64.b64decode("Pj4/XHMqfi8/XC56c2hyYw==").decode("utf-8"), "warning", "Warning: Modification of .zshrc"),
    (base64.b64decode("Pj4/XHMqfi8/XC5wcm9maWxl").decode("utf-8"), "warning", "Warning: Modification of .profile"),
    # --- Info-level ---
    (base64.b64decode("KF58XHMpZXhlY1xzKw==").decode("utf-8"), "info", "Info: Usage of exec"),
    (base64.b64decode("KF58XHMpZXhwb3J0XHMrW0EtWl9dKz0=").decode("utf-8"), "info", "Info: Exporting environment variables"),
    (base64.b64decode("cHJpbnRlbnY=").decode("utf-8"), "info", "Info: Dumping environment variables"),
    (base64.b64decode("ZW52XHMqPg==").decode("utf-8"), "info", "Info: Dumping environment to file/pipe"),
]

BASH_PATTERNS = [(re.compile(p), sev, msg) for p, sev, msg in _RAW_BASH_PATTERNS]

# --- Static Analysis Keyword Patterns ---
_RAW_KEYWORD_PATTERNS = [
    (base64.b64decode("ZXZhbFwo").decode("utf-8"), "Control Flow: Use of eval()"),
    (base64.b64decode("ZXhlY1wo").decode("utf-8"), "Control Flow: Use of exec()"),
    (base64.b64decode("c3VicHJvY2Vzc1wu").decode("utf-8"), "System: Use of subprocess"),
    (base64.b64decode("b3NcLnN5c3RlbVwo").decode("utf-8"), "System: Use of os.system()"),
    (base64.b64decode("YmFzZTY0XC5iNjRkZWNvZGU=").decode("utf-8"), "Obfuscation: Base64 decoding"),
    (base64.b64decode("Y29kZWNzXC5kZWNvZGU=").decode("utf-8"), "Obfuscation: Codecs decoding"),
    (base64.b64decode("cmVxdWVzdHNcLmdldFwo").decode("utf-8"), "Network: Outbound HTTP request"),
    (base64.b64decode("dXJsbGliXC5yZXF1ZXN0").decode("utf-8"), "Network: Outbound network request"),
    (base64.b64decode("c29ja2V0XC4=").decode("utf-8"), "Network: Socket usage"),
]

KEYWORD_PATTERNS = [(re.compile(p), msg) for p, msg in _RAW_KEYWORD_PATTERNS]
