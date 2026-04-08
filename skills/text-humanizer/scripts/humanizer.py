#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path

# Constants for Paths
SKILL_ROOT = Path(__file__).parent.parent
REFERENCES_DIR = SKILL_ROOT / "references"
STYLES_DIR = REFERENCES_DIR / "styles"
ASSETS_DIR = SKILL_ROOT / "assets"

GENRE_MAP = {
    # Objective / Neutral Modes (Use Wiki Patterns)
    "encyclopedic": "patterns_wiki.md",
    "academic": "patterns_wiki.md",
    "technical": "patterns_wiki.md",
    "journalistic": "patterns_wiki.md",
    "science": "patterns_wiki.md",

    # Subjective / Creative Modes (Use Creative Patterns)
    "blog": "patterns_creative.md",
    "social": "patterns_creative.md",
    "marketing": "patterns_creative.md",
    "corporate": "patterns_creative.md",
    "food": "patterns_creative.md",
    "crypto": "patterns_creative.md"
}

# Genre -> base role category
ROLE_MAP = {
    "encyclopedic": "encyclopedic",
    "academic": "encyclopedic",
    "technical": "encyclopedic",
    "journalistic": "encyclopedic",
    "science": "encyclopedic",
    "blog": "creative",
    "social": "creative",
    "marketing": "creative",
    "corporate": "creative",
    "food": "creative",
    "crypto": "crypto",
}

# Default intensity per genre
INTENSITY_DEFAULTS = {
    "marketing": "max",
    "social": "max",
    "blog": "high",
    "food": "high",
    "crypto": "high",
    "corporate": "medium",
    "journalistic": "medium",
    "encyclopedic": "medium",
    "academic": "medium",
    "technical": "low",
    "science": "medium",
}

# Which priority tags to include at each intensity level
INTENSITY_PRIORITIES = {
    "max":     {"A", "B", "C", "D"},
    "high":    {"A", "B", "C"},
    "medium":  {"A", "B"},
    "low":     {"A"},
    "minimal": {"A"},
}


def load_file(path):
    """Safely load a file content."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def filter_patterns_by_priority(text, allowed_priorities):
    """Filter pattern sections by priority tags.

    Each pattern section starts with '## ' and contains a `[X]` priority tag.
    Keeps only sections whose tag is in allowed_priorities.
    Also preserves any content before the first '## ' (header, legend, etc.).
    """
    # Split into sections by ## headers
    parts = re.split(r'(?=^## )', text, flags=re.MULTILINE)

    filtered = []
    for part in parts:
        # Content before the first ## (header/legend) -- always keep
        if not part.startswith("## "):
            filtered.append(part)
            continue

        # Extract priority tag like `[A]`, `[B]`, `[C]`, `[D]`
        tag_match = re.search(r'`\[([A-D])\]`', part)
        if tag_match:
            tag = tag_match.group(1)
            if tag in allowed_priorities:
                filtered.append(part)
        else:
            # No tag found -- include by default (safety)
            filtered.append(part)

    return "".join(filtered)


def get_available_styles():
    """List available style files."""
    return [f.stem for f in STYLES_DIR.glob("*.md")]


def main():
    parser = argparse.ArgumentParser(description="Deterministic System Prompt Assembler for Text Humanizer")
    parser.add_argument("--genre", required=True, choices=GENRE_MAP.keys(), help="Target genre")
    parser.add_argument("--style", help=f"Target style/domain (e.g., crypto). Available: {get_available_styles()}")
    parser.add_argument("--task", default="Rewriting content", help="Description of the task")
    parser.add_argument("--mode", choices=["prompt-gen", "humanize", "audit"], default="humanize",
                        help="Output mode: humanize (rewrite), prompt-gen (generate reusable prompt), audit (diagnose only)")
    parser.add_argument("--intensity", choices=["auto", "max", "high", "medium", "low", "minimal"], default="auto",
                        help="Editing intensity. 'auto' selects based on genre.")
    parser.add_argument("--voice", help="Path to a voice passport file (writing samples analysis)", default="")
    parser.add_argument("--extra-rules", help="Additional custom constraints provided by the user", default="")

    args = parser.parse_args()

    # Resolve intensity
    if args.intensity == "auto":
        resolved_intensity = INTENSITY_DEFAULTS.get(args.genre, "medium")
    else:
        resolved_intensity = args.intensity

    allowed_priorities = INTENSITY_PRIORITIES[resolved_intensity]

    # 1. Load Components
    universal_patterns = load_file(REFERENCES_DIR / "patterns_universal.md")
    rewriting_strategy = load_file(REFERENCES_DIR / "rewriting_strategy.md")

    # Filter patterns by intensity
    universal_patterns = filter_patterns_by_priority(universal_patterns, allowed_priorities)

    # Genre logic
    genre_file = GENRE_MAP[args.genre]
    genre_patterns = load_file(REFERENCES_DIR / genre_file)
    genre_patterns = filter_patterns_by_priority(genre_patterns, allowed_priorities)

    # Style logic
    target_style = args.style if args.style else args.genre

    style_content = ""
    style_path = STYLES_DIR / f"{target_style}.md"

    if style_path.exists():
        style_content = load_file(style_path)
    elif args.style:
        print(f"Warning: Style '{args.style}' not found. Available: {get_available_styles()}", file=sys.stderr)

    # Voice passport logic
    voice_content = ""
    if args.voice:
        voice_path = Path(args.voice)
        if voice_path.exists():
            voice_content = load_file(voice_path)
        else:
            print(f"Warning: Voice file '{args.voice}' not found.", file=sys.stderr)

    # Resolve role
    role_category = ROLE_MAP.get(args.genre, "creative")

    # 2. Load Template
    template = load_file(ASSETS_DIR / "generator_template.md")

    # 3. Assemble
    final_output = template.replace("{{genre}}", args.genre.title())
    final_output = final_output.replace("{{task_description}}", args.task)
    final_output = final_output.replace("{{intensity}}", resolved_intensity)
    final_output = final_output.replace("{{mode}}", args.mode)
    final_output = final_output.replace("{{role_category}}", role_category)

    # Inject Universal Patterns (already filtered by intensity)
    final_output = final_output.replace("{{patterns_universal}}", universal_patterns)

    # Inject Rewriting Strategy
    final_output = final_output.replace("{{rewriting_strategy}}", rewriting_strategy if rewriting_strategy else "No rewriting strategy loaded.")

    # Inject Genre Patterns (already filtered by intensity)
    final_output = final_output.replace("{{patterns_genre}}", genre_patterns)

    # Inject Style
    final_output = final_output.replace("{{style_section}}", style_content if style_content else "No specific domain style applied.")

    # Inject Voice Passport
    final_output = final_output.replace("{{voice_section}}", voice_content if voice_content else "No voice passport provided. Write as a smart person explaining to a friend over coffee.")

    # Inject Extra Rules
    final_output = final_output.replace("{{extra_rules}}", args.extra_rules if args.extra_rules else "No custom constraints.")

    # 4. Strip mode-conditional sections
    if args.mode == "prompt-gen":
        # Remove Diagnosis and Verification sections (only for humanize/audit)
        final_output = re.sub(
            r'### 2\. Diagnosis \(Humanize and Audit modes only\).*?(?=### 3\.)',
            '', final_output, flags=re.DOTALL)
        final_output = re.sub(
            r'### 9\. Verification \(Humanize mode only\).*?(?=---|\Z)',
            '', final_output, flags=re.DOTALL)
    elif args.mode == "audit":
        # Remove Verification (audit doesn't rewrite, so no verification needed)
        final_output = re.sub(
            r'### 9\. Verification \(Humanize mode only\).*?(?=---|\Z)',
            '', final_output, flags=re.DOTALL)

    # 5. Output
    print(final_output)


if __name__ == "__main__":
    main()
