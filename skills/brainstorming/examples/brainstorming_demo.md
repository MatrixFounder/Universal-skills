# Brainstorming Demo

This example shows how to properly conduct a brainstorming session, demonstrating the "One Question at a Time" rule and "Incremental Validation".

## Scenario
User wants to build a "Daily Standup Bot" for Slack.

## Interaction

**SYSTEM:** (Internal Monologue) User wants a bot. I need to understand context first. Checking files... no existing bot code. OK, I'll start by clarifying the goal.
**AGENT:** I'd love to help design the Daily Standup Bot. To make sure we build exactly what you need, I have a few questions.

First, **who is the primary audience for this bot?**
A) A small team (<10 people) in a single channel
B) A large organization with multiple teams/channels
C) A completely public bot for any workspace

**USER:** Mostly A, just for our engineering team of 5 people.

**SYSTEM:** (Internal Monologue) OK, small scale. Now I need to know about the reporting format.
**AGENT:** Got it, keeping it simple for a small team.

Next, **how should the standup be triggered?**
A) Scheduled time (e.g., 9 AM every day)
B) User command (e.g., `/standup`)
C) Async prompt (bot DMs users)

**USER:** C. The bot should DM them.

**SYSTEM:** (Internal Monologue) Async DMs. Good. Now about the questions they answer.
**AGENT:** Async DMs work great for flexibility.

**What specific questions should the bot ask each person?**
1. Standard 3 (Yesterday, Today, Blockers)
2. Custom configurable questions
3. Standard 3 + "Mood/Vibe" check

**USER:** Standard 3 is fine for now.

(...)

**AGENT:** (After gathering requirements) Thanks! I have a clear picture now. I'd like to propose a simple design.

### Approach: "Stateful DM Handler"
We'll use a simple state machine to track if a user has answered.

**Key Components:**
\- **Scheduler:** Cron job triggers DMs at 9 AM.
\- **DM Handler:** Bot sends questions one by one. Stores answers in memory (or light DB) until finished.
\- **Reporter:** Once all answers are in (or at cutoff time), posts a summary to the #standup channel.

**Does this high-level approach sound right to you?**

**USER:** Yes, perfect.

**AGENT:** Great. Now let's detail the Data Model...
(Proceeds to detail the next section)
