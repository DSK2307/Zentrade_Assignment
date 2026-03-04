"""
scripts/logger.py
─────────────────────────────────────────────────────────
Centralized logging for Clara Agent Pipeline.
All scripts import get_logger() from this module.

Log file: logs/pipeline.log
Format:   [YYYY-MM-DD HH:MM:SS] [LEVEL] message
─────────────────────────────────────────────────────────
"""

import logging
import os
from pathlib import Path
from datetime import datetime

# ── Resolve log directory relative to this file's repo root ──────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR   = _REPO_ROOT / "logs"
_LOG_FILE  = _LOG_DIR / "pipeline.log"

# Ensure logs/ directory exists before first logger is built
_LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_logger(name: str = "clara") -> logging.Logger:
    """
    Return a named logger that writes to both stdout and logs/pipeline.log.

    Usage
    -----
    from logger import get_logger
    log = get_logger(__name__)
    log.info("Processing transcript demo_transcript_001")
    log.warning("Missing timezone")
    log.error("Failed to parse business hours")
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if get_logger is called more than once
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    _fmt = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── File handler ──────────────────────────────────────────────────────────
    fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_fmt)

    # ── Console handler ───────────────────────────────────────────────────────
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(_fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger
