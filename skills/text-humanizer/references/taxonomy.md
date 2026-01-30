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

## 3. Combinations (Examples)
*   **Whitepaper**: `Genre: Encyclopedic` + `Style: Crypto`
*   **Tech Blog**: `Genre: Opinionated` + `Style: Technical`
*   **Press Release**: `Genre: Objective` + `Style: Corporate`
*   **Review**: `Genre: Opinionated` + `Style: Food`
