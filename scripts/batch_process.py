"""
scripts/batch_process.py
─────────────────────────────────────────────────────────
Batch processing runner for Pipeline A.

Scans dataset/demo_calls/ for all .txt transcripts,
runs normalize → extract → generate on each, and
produces outputs/summary_report.json + a CLI summary table.

Usage
-----
    python scripts/batch_process.py \\
        --dataset_dir dataset/demo_calls \\
        --output_dir  outputs/accounts \\
        [--force]
─────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from logger import get_logger

log = get_logger(__name__)

_REPO_ROOT   = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent


def run_script(script: str, args: list[str]) -> tuple[int, str]:
    """Run a Python script in a subprocess and return (returncode, stderr)."""
    cmd = [sys.executable, str(_SCRIPTS_DIR / script)] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stderr.strip()


def process_transcript(
    transcript_path: Path,
    output_root: Path,
    force: bool,
) -> dict:
    """
    Run full Pipeline A on a single transcript.
    Returns a result dict for the summary report.
    """
    name = transcript_path.stem
    log.info(f"{'─'*50}")
    log.info(f"Processing: {transcript_path.name}")

    result = {
        "file": transcript_path.name,
        "account_id": None,
        "status": "ok",
        "missing_business_hours": False,
        "missing_emergency_definition": False,
        "error": None,
    }

    # ── Step 1: Normalize ─────────────────────────────────────────────────────
    normalized_path = transcript_path.parent / f"{name}_normalized.txt"
    rc, err = run_script("normalize_transcript.py", [
        "--input",  str(transcript_path),
        "--output", str(normalized_path),
    ])
    if rc != 0:
        log.error(f"Normalization failed for {name}: {err}")
        result.update({"status": "error", "error": f"normalize failed: {err}"})
        return result

    # ── Step 2: Extract memo ──────────────────────────────────────────────────
    # Auto account_id from filename for temp use; extract_memo.py will resolve properly
    temp_id = name.replace("demo_transcript_", "account_").replace("_normalized", "")

    # Determine actual output dir after potential slug resolution
    # We use a temporary dir name — extract_memo will compute slug internally
    temp_out = output_root / temp_id / "v1"
    force_flag = ["--force"] if force else []

    rc, err = run_script("extract_memo.py", [
        "--input",      str(normalized_path),
        "--output_dir", str(temp_out),
        "--account_id", temp_id,
    ] + force_flag)
    if rc != 0:
        log.error(f"Extraction failed for {name}: {err}")
        result.update({"status": "error", "error": f"extract failed: {err}"})
        return result

    # ── Read memo to collect stats ─────────────────────────────────────────────
    memo_path = temp_out / "memo.json"
    if memo_path.exists():
        memo = json.loads(memo_path.read_text(encoding="utf-8"))
        result["account_id"] = memo.get("account_id", temp_id)
        result["missing_business_hours"]       = not bool(memo.get("business_hours"))
        result["missing_emergency_definition"] = not bool(memo.get("emergency_definition"))
    else:
        result["missing_business_hours"]       = True
        result["missing_emergency_definition"] = True

    # ── Step 3: Generate agent spec ───────────────────────────────────────────
    rc, err = run_script("generate_agent.py", [
        "--memo",       str(memo_path),
        "--output_dir", str(temp_out),
    ] + force_flag)
    if rc != 0:
        log.error(f"Agent generation failed for {name}: {err}")
        result.update({"status": "error", "error": f"generate failed: {err}"})
        return result

    log.info(f"Done: {name} → {result['account_id']}")
    return result


def print_summary(results: list[dict]) -> None:
    ok_results    = [r for r in results if r["status"] == "ok"]
    err_results   = [r for r in results if r["status"] == "error"]
    miss_bh       = sum(1 for r in ok_results if r["missing_business_hours"])
    miss_ed       = sum(1 for r in ok_results if r["missing_emergency_definition"])

    print()
    print("┌──────────────────────────────────────────┐")
    print("│          Pipeline Summary Report          │")
    print("├──────────────────────────────────────────┤")
    print(f"│  Transcripts processed  : {len(results):<15}│")
    print(f"│  Accounts created       : {len(ok_results):<15}│")
    print(f"│  Extraction errors      : {len(err_results):<15}│")
    print(f"│  Missing business hours : {miss_bh:<15}│")
    print(f"│  Missing emergency defs : {miss_ed:<15}│")
    print("└──────────────────────────────────────────┘")


def main():
    parser = argparse.ArgumentParser(description="Batch process demo call transcripts (Pipeline A).")
    parser.add_argument("--dataset_dir", required=True, help="Folder containing demo_transcript_*.txt files")
    parser.add_argument("--output_dir",  required=True, help="Root folder for outputs/accounts/")
    parser.add_argument("--force",       action="store_true", help="Force overwrite existing outputs")
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir).resolve()
    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    transcripts = sorted(dataset_dir.glob("*.txt"))
    # Exclude already-normalized files
    transcripts = [t for t in transcripts if "_normalized" not in t.stem]

    if not transcripts:
        log.warning(f"No transcripts found in {dataset_dir}")
        sys.exit(0)

    log.info(f"Found {len(transcripts)} transcript(s) to process in {dataset_dir}")

    results = []
    for t in transcripts:
        r = process_transcript(t, output_root, force=args.force)
        results.append(r)

    # ── Print summary table ───────────────────────────────────────────────────
    print_summary(results)

    # ── Save summary_report.json ──────────────────────────────────────────────
    report = {
        "run_timestamp":              datetime.now(timezone.utc).isoformat(),
        "processed":                  len(results),
        "accounts_created":           sum(1 for r in results if r["status"] == "ok"),
        "errors":                     sum(1 for r in results if r["status"] == "error"),
        "missing_business_hours":     sum(1 for r in results if r["missing_business_hours"]),
        "missing_emergency_definitions": sum(1 for r in results if r["missing_emergency_definition"]),
        "details":                    results,
    }

    reports_path = _REPO_ROOT / "outputs" / "summary_report.json"
    reports_path.parent.mkdir(parents=True, exist_ok=True)
    reports_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Summary report saved → {reports_path}")


if __name__ == "__main__":
    main()
