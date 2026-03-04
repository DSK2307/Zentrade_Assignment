"""
scripts/apply_patch.py
─────────────────────────────────────────────────────────
Pipeline B – Step 2:  Onboarding transcript → v2 Memo JSON

Reads v1/memo.json + onboarding transcript, extracts updates,
deep-merges them onto v1 to produce v2/memo.json.
After patching, call generate_agent.py to produce v2/agent_spec.json.

Rules
-----
• Never remove existing fields unless explicitly overwritten
• Only update fields that have new information in onboarding transcript
• All uncertain/new items go to questions_or_unknowns
• v1 is NEVER modified — v2 is always a new file

Usage
-----
    python scripts/apply_patch.py \\
        --v1_memo  outputs/accounts/abc_fire_protection/v1/memo.json \\
        --onboarding dataset/onboarding_calls/onboarding_001.txt \\
        --output_dir outputs/accounts/abc_fire_protection/v2 \\
        [--force]
─────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from logger import get_logger
from normalize_transcript import normalize
import extraction_rules as rules

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Deep merge helper
# ─────────────────────────────────────────────────────────────────────────────

def deep_merge(base: dict, updates: dict) -> dict:
    """
    Recursively merge updates into base.
    - dicts: recurse
    - lists: union (no duplicates)
    - scalars: override if update is not None/empty
    """
    result = copy.deepcopy(base)
    for key, val in updates.items():
        if val is None or val == "" or val == [] or val == {}:
            continue  # skip empty updates
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = deep_merge(result[key], val)
        elif key in result and isinstance(result[key], list) and isinstance(val, list):
            # Union merge: add items not already present
            existing = [str(x).lower() for x in result[key]]
            for item in val:
                if str(item).lower() not in existing:
                    result[key].append(item)
                    existing.append(str(item).lower())
        else:
            result[key] = val
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Extract updates from onboarding transcript
# ─────────────────────────────────────────────────────────────────────────────

def extract_onboarding_updates(transcript: str) -> dict:
    """
    Extract only fields mentioned in the onboarding transcript.
    Returns a sparse dict — only keys with new data.
    """
    updates: dict = {}
    new_unknowns: list[str] = []

    company = rules.extract_company_name(transcript)
    if company:
        updates["company_name"] = company

    biz_hours = rules.extract_business_hours(transcript)
    if biz_hours:
        updates["business_hours"] = biz_hours

    tz = rules.extract_timezone(transcript)
    if tz:
        updates["timezone"] = tz

    address = rules.extract_address(transcript)
    if address:
        updates["office_address"] = address

    phones = rules.extract_phone_numbers(transcript)
    if phones:
        updates["phone_numbers"] = phones

    services = rules.extract_services_supported(transcript)
    if services:
        updates["services_supported"] = services

    emerg_def = rules.extract_emergency_definition(transcript)
    if emerg_def:
        updates["emergency_definition"] = emerg_def

    emerg_routing = rules.extract_emergency_routing_rules(transcript)
    if emerg_routing:
        updates["emergency_routing_rules"] = emerg_routing

    non_emerg = rules.extract_non_emergency_routing_rules(transcript)
    if non_emerg:
        updates["non_emergency_routing_rules"] = non_emerg

    transfer = rules.extract_call_transfer_rules(transcript)
    if transfer:
        updates["call_transfer_rules"] = transfer

    integrations = rules.extract_integration_constraints(transcript)
    if integrations:
        updates["integration_constraints"] = integrations

    # Detect any notes the onboarding agent mentioned
    import re
    note_m = re.search(
        r"(?:note|notes|important)\s*[:\-]\s*(.+?)(?:\.|$)",
        transcript, re.IGNORECASE
    )
    if note_m:
        updates["notes"] = note_m.group(1).strip()

    # LLM fallback for key missing fields
    for field, desc in [
        ("office_address", "Street address of the office"),
        ("company_name",   "Name of the company"),
    ]:
        if field not in updates:
            val = rules.llm_extract_field(transcript, field, desc)
            if val:
                updates[field] = val

    if new_unknowns:
        updates["_new_unknowns"] = new_unknowns

    return updates


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Apply onboarding patch to produce v2 memo.")
    parser.add_argument("--v1_memo",    required=True, help="Path to v1/memo.json")
    parser.add_argument("--onboarding", required=True, help="Path to onboarding transcript .txt")
    parser.add_argument("--output_dir", required=True, help="Directory to write v2/memo.json")
    parser.add_argument("--force",      action="store_true", help="Overwrite existing v2/memo.json")
    args = parser.parse_args()

    v1_path      = Path(args.v1_memo).resolve()
    onboard_path = Path(args.onboarding).resolve()
    output_dir   = Path(args.output_dir).resolve()
    output_path  = output_dir / "memo.json"

    # ── Idempotency ───────────────────────────────────────────────────────────
    if output_path.exists() and not args.force:
        log.info(f"v2/memo.json already exists at {output_path}. Use --force to overwrite. Skipping.")
        sys.exit(0)

    if not v1_path.exists():
        log.error(f"v1/memo.json not found: {v1_path}")
        sys.exit(1)
    if not onboard_path.exists():
        log.error(f"Onboarding transcript not found: {onboard_path}")
        sys.exit(1)

    # ── Load v1 ───────────────────────────────────────────────────────────────
    v1_memo = json.loads(v1_path.read_text(encoding="utf-8"))
    log.info(f"Loaded v1 memo for account: {v1_memo.get('account_id')}")

    # ── Normalize + extract updates ───────────────────────────────────────────
    raw_onboard = onboard_path.read_text(encoding="utf-8")
    normalized  = normalize(raw_onboard)
    log.info(f"Extracting updates from onboarding: {onboard_path.name}")
    updates = extract_onboarding_updates(normalized)

    if not updates:
        log.warning("No updates extracted from onboarding transcript. v2 will be identical to v1.")

    # ── Merge ─────────────────────────────────────────────────────────────────
    v2_memo = deep_merge(v1_memo, updates)

    # Pull new unknowns into existing list
    if "_new_unknowns" in updates:
        v2_memo["questions_or_unknowns"].extend(updates.pop("_new_unknowns"))
        v2_memo.pop("_new_unknowns", None)

    # Update metadata
    now = datetime.now(timezone.utc).isoformat()
    v2_memo["last_updated"]   = now
    v2_memo["schema_version"] = "2.0"

    # ── Write v2/memo.json ────────────────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(v2_memo, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"v2 memo saved → {output_path}")
    log.info(f"Fields updated: {list(updates.keys())}")


if __name__ == "__main__":
    main()
