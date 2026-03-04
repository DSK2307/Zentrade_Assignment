"""
scripts/extraction_rules.py
─────────────────────────────────────────────────────────
Rule-based field extraction module for Clara Agent Pipeline.

Strategy
--------
1. Apply regex / keyword rules first (free, fast, deterministic)
2. If field still None and Ollama available → call LLM once  (optional)
3. If still None → field stays None; caller appends to questions_or_unknowns

NEVER invent or infer values not present in the transcript.
─────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
import json
from typing import Optional, List

# ── Optional Ollama import (graceful fallback) ────────────────────────────────
try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

OLLAMA_URL    = "http://localhost:11434/api/generate"
OLLAMA_MODEL  = "llama3"
OLLAMA_TIMEOUT = 30  # seconds


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _search(pattern: str, text: str, flags: int = re.IGNORECASE) -> Optional[re.Match]:
    return re.search(pattern, text, flags)


def _findall(pattern: str, text: str, flags: int = re.IGNORECASE) -> List[str]:
    return re.findall(pattern, text, flags)


def _normalize_time(raw: str) -> str:
    """Convert '8am', '8 AM', '8:00am' → '08:00'; '5pm' → '17:00'."""
    raw = raw.strip().lower().replace(" ", "")
    match = re.match(r"^(\d{1,2})(?::(\d{2}))?([ap]m)?$", raw)
    if not match:
        return raw
    hour   = int(match.group(1))
    minute = int(match.group(2) or 0)
    ampm   = match.group(3)
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


# ─────────────────────────────────────────────────────────────────────────────
#  Public extraction functions
# ─────────────────────────────────────────────────────────────────────────────

def extract_company_name(text: str) -> Optional[str]:
    """
    Detect company name from common transcript greeting patterns.
    e.g. "This is ABC Fire Protection calling" / "from XYZ Services"
    """
    patterns = [
        r"(?:this is|I'm|I am|we are|from|with|of)\s+([A-Z][A-Za-z0-9&'\s]+?(?:Inc|LLC|Ltd|Corp|Services|Protection|Solutions|Group|Systems|Co\.?))",
        r"([A-Z][A-Za-z0-9&'\s]+?(?:Inc|LLC|Ltd|Corp|Services|Protection|Solutions|Group|Systems|Co\.?))",
        r"company[:\s]+([A-Z][A-Za-z0-9&'\s]{2,40})",
        r"(?:account|client|customer)[:\s]+([A-Z][A-Za-z0-9&'\s]{2,40})",
    ]
    for pat in patterns:
        m = _search(pat, text)
        if m:
            return m.group(1).strip()
    return None


def extract_business_hours(text: str) -> Optional[dict]:
    """
    Extract business hours object with open_time, close_time, days.

    Supports:
        '8am to 5pm', '8:00 - 17:00', '8 AM – 5 PM',
        'Monday to Friday', 'Mon-Fri', 'Monday through Friday'
    """
    result = {}

    # Time range
    time_pattern = (
        r"(\d{1,2}(?::\d{2})?\s*[aApP][mM]?)"
        r"\s*(?:to|–|-|through|until)\s*"
        r"(\d{1,2}(?::\d{2})?\s*[aApP][mM]?)"
    )
    tm = _search(time_pattern, text)
    if tm:
        result["open_time"]  = _normalize_time(tm.group(1))
        result["close_time"] = _normalize_time(tm.group(2))

    # 24-hour range  e.g. "08:00 - 17:00"
    h24 = _search(r"(\d{2}:\d{2})\s*[-–]\s*(\d{2}:\d{2})", text)
    if h24 and "open_time" not in result:
        result["open_time"]  = h24.group(1)
        result["close_time"] = h24.group(2)

    # Day range
    day_patterns = [
        r"(Monday|Mon)\s*(?:to|–|-|through)\s*(Friday|Fri)",
        r"(Monday|Mon)\s*(?:to|–|-|through)\s*(Thursday|Thu)",
        r"(Monday|Mon)\s*(?:to|–|-|through)\s*(Saturday|Sat)",
    ]
    for dp in day_patterns:
        dm = _search(dp, text)
        if dm:
            result["days"] = f"{dm.group(1)[:3]}-{dm.group(2)[:3]}"
            break

    # Explicit Mon-Fri style
    if "days" not in result:
        mf = _search(r"\b(Mon-Fri|Mon–Fri|Monday-Friday|Monday–Friday)\b", text)
        if mf:
            result["days"] = "Mon-Fri"

    return result if result else None


def extract_timezone(text: str) -> Optional[str]:
    """Detect timezone abbreviation or name."""
    m = _search(
        r"\b(PST|PDT|MST|MDT|CST|CDT|EST|EDT|GMT|UTC"
        r"|Pacific|Mountain|Central|Eastern|IST|AEST)\b",
        text,
    )
    return m.group(1) if m else None


def extract_emergency_definition(text: str) -> List[str]:
    """
    Return list of emergency keywords/phrases found in transcript.
    Keywords: fire alarm, sprinkler leak, water leak, alarm activation,
              fire suppression failure, gas leak, structural fire
    """
    keywords = [
        "sprinkler leak", "sprinkler activation", "fire alarm",
        "fire alarm triggered", "fire alarm activation",
        "water leak", "alarm activation", "fire suppression",
        "fire suppression failure", "gas leak", "structural fire",
        "smoke detector", "carbon monoxide", "co alarm",
    ]
    found = []
    text_lower = text.lower()
    for kw in keywords:
        if kw in text_lower:
            found.append(kw)
    return found


def extract_services_supported(text: str) -> List[str]:
    """
    Detect services mentioned in transcript.
    Keywords: sprinkler, alarm, extinguisher, inspection, maintenance,
              testing, suppression, fire pump
    """
    keywords = [
        "sprinkler", "fire alarm", "extinguisher", "fire extinguisher",
        "inspection", "maintenance", "testing", "suppression",
        "fire pump", "backflow", "monitoring", "emergency service",
        "repair", "installation",
    ]
    found = []
    text_lower = text.lower()
    for kw in keywords:
        if kw in text_lower and kw not in found:
            found.append(kw)
    return found


def extract_emergency_routing_rules(text: str) -> List[str]:
    """
    Detect emergency routing instructions.
    e.g. 'route to dispatch', 'call technician', 'page on-call'
    """
    patterns = [
        r"route\s+(?:emergency\s+)?(?:call\s+)?to\s+(\w[\w\s]+)",
        r"(?:call|page|contact|transfer\s+to)\s+(?:the\s+)?(?:on[- ]?call\s+)?(\w[\w\s]+)",
        r"dispatch\s+(?:a\s+)?(\w[\w\s]+technician|\w[\w\s]+team)",
        r"emergency\s+(?:line|number)[:\s]+([+\d\s()\-]+)",
        r"transfer\s+(?:to\s+)?(\w[\w\s]+)",
    ]
    found = []
    for pat in patterns:
        for m in _findall(pat, text):
            rule = m.strip().rstrip(".,")
            if rule and rule not in found:
                found.append(rule)
    return found


def extract_non_emergency_routing_rules(text: str) -> List[str]:
    """Detect non-emergency / routine routing instructions."""
    patterns = [
        r"(?:for\s+)?(?:routine|non[- ]?emergency|general|regular)\s+(?:call|request|inquiry)[,\s]+(?:please\s+)?(.+?)(?:\.|,|$)",
        r"schedule\s+(?:a\s+)?(?:service|appointment|visit|callback)\s+(?:with\s+)?(\w[\w\s]+)",
        r"leave\s+(?:a\s+)?(?:voicemail|message)",
        r"(?:email|send)\s+(?:to\s+)?(\S+@\S+)",
    ]
    found = []
    text_lower = text.lower()
    for pat in patterns:
        for m in _findall(pat, text_lower):
            rule = m.strip().rstrip(".,")
            if rule and rule not in found:
                found.append(rule)
    # Generic keyword detection
    if "voicemail" in text_lower and "leave voicemail" not in found:
        found.append("leave voicemail")
    if "schedule" in text_lower and "schedule service appointment" not in found:
        found.append("schedule service appointment")
    return found


def extract_call_transfer_rules(text: str) -> dict:
    """
    Detect call transfer instructions and fallback behavior.
    """
    result = {"primary": [], "fallback": []}
    transfer_m = _search(
        r"transfer\s+(?:the\s+)?(?:call\s+)?to\s+(?:the\s+)?(.+?)(?:\.|,|$)", text
    )
    if transfer_m:
        result["primary"].append(transfer_m.group(1).strip())

    fallback_m = _search(
        r"(?:if\s+(?:transfer\s+)?(?:fails?|unsuccessful|no\s+answer)|transfer\s+failure)[,:\s]+(.+?)(?:\.|$)",
        text, re.IGNORECASE
    )
    if fallback_m:
        result["fallback"].append(fallback_m.group(1).strip())

    return result if (result["primary"] or result["fallback"]) else {}


def extract_address(text: str) -> Optional[str]:
    """Extract office address."""
    m = _search(
        r"\d{1,5}\s+[A-Za-z0-9\s]+(?:Street|St|Avenue|Ave|Road|Rd|Blvd|Boulevard|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl)[\w\s,\.]*",
        text,
    )
    return m.group(0).strip() if m else None


def extract_phone_numbers(text: str) -> List[str]:
    """Extract phone numbers from transcript."""
    pattern = r"(\+?1?\s*[\(\-]?\d{3}[\)\-\s]?\s*\d{3}[\-\s]?\d{4})"
    return list(set(_findall(pattern, text)))


def extract_integration_constraints(text: str) -> List[str]:
    """Detect software/CRM integration mentions."""
    tools = [
        "ServiceTitan", "Salesforce", "HubSpot", "Zendesk", "Freshdesk",
        "Monday.com", "Slack", "Teams", "RingCentral", "Twilio",
        "CRM", "ERP", "ticketing system",
    ]
    found = []
    text_lower = text.lower()
    for tool in tools:
        if tool.lower() in text_lower:
            found.append(tool)
    return found


# ─────────────────────────────────────────────────────────────────────────────
#  Optional LLM fallback (Ollama / Llama3 – local, zero cost)
# ─────────────────────────────────────────────────────────────────────────────

def _ollama_available() -> bool:
    if not _REQUESTS_AVAILABLE:
        return False
    try:
        r = _requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def llm_extract_field(transcript: str, field_name: str, field_description: str) -> Optional[str]:
    """
    Ask local Ollama/Llama3 to extract a specific field.
    Returns None if Ollama unavailable or extraction fails.
    Called ONLY when rule-based extraction returns nothing.
    """
    if not _ollama_available():
        return None

    prompt = (
        f"You are a data extraction assistant. "
        f"Extract the field '{field_name}' ({field_description}) from the following call transcript.\n"
        f"Return ONLY the extracted value as plain text. "
        f"If the information is not clearly stated, return exactly: NOT_FOUND\n\n"
        f"Transcript:\n{transcript}\n\n"
        f"Extracted {field_name}:"
    )

    try:
        resp = _requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        value = resp.json().get("response", "").strip()
        if value.upper() == "NOT_FOUND" or not value:
            return None
        return value
    except Exception:
        return None
