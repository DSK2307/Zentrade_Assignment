"""
scripts/normalize_transcript.py
─────────────────────────────────────────────────────────
Transcript normalization layer – Pipeline Step 1.

Responsibilities
----------------
• Remove filler words (um, uh, you know, like, so, basically, etc.)
• Strip noise lines ([pause], [inaudible], stage directions)
• Normalize whitespace
• Normalize time expressions  (8am → 08:00,  5 PM → 17:00)
• Standardize day expressions (Monday through Friday → Mon-Fri)
• Output clean, structured plain text for downstream extraction

Usage
-----
    python scripts/normalize_transcript.py \\
        --input  dataset/demo_calls/demo_transcript_001.txt \\
        --output dataset/demo_calls/demo_transcript_001_normalized.txt

    # Or pipe (writes to stdout if --output omitted):
    python scripts/normalize_transcript.py --input transcript.txt
─────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Allow running from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parent))
from logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Normalization constants
# ─────────────────────────────────────────────────────────────────────────────

_FILLER_WORDS = [
    r"\bum{1,3}\b", r"\buh{1,3}\b", r"\byou know\b", r"\blike\b",
    r"\bso\b", r"\bbasically\b", r"\bactually\b", r"\bI mean\b",
    r"\bright\?\b", r"\bkind of\b", r"\bsort of\b", r"\bjust\b",
    r"\bokay so\b", r"\bwell\b",
]

_NOISE_LINE_PATTERNS = [
    r"^\s*\[.*?\]\s*$",          # [pause], [inaudible], [crosstalk]
    r"^\s*\(.*?\)\s*$",          # (pause), (laughter)
    r"^\s*---+\s*$",             # horizontal rules
    r"^\s*={3,}\s*$",            # ===  dividers
    r"^\s*$",                    # blank lines
]

_TIME_SUBSTITUTIONS: list[tuple[str, str]] = [
    # "8am" / "8 am" / "08am" → "08:00" style will be handled by _normalize_time()
    (r"(\d{1,2})\s*([aA][mM])\b",   lambda m: _norm_time(m.group(1), "am")),
    (r"(\d{1,2})\s*([pP][mM])\b",   lambda m: _norm_time(m.group(1), "pm")),
]

_DAY_SUBSTITUTIONS: list[tuple[str, str]] = [
    (r"\bMonday\s+(?:through|to|thru|-)\s+Friday\b",   "Mon-Fri"),
    (r"\bMonday\s+(?:through|to|thru|-)\s+Thursday\b", "Mon-Thu"),
    (r"\bMonday\s+(?:through|to|thru|-)\s+Saturday\b", "Mon-Sat"),
    (r"\bMon(?:day)?\s*-\s*Fri(?:day)?\b",             "Mon-Fri"),
]


def _norm_time(hour_str: str, ampm: str) -> str:
    hour = int(hour_str)
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:00"


# ─────────────────────────────────────────────────────────────────────────────
#  Core normalization pipeline
# ─────────────────────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    """
    Run the full normalization pipeline on raw transcript text.
    Returns clean, structured plain text.
    """
    lines = text.splitlines()

    # 1. Remove noise lines
    cleaned_lines = []
    for line in lines:
        if any(re.match(pat, line) for pat in _NOISE_LINE_PATTERNS):
            continue
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # 2. Normalize day expressions (before filler removal to avoid clobbering)
    for pattern, replacement in _DAY_SUBSTITUTIONS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # 3. Normalize time expressions
    for pattern, repl_func in _TIME_SUBSTITUTIONS:
        text = re.sub(pattern, repl_func, text)  # type: ignore[arg-type]

    # 4. Remove filler words
    for filler_pat in _FILLER_WORDS:
        text = re.sub(filler_pat, "", text, flags=re.IGNORECASE)

    # 5. Normalize whitespace within lines
    normalized_lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]{2,}", " ", line).strip()
        if line:
            normalized_lines.append(line)

    # 6. Collapse more than two consecutive blank lines into one
    result_lines: list[str] = []
    blank_count = 0
    for line in normalized_lines:
        if line == "":
            blank_count += 1
            if blank_count <= 1:
                result_lines.append(line)
        else:
            blank_count = 0
            result_lines.append(line)

    return "\n".join(result_lines).strip()


# ─────────────────────────────────────────────────────────────────────────────
#  CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Normalize a raw call transcript."
    )
    parser.add_argument("--input",  required=True,  help="Path to raw transcript .txt")
    parser.add_argument("--output", required=False, help="Path to write normalized output (default: stdout)")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        log.error(f"Input file not found: {input_path}")
        sys.exit(1)

    log.info(f"Normalizing transcript: {input_path.name}")
    raw_text = input_path.read_text(encoding="utf-8")
    normalized = normalize(raw_text)

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(normalized, encoding="utf-8")
        log.info(f"Normalized transcript saved: {out_path}")
    else:
        print(normalized)


if __name__ == "__main__":
    main()
