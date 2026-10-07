"""Best-effort user notifications for Hermes turns running inside cmux."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)


def notify_api_retry_exhausted(max_retries: int, *, platform: str = "") -> bool:
    """Notify the owning cmux surface after terminal API retry exhaustion.

    This is intentionally best-effort. A missing cmux executable, absent surface
    metadata, socket failure, or notification timeout must never alter the
    failed turn's normal response path.
    """
    if platform.strip().lower() == "subagent":
        return False

    workspace_id = os.environ.get("CMUX_WORKSPACE_ID") or os.environ.get(
        "CMUX_TAB_ID"
    )
    surface_id = os.environ.get("CMUX_SURFACE_ID") or os.environ.get(
        "CMUX_PANEL_ID"
    )
    if not workspace_id and not surface_id:
        return False

    cmux_bin = os.environ.get("CMUX_BUNDLED_CLI_PATH") or shutil.which("cmux")
    if not cmux_bin:
        return False

    retries = max(0, int(max_retries))
    command = [
        cmux_bin,
        "notify",
        "--title",
        "Hermes API failure",
        "--subtitle",
        f"{retries} retries exhausted",
        "--body",
        f"API call failed after {retries} retries",
    ]
    if workspace_id:
        command.extend(["--workspace", workspace_id])
    if surface_id:
        command.extend(["--surface", surface_id])

    try:
        completed = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        logger.debug("cmux retry-exhaustion notification failed", exc_info=True)
        return False
    return completed.returncode == 0
