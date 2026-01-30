#!/usr/bin/env python3
import argparse
import os
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
    "corporate": "patterns_creative.md",  # Often subjective/promotional, can use 'creative' base for 'I/We'
    "food": "patterns_creative.md",
    "crypto": "patterns_creative.md"
}

def load_file(path):
    """Safely load a file content."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        # Fallback: if a user requests a style that doesn't exist but is a valid genre
        return ""

def get_available_styles():
    """List available style files."""
    return [f.stem for f in STYLES_DIR.glob("*.md")]

def main():
    parser = argparse.ArgumentParser(description="Deterministic System Prompt Assembler for Text Humanizer")
    parser.add_argument("--genre", required=True, choices=GENRE_MAP.keys(), help="Target genre")
    parser.add_argument("--style", help=f"Target style/domain (e.g., crypto). Available: {get_available_styles()}")
    parser.add_argument("--task", default="Rewriting content", help="Description of the task")
    parser.add_argument("--mode", choices=["prompt-gen", "humanize"], default="humanize", help="Output mode")
    parser.add_argument("--extra-rules", help="Additional custom constraints provided by the user", default="")
    
    args = parser.parse_args()

    # 1. Load Components
    universal_patterns = load_file(REFERENCES_DIR / "patterns_universal.md")
    
    # Genre logic
    genre_file = GENRE_MAP[args.genre]
    genre_patterns = load_file(REFERENCES_DIR / genre_file)
    
    # Style logic
    # Auto-detection: If style is not provided, check if the genre NAME corresponds to a style file
    target_style = args.style if args.style else args.genre
    
    style_content = ""
    style_path = STYLES_DIR / f"{target_style}.md"
    
    if style_path.exists():
        style_content = load_file(style_path)
    elif args.style: # Only error if they EXPLICITLY asked for a style that doesn't exist
        print(f"Warning: Style '{args.style}' not found. Available: {get_available_styles()}")
        # We don't exit, we just generate without the specific style overlay
    
    # 2. Load Template
    template = load_file(ASSETS_DIR / "generator_template.md")

    # 3. Assemble
    # We construct the final content by filling the template
    final_output = template.replace("{{genre}}", args.genre.title())
    final_output = final_output.replace("{{task_description}}", args.task)
    
    # Inject Universal Patterns
    final_output = final_output.replace("{{patterns_universal}}", universal_patterns)
    
    # Inject Genre Patterns
    final_output = final_output.replace("{{patterns_genre}}", genre_patterns)
    
    # Inject Style (or empty string if none)
    final_output = final_output.replace("{{style_section}}", style_content if style_content else "No specific domain style applied.")

    # Inject Extra Rules
    final_output = final_output.replace("{{extra_rules}}", args.extra_rules if args.extra_rules else "No custom constraints.")


    # 4. Output
    print(final_output)

if __name__ == "__main__":
    main()
