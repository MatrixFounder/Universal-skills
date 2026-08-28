---
name: post-writing
description: Use when the user asks to write, draft, or rewrite a post for social media (LinkedIn, Telegram, Blog) or wants content to be more engaging.
tier: 2
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

## Execution Mode

- **Mode**: `prompt-first`
- **Rationale**: This skill ships no `scripts/` directory and no runtime dependency. Its output is prose. Hook choice, voice match, and platform formatting are judgement calls made by reading `references/` and writing Markdown — there is nothing here for an executable to decide.

## Script Contract

This skill ships no executable. The contract it honours is the file it writes; the values below restate `## File Conventions` as a checkable interface.

- **Input**: the user's brief plus the Step 1 answers (goal, audience, key takeaway, platform, language).
- **Output**: exactly one Markdown file per requested post.
- **Naming**: `YYYY-MM-DD Post Title.md` — ISO date, space, human title.
- **Destination**: `Draft Posts/RU/` or `Draft Posts/EN/` under the project path listed in `## File Conventions`. A location named by the user overrides that default.
- **Format**: Markdown body matching the target platform — → arrows and no headings for LinkedIn, full Markdown for Telegram.
- **Promotion**: a draft moves to `Published Posts/` ONLY on an explicit user instruction.

## Safety Boundaries

- **Write scope**: Create or modify ONLY the post file the user asked for. The skill's own `assets/` and `references/` are read-only inputs — never edit, extend, or overwrite them during a drafting run.
- **No publishing**: This skill writes a file and stops. It never posts, schedules, or transmits content to LinkedIn, Telegram, a blog engine, or any API. Publication stays a human action.
- **No invented facts**: Statistics, quotes, customer names, company names, dates, and metrics come from the user. When a hook formula needs a number the user has not supplied, ASK for it. Never fill the slot with a plausible-looking figure.
- **No borrowed experience**: Never fabricate first-person stories, failures, launches, or results the user has not claimed. "Embed authority through details" means the user's details.
- **Confidentiality**: Personal and client information the user supplies stays inside the requested artifact — never copied into the skill's own references, never repeated into unrelated files.

## Validation Evidence

- **Primary**: Every item in `references/review-checklist.md` — the Core block and the Advanced block — passes before the draft reaches the user.
- **Secondary**: Length and formatting match the target platform's limits in `references/platform-rules.md` (LinkedIn 800-1,500 characters, → arrows, no headings; Telegram 500-2,000 characters, full Markdown).
- **Hook gate**: The selected hook clears the Step 2 hook checklist in `references/hooks-examples.md` — specific, honest, open loop, matched to the reader's awareness level.
- **Inspectable**: A caller confirms the pass by opening the saved `YYYY-MM-DD Post Title.md` in the drafts folder and reading it against those two checklists; worked end-to-end traces live in `examples/`.

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

1. Read `references/hooks-examples.md` for hook types and formulas.
2. Propose **3 distinct hook options** (e.g., one Story, one Problem, one Contrarian Thesis).
3. ASK the user to choose one.

Apply Ogilvy's principle: "The headline is 80 cents of your dollar." Spend time on the hook.

### Step 3: Draft the Post

1. Read the appropriate voice guide:
   - **RU posts**: Read `references/voice-guide-ru.md`
   - **EN posts**: Read `references/voice-guide-en.md`
   - **Other languages**: Use `references/voice-guide-en.md` as fallback. Note to the user that no brand-specific voice guide exists for this language.
2. Read `references/platform-rules.md` for platform-specific formatting.
3. Optionally read `assets/templates.md` if the user wants a specific format (listicle, structured, multi-platform).

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

1. Read `references/review-checklist.md`.
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

- [Hook Types & Examples](references/hooks-examples.md) — formulas and examples for 7 hook types
- [Voice Guide — RU](references/voice-guide-ru.md) — Russian voice, tone, lexicon, anti-patterns
- [Voice Guide — EN](references/voice-guide-en.md) — English voice, tone, anti-patterns
- [Platform Rules](references/platform-rules.md) — LinkedIn vs Telegram formatting
- [Post Templates](assets/templates.md) — post format templates
- [Review Checklist](references/review-checklist.md) — pre-publish verification

## Examples

- [Worked Example — EN, LinkedIn](examples/linkedin-en-contrarian-thesis.md) — full four-step trace ending in a Contrarian Thesis hook, with four checklist failures and the three revisions they forced
- [Worked Example — RU, Telegram](examples/telegram-ru-story-lead.md) — full four-step trace ending in a Story Lead hook, with the "Раньше/Сейчас" framework added at review
