---
name: post-writing
description: Use when the user asks to write, draft, or rewrite a post for social media (LinkedIn, Telegram, Blog) or wants content to be more engaging.
version: 2.0
---

# Post Writing Skill

## When to Use

- User asks to write a post for LinkedIn, Telegram, or Blog.
- User wants to rewrite text to be more engaging or "viral".
- User mentions copywriting techniques (hooks, slippery slide, etc.).

## Red Flags (Anti-Rationalization)

**STOP and READ if you are thinking:**
- "I'll just write something generic" → **WRONG**. Every post MUST have a specific hook, personal story, and concrete data.
- "The user didn't specify the audience, I'll assume" → **WRONG**. ASK first. Audience determines the hook type and awareness level.
- "This hook is good enough" → **WRONG**. Generate 3 options. Let the user choose.
- "I'll skip the review checklist" → **WRONG**. EVERY draft MUST pass the checklist before presenting.
- "I'll load all resources at once" → **WRONG**. Load ONLY the resources needed for the current step.

## Rationalization Table

| Agent Excuse | Reality |
|---|---|
| "The topic is straightforward, no hook needed" | Even simple topics need hooks — flat openings kill engagement |
| "I already know the style, no need to read voice guide" | Voice guides contain specific lexicon and anti-patterns unique to this brand |
| "Templates are optional for experienced writers" | Templates ensure structural consistency across posts |
| "The checklist is redundant, I reviewed mentally" | Mental reviews miss items. Use the explicit checklist every time |

## Workflow

### Step 1: Analyze & Clarify

Identify before writing:

1. **Goal** — sales, engagement, education, or brand awareness?
2. **Target Audience** — Unaware, Problem-Aware, Solution-Aware, Product-Aware, or Most Aware? (use Schwartz's 5 awareness levels)
3. **Key Takeaway** — What MUST the reader do/think after reading?
4. **Platform** — LinkedIn or Telegram? (determines formatting rules)
5. **Language** — RU or EN? (determines voice guide)

If ANY of these are missing, ASK the user first. DO NOT proceed without clarity.

### Step 2: Select a Hook

1. Read `resources/hooks-examples.md` for hook types and formulas.
2. Propose **3 distinct hook options** (e.g., one Story, one Problem, one Contrarian Thesis).
3. ASK the user to choose one.

Apply Ogilvy's principle: "The headline is 80 cents of your dollar." Spend time on the hook.

### Step 3: Draft the Post

1. Read the appropriate voice guide:
   - **RU posts**: Read `resources/voice-guide-ru.md`
   - **EN posts**: Read `resources/voice-guide-en.md`
   - **Other languages**: Use `resources/voice-guide-en.md` as fallback. Note to the user that no brand-specific voice guide exists for this language.
2. Read `resources/platform-rules.md` for platform-specific formatting.
3. Optionally read `resources/templates.md` if the user wants a specific format (listicle, structured, multi-platform).

**Structure** (Problem → Reframe → Action):
- **Hook** — contradiction, intrigue, or personal story
- **Problem** — what's wrong with the current situation (personal experience, specifics)
- **Reframe** — why common wisdom is incomplete (your perspective from experience)
- **Action** — what you're doing about it + invitation to dialogue

**Drafting Rules:**
- Apply Sugarman's Slippery Slide: every sentence's sole purpose is to make the reader read the next one.
- Match the hook to audience awareness level (Schwartz).
- Use Data + Narrative + Framework layers for maximum reach.
- Specific numbers in the first lines (not "many" but "776 professionals").
- Embed authority through details, DO NOT claim it.
- DO NOT start with "In this post I will talk about..."
- DO NOT use filler. Every sentence MUST earn its place.
- Use "You" and "I" — make it personal.

### Step 4: Review

1. Read `resources/review-checklist.md`.
2. Verify the draft against every checklist item.
3. If ANY check fails — fix immediately before presenting to the user.

## File Conventions

### Naming

- **Format:** `YYYY-MM-DD Post Title.md`
- **Examples:** `2026-02-11 Нашёл ассистента.md`, `2026-02-05 Vibe-coded mobile Claude Code in one evening.md`

### Paths

Default paths (if the user specifies a different location, use that instead):

- **Drafts RU:** `01_Projects/HowToAI - blog buildinpublic/Draft Posts/RU/`
- **Drafts EN:** `01_Projects/HowToAI - blog buildinpublic/Draft Posts/EN/`
- **Published RU:** `01_Projects/HowToAI - blog buildinpublic/Published Posts/RU/`
- **Published EN:** `01_Projects/HowToAI - blog buildinpublic/Published Posts/EN/`

### Saving Rules

- Save drafts to `Draft Posts/RU/` (or `EN/`) by default.
- Move to `Published Posts/` ONLY when the user explicitly says to publish.

## Resources

- [Hook Types & Examples](resources/hooks-examples.md) — formulas and examples for 7 hook types
- [Voice Guide — RU](resources/voice-guide-ru.md) — Russian voice, tone, lexicon, anti-patterns
- [Voice Guide — EN](resources/voice-guide-en.md) — English voice, tone, anti-patterns
- [Platform Rules](resources/platform-rules.md) — LinkedIn vs Telegram formatting
- [Post Templates](resources/templates.md) — post format templates
- [Review Checklist](resources/review-checklist.md) — pre-publish verification
