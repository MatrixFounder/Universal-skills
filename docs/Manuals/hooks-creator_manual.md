# hooks-creator Skill Manual

The **hooks-creator** skill helps you generate robust, secure, and compliant hooks for the Gemini CLI agentic loop. It automates the boilerplate of creating Bash or Node.js scripts and configuring `settings.json`, while strictly enforcing security best practices.

## 🚀 Getting Started

### Prerequisites
*   **Gemini CLI**: Installed and running.
*   **Dependencies**:
    *   `jq` (Required for Bash hooks): `brew install jq` or `apt-get install jq`.
    *   `node` (Required for Node.js hooks).

### Installation
Ensure the skill is located at:
`.agent/skills/hooks-creator`

## 💡 How to Use

The skill is triggered when you ask to "create a hook", "block a tool", "log output", or "inject context".

### 1. Clear Instructions (Fast Path)
If you know exactly what you want, be specific to get immediate results:
> "Create a hook that blocks any `write_file` operation containing 'SECRET_KEY' using Bash."

### 2. Ambiguous Exploration
If you are unsure, describe your goal, and the agent will ask **one** clarifying question:
> **User**: "Make my agent safer."
> **Agent**: "Do you want to block specific tools (like `rm`) or scan content for secrets?"

## 🛠 Capabilities

| Feature | Description | Support |
| :--- | :--- | :--- |
| **Security Gates** | Block tools based on content patterns (Regex/Jq). | Bash, Node |
| **Tool Filtering** | Allow/Deny tools dynamically based on user intent. | Node.js |
| **Context Injection** | Add Git history, file summaries, or DB context before planning. | Bash, Node |
| **Auditing** | Log all prompts, responses, and tool outputs to a file. | Bash, Node |

## ⚠️ Security & Best Practices

The skill enforces "Golden Rules" to keep your system safe. **Do not bypass these:**

1.  **Strict JSON Output**: Hooks MUST NOT print plain text to `stdout`. Use `stderr` for logs.
2.  **Input Sanitization**: Bash hooks use `jq` to parse input. `grep` on raw input is forbidden to prevent injection attacks.
3.  **Dependency Checks**: Generated scripts include checks for `jq` or `node` and fail gracefully (Exit Code 2) if missing.

## 📂 Generated Structure

The skill generates:
1.  **Script File**: e.g., `.gemini/hooks/my_check.sh`.
2.  **Configuration**: A snippet for `.gemini/settings.json`.

### Example Workflow 1: Security Block
1.  **User**: "Prevent the agent from writing to `.env` files."
2.  **Agent**: Generates `.gemini/hooks/block_env.sh` and configuration.
3.  **User**:
    *   Run `chmod +x .gemini/hooks/block_env.sh`.
    *   Add snippet to `settings.json`.
    *   (Optional) Test: `cat test.json | ./block_env.sh`.

### Example Workflow 2: Context Injection
1.  **User**: "Inject the current git status before every agent turn."
2.  **Agent**: Generates `.gemini/hooks/git_context.sh` hooked to `BeforeAgent`.
3.  **Result**: The agent sees `git status` output in the context window automatically.

### Example Workflow 3: Audit Logging
1.  **User**: "Log all tool executions to `audit.log`."
2.  **Agent**: Generates `.gemini/hooks/audit.sh` hooked to `AfterTool`.
3.  **Result**: Every tool call is appended to a log file for review.

## 📚 Official Documentation
For deep dives into the hook system, visit the [Gemini CLI Hooks Documentation](https://geminicli.com/docs/hooks/).

## ❓ Troubleshooting

*   **Hook fails silently?** Check if `jq` is installed. Check `stderr` output in logs.
*   **CLI ignores hook?** Verify `settings.json` matcher. Restart CLI (some changes need reload).
*   **"Invalid JSON" error?** Ensure your script isn't `echo`ing debug info to `stdout`.
