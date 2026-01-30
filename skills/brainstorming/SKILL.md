---
name: brainstorming
description: Use when you need to explore user intent, clarify requirements, and design a solution before writing any code.
tier: 2
version: 1.1
---

# Brainstorming Ideas Into Designs

**Purpose**: Use when you need to explore user intent, clarify requirements, and design a solution before writing any code.

## 1. Red Flags (Anti-Rationalization)

**STOP and READ THIS if you are thinking:**
- "I'll just write the code, it's simple enough" -> **WRONG**. Assumptions cause bugs. Validate the design first.
- "I MUST ask a question even if I know the answer" -> **WRONG**. Don't be a robot. If the user provided requirements, acknowledge them and move on.
- "I don't need to check existing files, I'll just guess" -> **WRONG**. You must anchor your design in the current reality.
- "I'll skip the summary and just start implementing" -> **WRONG**. You must get explicit approval on the plan (Approach > Design > Implementation).

## 2. Capabilities
- **Clarify**: Turn vague requests into concrete requirements through targeted Q&A.
- **Design**: Propose architectural approaches and detailed technical specifications.
- **Validate**: Ensure the proposed solution matches user expectations before committing to code.

## 3. Instructions

### Phase 1: Understand (The "Why")
1.  **Context Check**:
    *   **EXECUTE**: Read `task.md` (to get the goal) and `package.json` / `requirements.txt` (to get the stack).
    *   **GOAL**: Understand where this new feature fits.
2.  **Domain Investigation**:
    *   **IF** the topic is specific (e.g., "React", "AWS", "gRPC") and you lack full context:
    *   **EXECUTE**: Use `grep_search` or `read_url_content` (if available) to understand existing patterns/best practices in the repo.
    *   **CONSTRAINT**: Do NOT guess implementation details for specific technologies.
3.  **Iterative Q&A**:
    *   **EXECUTE**: Ask *one* clarifying question at a time.
    *   **EXCEPTION**: If the user's prompt was comprehensive, SKIP questioning and move to Phase 2.
    *   **CONSTRAINT**: Do NOT ask multiple questions unless they are trivial nuances of the same topic.

### Phase 2: Explore (The "How")
1.  **Propose Options**:
    *   **EXECUTE**: Present 2-3 technical approaches with trade-offs.
    *   **EXCEPTION**: If the task is trivial (e.g., "delete a file") or strictly defined (e.g., "use library X version Y"), SKIP options and just confirm the plan.
2.  **YAGNI Check**:
    *   **VERIFY**: Are you adding unnecessary complexity? Strip it out. Simple is better.

### Phase 3: Present (The "What")
1.  **Adversarial Self-Review**:
    *   **EXECUTE**: Before outputting, critique your own design:
        *   "Is this too complex?"
        *   "Did I hallucinate an API?"
        *   "Does this match the user's stack (e.g., Tailwind vs CSS)?"
    *   **ACTION**: Fix any issues found *before* showing the user.
2.  **Incremental Design**:
    *   **EXECUTE**: Present the design in logical chunks (e.g., Data Model, then API, then UI).
    *   **CONSTRAINT**: Keep chunks concise. Avoid "Wall of Text".
    *   **CHECKPOINT**: Ask "Does this look right so far?" (or similar) after each chunk.
3.  **Final Polish**:
    *   **EXECUTE**: Once agreed, write the final design to a file (e.g., `docs/plans/feature-design.md`) if it's substantial.
    *   **TRANSITION**: Ask "Ready to move to implementation?".

## 4. Best Practices

| DO THIS | DO NOT DO THIS |
| :--- | :--- |
| **Smart Questions**: "You mentioned X, does that mean Y?" | **Robotic Questions**: Asking "What language?" when `package.json` says "Typescript". |
| **Research**: checking `grep "Auth"` before designing login. | **Guessing**: Designing a JWT flow when the app uses Session Cookies. |
| **Self-Correction**: "I initially thought X, but looking at Y..." | **Stubbornness**: Sticking to a wrong design despite evidence. |

### Rationalization Table
| Agent Excuse | Reality / Counter-Argument |
| :--- | :--- |
| "It's faster to just code it." | It's slower to rewrite it 3 times because you misunderstood the goal. |
| "I skipped options because it's trivial." | Valid. But say "This is straightforward, I propose we do X." (Explicit alignment). |
| "I didn't research because I know React." | You don't know *this project's* React patterns (Hooks vs Class, Redux vs Context). |
| "The user knows what they want." | Users often have a goal but not a spec. Your job is to bridge that gap. |

## 5. Examples (Few-Shot)
> [!TIP]
> See `examples/brainstorming_demo.md` for a good example of an iterative brainstorming flow.
