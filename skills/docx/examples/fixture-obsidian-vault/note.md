---
type: meeting-summary
title: Fixture note
lang: en
participants:
  - Ada Lovelace
  - Alan Turing
tags:
  - fixture
  - obsidian
published: 2026-08-13
URL: https://example.invalid/source
sources:
  - _raw/should-not-appear.md
tldr: "This value is suppressed because it duplicates the body."
---

# Fixture note

> **Source:** a blockquote directly under the H1, so the frontmatter table lands after it.

## Embeds

![[diagram.png]]

![[diagram.png|120]]

![[photo.jpg|100x50]]

![[100% coverage.png]]

![[nested.png]]

![[missing-attachment.png]]

![[report.pdf]]

![[recording.mp3]]

![[linked note]]

## Links

[[linked note|A labelled link]]
[[folder/plain-target]]
[[linked note#Some Heading]]
[[linked note#^block-id]]
[[a|b|c]]

## Callouts

> [!warning] Watch out
> The body of the callout.

> [!note]
> A callout with no title takes the type's label.

> [!nonsense]- A folded callout of an unknown type
> Body.

## Minor syntax

Some ==highlighted text== here.

An inline %%comment%% is removed.

%%
A block comment is removed too.
%%

#fixture-tag #another/tag are stripped by default. Issue #42 is not a tag.

- [ ] an open task
- [x] a done task

## Inert regions

The following fenced block must survive byte-identical:

```markdown
![[not-an-embed.png]]
[[not-a-link]]
> [!warning] Not a callout
==not highlighted==
%%not a comment%%
#not-a-tag
```

And an inline span: `![[also-not-an-embed.png]]` stays as written.

## A thematic break

---

Text after the break, proving the frontmatter regex is anchored at offset 0.
