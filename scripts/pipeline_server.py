"""
scripts/pipeline_server.py
─────────────────────────────────────────────────────────
Lightweight local HTTP API server for Clara Agent Pipeline.

n8n uses HTTP Request nodes to call this server instead of
running Python scripts directly (bypasses n8n sandbox restrictions).

Endpoints
---------
POST /normalize   – normalize_transcript.py
POST /extract     – extract_memo.py
POST /generate    – generate_agent.py
POST /patch       – apply_patch.py
POST /changelog   – changelog.py
POST /pipeline-a  – full Pipeline A (normalize + extract + generate)
POST /pipeline-b  – full Pipeline B (normalize + patch + generate + changelog)
GET  /health      – health check

Usage
-----
    python scripts/pipeline_server.py
    # Server runs at http://localhost:8765

    # Or custom port:
    python scripts/pipeline_server.py --port 8765
─────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from logger import get_logger

log = get_logger("pipeline_server")

_REPO_ROOT   = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent


# ─────────────────────────────────────────────────────────────────────────────
#  Script runner helper
# ─────────────────────────────────────────────────────────────────────────────

def run_script(script_name: str, args: list[str]) -> dict:
    """Run a pipeline Python script and return result dict."""
    cmd = [sys.executable, str(_SCRIPTS_DIR / script_name)] + args
    log.info(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return {"status": "ok", "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        else:
            return {"status": "error", "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"status": "error", "stderr": "Script timed out after 120s"}
    except Exception as e:
        return {"status": "error", "stderr": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
#  Route handlers
# ─────────────────────────────────────────────────────────────────────────────

def handle_normalize(body: dict) -> dict:
    """
    Body: { "input": "dataset/demo_calls/demo_transcript_001.txt",
            "output": "dataset/demo_calls/demo_transcript_001_normalized.txt" }
    """
    input_path  = body.get("input", "")
    output_path = body.get("output", input_path.replace(".txt", "_normalized.txt"))
    if not input_path:
        return {"status": "error", "message": "Missing 'input' field"}
    result = run_script("normalize_transcript.py", ["--input", input_path, "--output", output_path])
    result["normalized_path"] = output_path
    return result


def handle_extract(body: dict) -> dict:
    """
    Body: { "input": "..._normalized.txt",
            "account_id": "abc_fire_protection",
            "output_dir": "outputs/accounts/abc_fire_protection/v1",
            "force": true }
    """
    input_path  = body.get("input", "")
    account_id  = body.get("account_id", "")
    output_dir  = body.get("output_dir", "")
    force       = body.get("force", False)
    if not input_path or not output_dir:
        return {"status": "error", "message": "Missing 'input' or 'output_dir'"}
    args = ["--input", input_path, "--output_dir", output_dir]
    if account_id:
        args += ["--account_id", account_id]
    if force:
        args.append("--force")
    result = run_script("extract_memo.py", args)
    result["memo_path"] = output_dir + "/memo.json"
    return result


def handle_generate(body: dict) -> dict:
    """
    Body: { "memo": "outputs/accounts/abc_fire_protection/v1/memo.json",
            "output_dir": "outputs/accounts/abc_fire_protection/v1",
            "version": "1.0", "force": true }
    """
    memo_path  = body.get("memo", "")
    output_dir = body.get("output_dir", "")
    version    = body.get("version", "1.0")
    force      = body.get("force", False)
    if not memo_path or not output_dir:
        return {"status": "error", "message": "Missing 'memo' or 'output_dir'"}
    args = ["--memo", memo_path, "--output_dir", output_dir, "--version", version]
    if force:
        args.append("--force")
    result = run_script("generate_agent.py", args)
    result["agent_spec_path"] = output_dir + "/agent_spec.json"
    return result


def handle_patch(body: dict) -> dict:
    """
    Body: { "v1_memo": "outputs/.../v1/memo.json",
            "onboarding": "dataset/onboarding_calls/onboarding_001_normalized.txt",
            "output_dir": "outputs/.../v2", "force": true }
    """
    v1_memo    = body.get("v1_memo", "")
    onboarding = body.get("onboarding", "")
    output_dir = body.get("output_dir", "")
    force      = body.get("force", False)
    if not v1_memo or not onboarding or not output_dir:
        return {"status": "error", "message": "Missing required fields"}
    args = ["--v1_memo", v1_memo, "--onboarding", onboarding, "--output_dir", output_dir]
    if force:
        args.append("--force")
    result = run_script("apply_patch.py", args)
    result["v2_memo_path"] = output_dir + "/memo.json"
    return result


def handle_changelog(body: dict) -> dict:
    """
    Body: { "v1": "outputs/.../v1/memo.json",
            "v2": "outputs/.../v2/memo.json",
            "output": "outputs/.../v2/changes.md", "force": true }
    """
    v1     = body.get("v1", "")
    v2     = body.get("v2", "")
    output = body.get("output", "")
    force  = body.get("force", False)
    if not v1 or not v2 or not output:
        return {"status": "error", "message": "Missing 'v1', 'v2', or 'output'"}
    args = ["--v1", v1, "--v2", v2, "--output", output]
    if force:
        args.append("--force")
    result = run_script("changelog.py", args)
    result["changelog_path"] = output
    return result


def handle_pipeline_a(body: dict) -> dict:
    """
    Full Pipeline A in one call.
    Body: { "transcript": "dataset/demo_calls/demo_transcript_001.txt",
            "account_id": "abc_fire_protection",
            "output_dir": "outputs/accounts/abc_fire_protection/v1",
            "force": true }
    """
    transcript = body.get("transcript", "")
    account_id = body.get("account_id", "")
    output_dir = body.get("output_dir", "")
    force      = body.get("force", False)

    if not transcript or not output_dir:
        return {"status": "error", "message": "Missing 'transcript' or 'output_dir'"}

    normalized = transcript.replace(".txt", "_normalized.txt")

    # Step 1 – Normalize
    r1 = handle_normalize({"input": transcript, "output": normalized})
    if r1["status"] != "ok":
        return {"status": "error", "step": "normalize", "detail": r1}

    # Step 2 – Extract
    r2 = handle_extract({"input": normalized, "account_id": account_id,
                          "output_dir": output_dir, "force": force})
    if r2["status"] != "ok":
        return {"status": "error", "step": "extract", "detail": r2}

    # Step 3 – Generate
    r3 = handle_generate({"memo": output_dir + "/memo.json",
                           "output_dir": output_dir, "force": force})
    if r3["status"] != "ok":
        return {"status": "error", "step": "generate", "detail": r3}

    return {
        "status": "ok",
        "pipeline": "A",
        "account_id": account_id,
        "memo_path": output_dir + "/memo.json",
        "agent_spec_path": output_dir + "/agent_spec.json",
    }


def handle_pipeline_b(body: dict) -> dict:
    """
    Full Pipeline B in one call.
    Body: { "onboarding": "dataset/onboarding_calls/onboarding_001.txt",
            "v1_memo": "outputs/.../v1/memo.json",
            "v2_output_dir": "outputs/.../v2",
            "force": true }
    """
    onboarding  = body.get("onboarding", "")
    v1_memo     = body.get("v1_memo", "")
    v2_dir      = body.get("v2_output_dir", "")
    force       = body.get("force", False)

    if not onboarding or not v1_memo or not v2_dir:
        return {"status": "error", "message": "Missing required fields"}

    normalized = onboarding.replace(".txt", "_normalized.txt")

    r1 = handle_normalize({"input": onboarding, "output": normalized})
    if r1["status"] != "ok":
        return {"status": "error", "step": "normalize", "detail": r1}

    r2 = handle_patch({"v1_memo": v1_memo, "onboarding": normalized,
                        "output_dir": v2_dir, "force": force})
    if r2["status"] != "ok":
        return {"status": "error", "step": "patch", "detail": r2}

    r3 = handle_generate({"memo": v2_dir + "/memo.json",
                           "output_dir": v2_dir, "version": "2.0", "force": force})
    if r3["status"] != "ok":
        return {"status": "error", "step": "generate_v2", "detail": r3}

    r4 = handle_changelog({"v1": v1_memo, "v2": v2_dir + "/memo.json",
                            "output": v2_dir + "/changes.md", "force": force})
    if r4["status"] != "ok":
        return {"status": "error", "step": "changelog", "detail": r4}

    return {
        "status": "ok",
        "pipeline": "B",
        "v2_memo_path": v2_dir + "/memo.json",
        "agent_spec_path": v2_dir + "/agent_spec.json",
        "changelog_path": v2_dir + "/changes.md",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  HTTP Server
# ─────────────────────────────────────────────────────────────────────────────

ROUTES = {
    "/normalize":  handle_normalize,
    "/extract":    handle_extract,
    "/generate":   handle_generate,
    "/patch":      handle_patch,
    "/changelog":  handle_changelog,
    "/pipeline-a": handle_pipeline_a,
    "/pipeline-b": handle_pipeline_b,
}


class PipelineHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        log.info(f"HTTP {format % args}")

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json({"status": "ok", "service": "Clara Pipeline Server",
                             "routes": list(ROUTES.keys())})
        else:
            self._send_json({"error": f"Unknown route: {path}"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ROUTES:
            self._send_json({"error": f"Unknown route: {path}"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw    = self.rfile.read(length) if length else b"{}"
            body   = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception as e:
            self._send_json({"error": f"Invalid JSON body: {e}"}, 400)
            return
        try:
            result = ROUTES[path](body)
            http_status = 200 if result.get("status") == "ok" else 500
            self._send_json(result, http_status)
        except Exception as e:
            log.error(traceback.format_exc())
            self._send_json({"status": "error", "message": str(e)}, 500)


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Clara Pipeline local API server")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), PipelineHandler)
    log.info(f"Clara Pipeline Server running at http://{args.host}:{args.port}")
    log.info(f"Available routes: {list(ROUTES.keys())}")
    log.info("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Server stopped.")


if __name__ == "__main__":
    main()
