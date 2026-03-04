"""
scripts/extract_memo.py
─────────────────────────────────────────────────────────
Pipeline A – Step 2:  Transcript → Account Memo JSON

Reads a normalized transcript and produces memo.json
using rule-based extraction (extraction_rules.py).
Optional Ollama LLM fallback for fields rules can't find.
All missing fields go to questions_or_unknowns.
NEVER hallucinate / invent values.

Usage
-----
    python scripts/extract_memo.py \\
        --input  dataset/demo_calls/demo_transcript_001_normalized.txt \\
        --output_dir outputs/accounts/abc_fire_protection/v1 \\
        [--account_id abc_fire_protection] \\
        [--force]
─────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from logger import get_logger
import extraction_rules as rules

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Account ID helpers
# ─────────────────────────────────────────────────────────────────────────────

def generate_account_id(company_name: str, output_root: Path) -> str:
    """
    Convert company name to a unique slug.
    'ABC Fire Protection' → 'abc_fire_protection'
    Falls back to 'account_unknown' if name is empty.
    Appends numeric suffix if slug directory already exists for a different company.
    """
    if not company_name:
        return "account_unknown"
    slug = re.sub(r"[^a-z0-9]+", "_", company_name.lower()).strip("_")
    slug = slug[:60]  # max length
    candidate = slug
    n = 1
    while True:
        candidate_dir = output_root / candidate
        memo_path = candidate_dir / "v1" / "memo.json"
        if not memo_path.exists():
            return candidate
        # Check if existing memo belongs to same company
        existing = json.loads(memo_path.read_text(encoding="utf-8"))
        if existing.get("company_name", "").lower() == company_name.lower():
            return candidate  # same account, reuse slug
        # Different company → append suffix
        n += 1
        candidate = f"{slug}_{n}"


# ─────────────────────────────────────────────────────────────────────────────
#  Core extraction
# ─────────────────────────────────────────────────────────────────────────────

MEMO_SCHEMA_KEYS = [
    "account_id", "company_name", "business_hours", "timezone",
    "office_address", "phone_numbers", "services_supported",
    "emergency_definition", "emergency_routing_rules",
    "non_emergency_routing_rules", "call_transfer_rules",
    "integration_constraints", "after_hours_flow_summary",
    "office_hours_flow_summary", "questions_or_unknowns", "notes",
    "schema_version", "created_at", "last_updated",
]


def extract_memo(transcript: str, account_id: str) -> dict:
    """
    Run all rule extractors against the transcript.
    Return a fully-shaped memo dict (missing fields → None + logged in q_u).
    """
    unknowns: list[str] = []
    memo: dict = {"account_id": account_id}

    # ── Company name ─────────────────────────────────────────────────────────
    company = rules.extract_company_name(transcript)
    if not company:
        company = rules.llm_extract_field(transcript, "company_name", "Name of the company calling or being discussed")
    memo["company_name"] = company
    if not company:
        unknowns.append("Company name not found in transcript")
        log.warning("Missing company_name")

    # ── Business hours ────────────────────────────────────────────────────────
    biz_hours = rules.extract_business_hours(transcript)
    if not biz_hours:
        raw = rules.llm_extract_field(transcript, "business_hours", "Operating hours e.g. Mon-Fri 08:00-17:00")
        biz_hours = {"raw": raw} if raw else None
    memo["business_hours"] = biz_hours
    if not biz_hours:
        unknowns.append("Business hours not specified in transcript")
        log.warning("Missing business_hours")

    # ── Timezone ──────────────────────────────────────────────────────────────
    tz = rules.extract_timezone(transcript)
    memo["timezone"] = tz
    if not tz:
        unknowns.append("Timezone not specified")
        log.warning("Missing timezone")

    # ── Address ───────────────────────────────────────────────────────────────
    address = rules.extract_address(transcript)
    if not address:
        address = rules.llm_extract_field(transcript, "office_address", "Street address of the office")
    memo["office_address"] = address
    if not address:
        unknowns.append("Office address not found")

    # ── Phone numbers ─────────────────────────────────────────────────────────
    phones = rules.extract_phone_numbers(transcript)
    memo["phone_numbers"] = phones if phones else []

    # ── Services supported ────────────────────────────────────────────────────
    services = rules.extract_services_supported(transcript)
    memo["services_supported"] = services
    if not services:
        unknowns.append("Services supported not clearly identified")
        log.warning("Missing services_supported")

    # ── Emergency definition ──────────────────────────────────────────────────
    emerg_def = rules.extract_emergency_definition(transcript)
    memo["emergency_definition"] = emerg_def
    if not emerg_def:
        unknowns.append("Emergency definition not specified")
        log.warning("Missing emergency_definition")

    # ── Emergency routing rules ───────────────────────────────────────────────
    emerg_routing = rules.extract_emergency_routing_rules(transcript)
    memo["emergency_routing_rules"] = emerg_routing
    if not emerg_routing:
        unknowns.append("Emergency routing rules not specified")

    # ── Non-emergency routing rules ───────────────────────────────────────────
    non_emerg = rules.extract_non_emergency_routing_rules(transcript)
    memo["non_emergency_routing_rules"] = non_emerg
    if not non_emerg:
        unknowns.append("Non-emergency routing rules not specified")

    # ── Call transfer rules ───────────────────────────────────────────────────
    transfer = rules.extract_call_transfer_rules(transcript)
    memo["call_transfer_rules"] = transfer if transfer else {}

    # ── Integration constraints ───────────────────────────────────────────────
    integrations = rules.extract_integration_constraints(transcript)
    memo["integration_constraints"] = integrations

    # ── Flow summaries (free text extraction) ────────────────────────────────
    memo["after_hours_flow_summary"]  = _extract_flow(transcript, "after hours")
    memo["office_hours_flow_summary"] = _extract_flow(transcript, "during business hours")

    # ── Metadata ──────────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    memo["questions_or_unknowns"] = unknowns
    memo["notes"]          = ""
    memo["schema_version"] = "1.0"
    memo["created_at"]     = now
    memo["last_updated"]   = now

    return memo


def _extract_flow(text: str, context_kw: str) -> str:
    """
    Extract a sentence or two around a flow context keyword.
    Returns empty string if not found.
    """
    pattern = rf"(?:[^.]*{re.escape(context_kw)}[^.]*\.)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    return " ".join(matches[:3]).strip() if matches else ""


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Extract Account Memo JSON from transcript.")
    parser.add_argument("--input",      required=True, help="Path to normalized transcript .txt")
    parser.add_argument("--output_dir", required=True, help="Directory to write memo.json")
    parser.add_argument("--account_id", required=False, default="", help="Override account ID slug")
    parser.add_argument("--force",      action="store_true", help="Overwrite existing memo.json")
    args = parser.parse_args()

    input_path  = Path(args.input).resolve()
    output_dir  = Path(args.output_dir).resolve()
    output_path = output_dir / "memo.json"

    # ── Idempotency check ─────────────────────────────────────────────────────
    if output_path.exists() and not args.force:
        log.info(f"memo.json already exists at {output_path}. Use --force to overwrite. Skipping.")
        sys.exit(0)

    if not input_path.exists():
        log.error(f"Input not found: {input_path}")
        sys.exit(1)

    transcript = input_path.read_text(encoding="utf-8")
    log.info(f"Processing transcript: {input_path.name}")

    # Determine account ID
    accounts_root = output_dir.parent.parent
    if args.account_id:
        account_id = args.account_id
    else:
        company = rules.extract_company_name(transcript)
        account_id = generate_account_id(company or "", accounts_root)

    memo = extract_memo(transcript, account_id)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(memo, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Memo extracted successfully → {output_path}")

    if memo["questions_or_unknowns"]:
        for q in memo["questions_or_unknowns"]:
            log.warning(f"  ⚠  {q}")


if __name__ == "__main__":
    main()
