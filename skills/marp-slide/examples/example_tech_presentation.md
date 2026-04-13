# Example: Tech Meetup Presentation

## User Request
"Create a presentation about Python async/await for a tech meetup, 5 slides"

## Agent Reasoning
1. **Theme inference**: Technical/developer content → **tech theme**
2. **Read references**: `references/marp-syntax.md`, `references/best-practices.md`
3. **Load template**: `assets/template-tech.md` (GitHub-style dark, Fira Code font)
4. **Structure**: Title + 4 content slides, 3-5 bullets each

## Output (abbreviated)

```markdown
---
marp: true
theme: default
paginate: true
---

<style>
/* Full CSS from assets/template-tech.md is embedded here.
   Representative excerpt: */
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;700&family=Noto+Sans+JP:wght@400;700&display=swap');
section {
  background-color: #0d1117;
  color: #c9d1d9;
  font-family: 'Fira Code', 'Noto Sans JP', monospace;
  font-size: 22px;
}
h1, h2 { color: #58a6ff; }
/* ... remaining theme CSS ... */
</style>

<!-- _class: lead -->

# Python Async/Await
## Modern Concurrency Patterns

Tech Meetup | 2024

---

## Why Async?

- I/O-bound tasks block the event loop
- Threads add complexity and overhead
- `asyncio` enables cooperative multitasking
- 10x throughput on network-heavy workloads

---

## Core Syntax

![bg right:40%](code-example.png)

- `async def` declares a coroutine
- `await` yields control to the event loop
- `asyncio.gather()` runs tasks concurrently
- `async with` for resource management

---

## Common Patterns

- **Fan-out**: `asyncio.gather(*tasks)`
- **Queues**: `asyncio.Queue` for producer/consumer
- **Timeouts**: `asyncio.wait_for(coro, timeout=5)`
- **Semaphores**: limit concurrent connections

---

<!-- _class: lead -->

# Thank You
Questions?
```

## Key Decisions
- Used `<!-- _class: lead -->` for title and closing slides
- Kept bullets to 3-5 per slide
- Used `![bg right:40%]` for side image (Marp syntax, not standard Markdown)
- Embedded CSS from template (not written from scratch)
