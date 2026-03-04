"""
scripts/changelog.py
─────────────────────────────────────────────────────────
Pipeline B – Step 4:  Generate field-level changelog

Diffs v1/memo.json vs v2/memo.json and writes a structured
markdown changelog (changes.md) with sections:
  ## Added   – new fields / new list items
  ## Modified – changed scalar or dict values
  ## Removed  – fields present in v1 but gone in v2

Usage
-----
    python scripts/changelog.py \\
        --v1     outputs/accounts/abc_fire_protection/v1/memo.json \\
        --v2     outputs/accounts/abc_fire_protection/v2/memo.json \\
        --output outputs/accounts/abc_fire_protection/v2/changes.md \\
        [--force]
─────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from logger import get_logger

log = get_logger(__name__)

# Fields that are metadata — do not diff these
_SKIP_FIELDS = {"last_updated", "schema_version", "created_at"}


# ─────────────────────────────────────────────────────────────────────────────
#  Diff engine
# ─────────────────────────────────────────────────────────────────────────────

def _value_repr(val: Any) -> str:
    if isinstance(val, list):
        return json.dumps(val, ensure_ascii=False)
    if isinstance(val, dict):
        return json.dumps(val, indent=2, ensure_ascii=False)
    return str(val)


def diff_memos(v1: dict, v2: dict) -> dict:
    """
    Return a structured diff:
    {
      "added":    { field: new_value },
      "modified": { field: {"from": old, "to": new} },
      "removed":  { field: old_value }
    }
    """
    added    = {}
    modified = {}
    removed  = {}

    all_keys = set(v1.keys()) | set(v2.keys())

    for key in sorted(all_keys):
        if key in _SKIP_FIELDS:
            continue

        v1_val = v1.get(key)
        v2_val = v2.get(key)

        # Key only in v2 → Added
        if key not in v1:
            added[key] = v2_val
            continue

        # Key only in v1 → Removed
        if key not in v2:
            removed[key] = v1_val
            continue

        # Both exist — check change
        if isinstance(v1_val, list) and isinstance(v2_val, list):
            added_items   = [x for x in v2_val if x not in v1_val]
            removed_items = [x for x in v1_val if x not in v2_val]
            if added_items or removed_items:
                modified[key] = {
                    "from": v1_val,
                    "to":   v2_val,
                    "_added_items":   added_items,
                    "_removed_items": removed_items,
                }
        elif v1_val != v2_val:
            modified[key] = {"from": v1_val, "to": v2_val}

    return {"added": added, "modified": modified, "removed": removed}


# ─────────────────────────────────────────────────────────────────────────────
#  Markdown formatter
# ─────────────────────────────────────────────────────────────────────────────

def format_changelog_markdown(
    diff: dict, account_id: str, v1_path: str, v2_path: str
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Changelog – `{account_id}`",
        "",
        f"**Generated:** {now}  ",
        f"**Comparing:** `v1/memo.json` → `v2/memo.json`",
        "",
        "---",
        "",
    ]

    # ── Added ─────────────────────────────────────────────────────────────────
    added = diff["added"]
    if added:
        lines.append("## ✅ Added")
        lines.append("")
        for field, val in added.items():
            lines.append(f"- **`{field}`**: `{_value_repr(val)}`")
        lines.append("")
    else:
        lines += ["## ✅ Added", "", "_No new fields added._", ""]

    # ── Modified ──────────────────────────────────────────────────────────────
    modified = diff["modified"]
    if modified:
        lines.append("## ✏️ Modified")
        lines.append("")
        for field, change in modified.items():
            lines.append(f"### `{field}`")
            if "_added_items" in change:
                if change["_added_items"]:
                    lines.append(f"- **Items added:** `{change['_added_items']}`")
                if change["_removed_items"]:
                    lines.append(f"- **Items removed:** `{change['_removed_items']}`")
                lines.append(f"- **From:** `{_value_repr(change['from'])}`")
                lines.append(f"- **To:** `{_value_repr(change['to'])}`")
            else:
                lines.append(f"- **From:** `{_value_repr(change['from'])}`")
                lines.append(f"- **To:**   `{_value_repr(change['to'])}`")
            lines.append("")
    else:
        lines += ["## ✏️ Modified", "", "_No fields modified._", ""]

    # ── Removed ───────────────────────────────────────────────────────────────
    removed = diff["removed"]
    if removed:
        lines.append("## 🗑️ Removed")
        lines.append("")
        for field, val in removed.items():
            lines.append(f"- **`{field}`** (was: `{_value_repr(val)}`)")
        lines.append("")
    else:
        lines += ["## 🗑️ Removed", "", "_No fields removed._", ""]

    lines += [
        "---",
        "",
        "> _This changelog was automatically generated by `changelog.py`._",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate field-level changelog between v1 and v2 memos.")
    parser.add_argument("--v1",     required=True, help="Path to v1/memo.json")
    parser.add_argument("--v2",     required=True, help="Path to v2/memo.json")
    parser.add_argument("--output", required=True, help="Path to write changes.md")
    parser.add_argument("--force",  action="store_true", help="Overwrite existing changes.md")
    args = parser.parse_args()

    v1_path  = Path(args.v1).resolve()
    v2_path  = Path(args.v2).resolve()
    out_path = Path(args.output).resolve()

    # ── Idempotency ───────────────────────────────────────────────────────────
    if out_path.exists() and not args.force:
        log.info(f"changes.md already exists at {out_path}. Use --force to overwrite. Skipping.")
        sys.exit(0)

    if not v1_path.exists():
        log.error(f"v1 memo not found: {v1_path}")
        sys.exit(1)
    if not v2_path.exists():
        log.error(f"v2 memo not found: {v2_path}")
        sys.exit(1)

    v1 = json.loads(v1_path.read_text(encoding="utf-8"))
    v2 = json.loads(v2_path.read_text(encoding="utf-8"))
    account_id = v1.get("account_id", "unknown")

    log.info(f"Generating changelog for account: {account_id}")
    diff = diff_memos(v1, v2)

    n_added    = len(diff["added"])
    n_modified = len(diff["modified"])
    n_removed  = len(diff["removed"])
    log.info(f"Diff result — Added: {n_added}, Modified: {n_modified}, Removed: {n_removed}")

    changelog_md = format_changelog_markdown(diff, account_id, str(v1_path), str(v2_path))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(changelog_md, encoding="utf-8")
    log.info(f"Changelog written → {out_path}")


if __name__ == "__main__":
    main()
