"""Runs the promptfoo behavioural evals (backend/evals) through pytest.

Live: calls Gemini once per case with EVAL_GEMINI_MODEL (default gemini-2.5-flash). Needs
GEMINI_API_KEY in backend/.env (or the environment) and `npm ci` inside backend/evals.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from shared.config.settings import get_settings

EVALS_DIR = Path(__file__).resolve().parents[2] / "evals"
CONFIG = "promptfooconfig.yaml"
RESULTS_DIR = EVALS_DIR / "results"
# Cheaper model for test runs only; the app keeps GEMINI_MODEL (3.5) for development and production.
EVAL_GEMINI_MODEL = os.environ.get("EVAL_GEMINI_MODEL", "gemini-2.5-flash")


def _promptfoo_binary() -> Path:
    name = "promptfoo.cmd" if os.name == "nt" else "promptfoo"
    return EVALS_DIR / "node_modules" / ".bin" / name


@pytest.mark.live
def test_promptfoo_behavioural_evals_pass() -> None:
    settings = get_settings()
    if not settings.gemini_api_key:
        pytest.skip("GEMINI_API_KEY not set (env or backend/.env)")
    binary = _promptfoo_binary()
    if not binary.exists():
        pytest.skip("promptfoo not installed: run `npm ci` in backend/evals")

    RESULTS_DIR.mkdir(exist_ok=True)
    output = RESULTS_DIR / "promptfoo-results.json"
    env = {
        **os.environ,
        "GEMINI_API_KEY": settings.gemini_api_key,
        "GEMINI_MODEL": EVAL_GEMINI_MODEL,
        # Gemini only for evals: an empty Cursor key keeps the fallback (Cursor) out of the run.
        "CURSOR_API_KEY": "",
        "PROMPTFOO_DISABLE_TELEMETRY": "1",
        # Run provider.py with the interpreter that has the backend dependencies installed.
        "PROMPTFOO_PYTHON": sys.executable,
    }

    completed = subprocess.run(
        [str(binary), "eval", "-c", CONFIG, "-o", str(output), "--no-cache"],
        cwd=EVALS_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    stats = report["results"]["stats"]
    assert completed.returncode == 0, completed.stderr[-2000:] or completed.stdout[-2000:]
    assert stats["failures"] == 0
    assert stats["errors"] == 0
