# Text Genre & Style Taxonomy

This document defines the classification system for the Humanizer.

## 1. Structural Genres (The Base Layer)
First, determine the **Structural Goal** of the text. This determines the base ruleset (patterns to include).

| Genre | Goal | Base Ruleset |
| :--- | :--- | :--- |
| **Encyclopedic** | Strictly neutral, factual, cited. | `patterns_wiki.md` |
| **Objective** | Informative, balanced, professional. | `patterns_wiki.md` |
| **Opinionated** | Personal, subjective, "Soulful". | `patterns_creative.md` |
| **Persuasive** | Sales, converting, engaging. | `patterns_creative.md` |

## 2. Domain Styles (The Overlay)
Specific vocabulary and tone rules applied *on top* of the structure.

| Style | Description | Best Paired With |
| :--- | :--- | :--- |
| **Academic** | Scholarly, logical, formal. | *Encyclopedic* |
| **Corporate** | Professional, action-oriented. | *Objective* |
| **Technical** | Instructional, dry, precise. | *Objective* or *Encyclopedic* |
| **Journalistic** | Inverted pyramid, attributable. | *Objective* |
| **Marketing** | Benefit-driven, punchy. | *Persuasive* |
| **Crypto** | Insider slang, skeletal, fast. | *Opinionated* or *Objective* |
| **Science** | Measured, hypothesis-driven. | *Encyclopedic* or *Objective* |
| **Food** | Sensory, evocative. | *Opinionated* |

## 3. Editing Intensity (The Throttle)

Intensity controls HOW MANY patterns to fix, based on text type. Works with priority tags [A]-[D] on each pattern.

| Intensity | Fix Priorities | Best For | Notes |
| :--- | :--- | :--- | :--- |
| **max** | A + B + C + D | Marketing, social media, blog posts | Full rewrite. Every pattern addressed. |
| **high** | A + B + C | Expert content (articles, Substack, Medium) | Strong editing, preserves structure. |
| **medium** | A + B | Business correspondence, product docs | Removes obvious AI markers, keeps formality. |
| **low** | A only | Technical documentation, specifications | Only critical patterns. Preserves precision. |
| **minimal** | A only (cautiously) | Legal, regulatory, compliance text | Touch as little as possible. Never change meaning. |

**Auto-detection** (when `--intensity auto` or omitted):

| Genre | Default Intensity |
| :--- | :--- |
| marketing, social | max |
| blog, food, crypto | high |
| corporate, journalistic, encyclopedic, academic, science | medium |
| technical | low |

**Special rules:**
*   **Direct quotes** inside any text: intensity = zero. Never edit someone else's words.
*   **Short texts** (<100 words): Don't overload with fixes. 2-3 key markers is enough.
*   **Already good text**: Say so. Don't edit for the sake of editing.

## 4. Combinations (Examples)
*   **Whitepaper**: `Genre: Encyclopedic` + `Style: Crypto`
*   **Tech Blog**: `Genre: Opinionated` + `Style: Technical`
*   **Press Release**: `Genre: Objective` + `Style: Corporate`
*   **Review**: `Genre: Opinionated` + `Style: Food`
