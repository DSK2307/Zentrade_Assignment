"""
scripts/generate_agent.py
─────────────────────────────────────────────────────────
Pipeline A/B – Step 3:  Account Memo JSON → Retell Agent Spec JSON

Reads memo.json and generates a complete Retell-compatible
agent_spec.json with a structured system_prompt covering:
  • Business-hours flow
  • After-hours flow

Prompt rules:
  - Business hours:  greeting → purpose → caller info → route/transfer
                     → handle failure → confirm → anything else → close
  - After hours:     greeting → purpose → emergency confirm
                     → emergency: collect info + attempt transfer + fallback
                     → non-emergency: collect request + confirm follow-up
                     → anything else → close

Never hallucinate — missing fields left as {unknown}.

Usage
-----
    python scripts/generate_agent.py \\
        --memo outputs/accounts/abc_fire_protection/v1/memo.json \\
        --output_dir outputs/accounts/abc_fire_protection/v1 \\
        [--force]
─────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Prompt template builders
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(value, fallback: str = "{unknown}") -> str:
    """Return a clean string from a memo value or a {unknown} placeholder."""
    if not value:
        return fallback
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else fallback
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            parts.append(f"{k}: {v}")
        return "; ".join(parts) if parts else fallback
    return str(value).strip() or fallback


def build_business_hours_prompt(memo: dict) -> str:
    company   = _fmt(memo.get("company_name"))
    biz_hours = _fmt(memo.get("business_hours"))
    services  = _fmt(memo.get("services_supported"))
    transfer  = _fmt(memo.get("call_transfer_rules", {}).get("primary"))
    fallback  = _fmt(memo.get("call_transfer_rules", {}).get("fallback"), "take a message and assure callback")

    return f"""## Business Hours Call Flow

You are a professional AI voice agent for **{company}**.
Business hours: {biz_hours}
Services provided: {services}

### Step-by-step Call Script (Business Hours)

1. **Greeting**
   "Thank you for calling {company}. How can I assist you today?"

2. **Determine Purpose**
   Listen carefully to why the caller is reaching out.
   Categorize: service request, emergency, billing, general inquiry.

3. **Collect Caller Information**
   "May I have your name, please?"
   "And the best phone number to reach you?"
   If service address needed: "What is the service location address?"

4. **Route or Transfer**
   Based on request type, transfer to: {transfer}.
   Announce transfer: "I'll connect you now — please hold."

5. **Handle Transfer Failure**
   If transfer fails: {fallback}.
   "I wasn't able to connect you right now. I've noted your details and
    someone will call you back promptly."

6. **Confirm Next Steps**
   "To confirm, [restate what was requested or promised]."

7. **Ask if Anything Else**
   "Is there anything else I can help you with today?"

8. **Close Call**
   "Thank you for calling {company}. Have a great day!"
"""


def build_after_hours_prompt(memo: dict) -> str:
    company     = _fmt(memo.get("company_name"))
    emerg_def   = _fmt(memo.get("emergency_definition"))
    emerg_route = _fmt(memo.get("emergency_routing_rules"))
    fallback    = _fmt(
        memo.get("call_transfer_rules", {}).get("fallback"),
        "assure the caller that a technician will follow up immediately"
    )
    biz_hours   = _fmt(memo.get("business_hours"))

    return f"""## After-Hours Call Flow

You are a professional AI voice agent for **{company}** handling after-hours calls.
Business hours: {biz_hours}

### Emergency Definitions
The following situations are classified as emergencies:
{emerg_def}

### Step-by-step Call Script (After Hours)

1. **Greeting**
   "Thank you for calling {company}. You've reached us outside of business hours.
    I'm here to assist you."

2. **Determine Purpose**
   "Can you briefly describe the reason for your call?"

3. **Assess Emergency**
   "Is this an emergency situation?"
   Emergency indicators: {emerg_def}.

4. **If EMERGENCY — Collect Critical Info Immediately**
   "I understand this is urgent. I need a few quick details:
    - Your full name?
    - Best phone number?
    - Address of the emergency location?"
   Do NOT delay collection with unnecessary questions.

5. **Attempt Emergency Transfer**
   Transfer to: {emerg_route}.
   "I'm connecting you to our emergency line right now."

6. **If Emergency Transfer Fails**
   {fallback}.
   "I was unable to reach our on-call team directly, but your information has been
    logged as a priority. A technician will contact you within 15 minutes."

7. **If NON-EMERGENCY — Collect Service Request**
   "I'll make sure your request is handled first thing during business hours.
    What service do you need, and at which location?"
   Collect: name, phone, address, nature of request.

8. **Confirm Follow-Up**
   "We will follow up with you during our next business hours: {biz_hours}.
    Can I confirm the best number to reach you?"

9. **Ask if Anything Else**
   "Is there anything else I can note for our team?"

10. **Close Call**
    "Thank you for calling {company}. Stay safe, and we'll be in touch soon."
"""


def build_system_prompt(memo: dict) -> str:
    bh = build_business_hours_prompt(memo)
    ah = build_after_hours_prompt(memo)
    company = _fmt(memo.get("company_name"))
    return (
        f"# Clara AI Voice Agent – System Prompt\n"
        f"## Company: {company}\n\n"
        f"You are the AI receptionist for {company}. "
        f"Follow these call scripts exactly. "
        f"Never invent information. If unsure, say: "
        f"\"Let me check on that and get back to you.\"\n\n"
        f"---\n\n"
        f"{bh}\n"
        f"---\n\n"
        f"{ah}"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Agent spec builder
# ─────────────────────────────────────────────────────────────────────────────

def generate_agent_spec(memo: dict, version: str = "1.0") -> dict:
    company = _fmt(memo.get("company_name"), "Unknown Company")
    agent_name = f"{company} Voice Agent"

    # Key variables the agent needs at runtime
    key_variables = {
        "company_name":    memo.get("company_name"),
        "business_hours":  memo.get("business_hours"),
        "timezone":        memo.get("timezone"),
        "emergency_line":  _fmt(memo.get("emergency_routing_rules")),
        "transfer_target": _fmt(memo.get("call_transfer_rules", {}).get("primary")),
    }

    # Transfer protocol
    transfer_rules = memo.get("call_transfer_rules", {})
    call_transfer_protocol = {
        "primary":  transfer_rules.get("primary", []),
        "announce": f"Please hold, I'm transferring you now.",
        "timeout_seconds": 30,
    }

    # Fallback
    fallback = transfer_rules.get("fallback", [])
    fallback_protocol = {
        "on_transfer_failure": fallback or ["Take message, promise callback within business hours"],
        "on_emergency_transfer_failure": [
            "Log caller name, number, and address as priority",
            "Assure callback within 15 minutes",
        ],
    }

    now = datetime.now(timezone.utc).isoformat()

    return {
        "agent_name":             agent_name,
        "account_id":             memo.get("account_id"),
        "voice_style":            "calm, professional, empathetic",
        "language":               "en-US",
        "system_prompt":          build_system_prompt(memo),
        "key_variables":          key_variables,
        "call_transfer_protocol": call_transfer_protocol,
        "fallback_protocol":      fallback_protocol,
        "version":                version,
        "generated_at":           now,
        "source_memo_version":    memo.get("schema_version", "1.0"),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate Retell Agent Spec from Account Memo.")
    parser.add_argument("--memo",       required=True, help="Path to memo.json")
    parser.add_argument("--output_dir", required=True, help="Directory to write agent_spec.json")
    parser.add_argument("--version",    default="1.0", help="Agent spec version string")
    parser.add_argument("--force",      action="store_true", help="Overwrite existing agent_spec.json")
    args = parser.parse_args()

    memo_path   = Path(args.memo).resolve()
    output_dir  = Path(args.output_dir).resolve()
    output_path = output_dir / "agent_spec.json"

    # ── Idempotency check ─────────────────────────────────────────────────────
    if output_path.exists() and not args.force:
        log.info(f"agent_spec.json already exists at {output_path}. Use --force to overwrite. Skipping.")
        sys.exit(0)

    if not memo_path.exists():
        log.error(f"memo.json not found: {memo_path}")
        sys.exit(1)

    memo = json.loads(memo_path.read_text(encoding="utf-8"))
    log.info(f"Generating agent spec for account: {memo.get('account_id')}")

    spec = generate_agent_spec(memo, version=args.version)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Agent spec generated → {output_path}")


if __name__ == "__main__":
    main()
