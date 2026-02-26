# Meeting Type Detection Rules

## Purpose

This file defines rules for automatically detecting the meeting type
from transcription text. The agent MUST use these rules when the user
has not explicitly specified a type via `--type`.

## Algorithm

1. Scan the first 20% of the transcription for signal words
2. Count matches per meeting type
3. The type with the most signal matches wins
4. On a tie or low confidence → use `default`

## Signals by Type

### standup

**Threshold**: ≥ 3 matches OR duration < 20 minutes + ≥ 1 match

Signal words (case-insensitive, multilingual):
- "yesterday" / "вчера"
- "today" / "сегодня"
- "blocker" / "blocked" / "блокер"
- "what I did" / "что сделал"
- "plans for" / "планы на"
- "standup" / "stand-up" / "daily" / "стендап"
- Short utterances (< 3 sentences) from many participants in sequence

### retrospective

**Threshold**: ≥ 2 matches

Signal words (case-insensitive, multilingual):
- "retro" / "retrospective" / "ретро"
- "what went well" / "что прошло хорошо"
- "what to improve" / "что улучшить"
- "what went wrong" / "что пошло не так"
- "keep" / "stop" / "start" (in process context)
- "sprint" / "спринт" (in summary context)
- "lessons learned" / "уроки"

### discovery

**Threshold**: ≥ 3 matches

Signal words (case-insensitive, multilingual):
- "brainstorm" / "брейншторм" / "мозговой штурм"
- "idea" / "идея"
- "option" / "alternative" / "вариант"
- "how should we" / "как лучше"
- "what if" / "а что если"
- "I suggest" / "предлагаю"
- "trade-off" / "tradeoff" / "компромисс"
- "research" / "discovery" / "исследование"

### default

Used when:
- No type reached its threshold signal count
- Signals are evenly distributed across types
- The agent is not confident in classification

## Override

If the user explicitly provides `--type <type>`, this parameter
has ABSOLUTE priority. Auto-detection is NOT applied.
