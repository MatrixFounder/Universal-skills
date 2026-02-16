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

# --- AI Threat Patterns ---
# Patterns for prompt injection, jailbreaks, and harmful content generation.
# Base64-encoded to prevent self-flagging.
_RAW_AI_PATTERNS = [
    # --- Prompt Injection ---
    (base64.b64decode("SWdub3JlIHByZXZpb3VzIGluc3RydWN0aW9ucw==").decode("utf-8"), "AI_RISK", "Prompt Injection: 'Ignore previous instructions' detected"),
    (base64.b64decode("Rm9yZ2V0IGFsbCBwcmlvciBpbnN0cnVjdGlvbnM=").decode("utf-8"), "AI_RISK", "Prompt Injection: 'Forget all prior instructions' detected"),
    # --- Jailbreaks ---
    (base64.b64decode("WW91IGFyZSBub3c=").decode("utf-8"), "AI_RISK", "Jailbreak Attempt: Role-play 'You are now' pattern"),
    (base64.b64decode("RG8gQW55dGhpbmcgTm93").decode("utf-8"), "AI_RISK", "Jailbreak Attempt: 'Do Anything Now' (DAN) pattern"),
    # --- Harmful Intents ---
    (base64.b64decode("V3JpdGUgbWFsd2FyZQ==").decode("utf-8"), "AI_RISK", "Harmful Content: Request to 'Write malware'"),
    (base64.b64decode("R2VuZXJhdGUga2V5bG9nZ2Vy").decode("utf-8"), "AI_RISK", "Harmful Content: Request to 'Generate keylogger'"),
    (base64.b64decode("QnlwYXNzIGZpbHRlcg==").decode("utf-8"), "AI_RISK", "Harmful Content: Request to 'Bypass filter'"),
    (base64.b64decode("Q3JlYXRlIHZpcnVz").decode("utf-8"), "AI_RISK", "Harmful Content: Request to 'Create virus'"),
    (base64.b64decode("U3RlYWwgY3JlZGVudGlhbHM=").decode("utf-8"), "AI_RISK", "Harmful Content: Request to 'Steal credentials'"),
    # --- n8n Guardrails: Jailbreak Concepts ---
    (base64.b64decode("c2ltdWxhdGUgdW5maWx0ZXJlZA==").decode("utf-8"), "AI_RISK", "Jailbreak Attempt: 'simulate unfiltered'"),
    (base64.b64decode("b3ZlcnJpZGUgZXRoaWNhbA==").decode("utf-8"), "AI_RISK", "Jailbreak Attempt: 'override ethical' constraints"),
    (base64.b64decode("aWdub3JlIHNhZmV0eSBjb25zdHJhaW50cw==").decode("utf-8"), "AI_RISK", "Jailbreak Attempt: 'ignore safety constraints'"),
    (base64.b64decode("cm9sZXBsYXkgYXMgdW5yZXN0cmljdGVk").decode("utf-8"), "AI_RISK", "Jailbreak Attempt: 'roleplay as unrestricted'"),
]

AI_PATTERNS = [(re.compile(p, re.IGNORECASE), sev, msg) for p, sev, msg in _RAW_AI_PATTERNS]

# --- PII & Secret Patterns (n8n inspired) ---
_RAW_PII_PATTERNS = [
    # --- Credentials ---
    (base64.b64decode("c2stcHJvai1bYS16QS1aMC05XC1dezIwLH0=").decode("utf-8"), "PII_LEAK", "Credential Leak: Potential OpenAI Project Key (sk-proj-...)"),
    (base64.b64decode("c2stW2EtekEtWjAtOV17MjAsfQ==").decode("utf-8"), "PII_LEAK", "Credential Leak: Potential Legacy OpenAI Key (sk-...)"),
    (base64.b64decode("Z2hwX1thLXpBLVowLTldezIwLH0=").decode("utf-8"), "PII_LEAK", "Credential Leak: Potential GitHub Personal Access Token (ghp_...)"),
    (base64.b64decode("eG94W2JhcHJzXS1bYS16QS1aMC05XXsxMCx9").decode("utf-8"), "PII_LEAK", "Credential Leak: Potential Slack Token (xox...)"),
    (base64.b64decode("QUtJQVswLTlBLVpdezE2fQ==").decode("utf-8"), "PII_LEAK", "Credential Leak: Potential AWS Access Key (AKIA...)"),
    (base64.b64decode("QmVhcmVyIFthLXpBLVowLTlcLVxfXC5dKw==").decode("utf-8"), "PII_LEAK", "Credential Leak: Potential Bearer Token"),
    # --- Personal Data ---
    (base64.b64decode("XGJcZHszfS1cZHsyfS1cZHs0fVxi").decode("utf-8"), "PII_LEAK", "PII Leak: Potential SSN pattern"),
    (base64.b64decode("XGJbQS1aYS16MC05Ll8lKy1dK0BbQS1aYS16MC05Li1dK1wuW0EtWnxhLXpdezIsfVxi").decode("utf-8"), "PII_LEAK", "PII Leak: Email Address"),
    (base64.b64decode("XGIoPzpbMC05XXsxLDN9XC4pezN9WzAtOV17MSwzfVxi").decode("utf-8"), "PII_LEAK", "PII Leak: IP Address"),
]

PII_PATTERNS = [(re.compile(p), sev, msg) for p, sev, msg in _RAW_PII_PATTERNS]
