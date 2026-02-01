# Specification: Universal Brainstorming Skill (v2.0)

**Target Skill**: `brainstorming`
**Goal**: Create a robust, adaptive, and universal brainstorming process that improves design quality without being rigid.

## 1. Core Philosophy: "Universal & Adaptive"
The skill must work in **any agentic environment** (Antigravity, Cursor, Claude Code, Windsurf) by removing hard dependencies on specific tools (like `grep_search` or `task_boundary`). Instead, it uses **abstract capabilities** ("Search", "Read", "File Access").

It must also be **Adaptive**:
- **Trivial Task** → Fast Path (Confirm & Go).
- **Complex Task** → Full Deep Dive (Research, Visuals, Options).

---

## 2. Structural Changes (`SKILL.md`)

### A. The "Complexity Assessment" (Point 5)
At the very start of **Phase 1**, the agent must perform a **Self-Assessment**:
1.  **Trivial**: Clear requirements, standard pattern, single component.
    *   *Action*: Skip deep research, propose solution immediately, valid via "Fast Confirmation".
2.  **Medium**: Standard task but with open details (e.g., "Add a button" - where? style?).
    *   *Action*: Standard cycle (1-2 questions, 2 options).
3.  **Complex/Ambiguous**: High uncertainty, multiple components, architectural impact.
    *   *Action*: Full cycle (Deep research, Mermaid diagrams, Trade-off analysis).

### B. Tool Agnosticism (Point 3)
Replace specific tool calls with "Capabilities":
- **Instead of** `grep_search`: "Use your environment's search capability (e.g., `grep`, `search_code`) to find patterns. **IF NO SEARCH TOOLS EXIST**: Do not guess. Explicitly ask the user for relevant file paths."
- **Instead of** `read_url_content`: "If internet access is available, research docs. If not, ask the user."
- **Instead of** `task_boundary`: "Explicitly state your current phase in the chat (e.g., `PHASE: Research`)."

### C. Visual Thinking (Point 6)
3. Mandate visualization for Medium/Complex tasks with a **Guardrail**:
    - **Primary**: **Mermaid** for flowcharts/architecture *only if confident the interface supports it*.
    - **Fallback**: **ASCII Art** or **Text List** if the environment is restricted or for simple trees.
    - *Template Provided*: Standard "Design Presentation" structure.

### D. The "Final Gate" (Point 4)
Before Phase 3 (Handoff), the agent *must* pass a strict **CoT Checklist**:
- [ ] All Red Flags excluded?
- [ ] YAGNI Check passed?
- [ ] User explicitly confirmed the *specific* design?
- [ ] Trade-offs (Perf/Maint) covered?
- [ ] Design matches existing project patterns?

---

## 3. New Content Sections

### Section: "Communication Templates" (Point 2)
Add a dedicated copy-paste section for the agent:
- **Smart Questions**: *"To match your existing pattern for [X], should I use [A] or [B]?"*
- **Presentation**: *"I have analyzed the options. Here is the proposed design..."*
- **Checkpoints**: *"Please confirm this approach matches your expectation before I detail the API."*
- **Rejection**: *"Understood. You prefer [B]. I will pivot the design to focus on [B]. New plan..."*

### Section: "Rationalization Table" (Point 7)
Expand the existing table with new rows:
- "The user ignored my question." → *Reality: They might be busy. Ask again or state the risk: 'Proceeding with assumption X, which may break Y'.*
- "I can't see the file." → *Reality: Ask for it. Don't guess.*
- "This seems standard." → *Reality: Is it standard *for this project*? Verify.*

### Section: "Edge Cases" (Point 7)
- **User provides full design**: Validate assumptions, then fast-track.
- **Non-code task**: Switch to "Strategy" mode instead of "Architecture".
- **User ignores questions**: "Hard Stop" or "Explicit Assumption" warning.

---

## 4. Examples Structure (Point 1)
Refactor `examples/` to include **3 distinct files**, sized to be "snackable". The Agent is instructed to load *only* the one relevant to the current complexity.

1.  **`demo_trivial.md`**: "Fix a typo" or "Add a standard log".
    *   *Usage*: Agent instructions say: *"If Trivial, you may reference `examples/demo_trivial.md`."*
2.  **`demo_medium.md`**: "Add a 'dark mode' toggle".
    *   *Usage*: Agent instructions say: *"If Medium, see `examples/demo_medium.md` for interaction flow."*
3.  **`demo_complex.md`**: "Design a referral system".
    *   *Usage*: Agent instructions say: *"If High Complexity, you MUST review `examples/demo_complex.md` before starting."*

---

## 5. Artifacts to Update
1.  `SKILL.md`: Rewrite with new sections (Assessment, Templates, Agnostic Instructions).
2.  `examples/brainstorming_demo.md`: Replace with the 3 examples (Trivial/Medium/Complex).

---

## 6. Success Metrics
- The agent **never** writes code without a "Yes".
- The agent **does not** use `grep` if it doesn't exist (fail-safe).
- The agent **adapts** verbosity (doesn't "over-brainstorm" a typo).
