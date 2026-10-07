from __future__ import annotations

import subprocess

from agent.cmux_notifications import notify_api_retry_exhausted


def test_retry_exhaustion_targets_current_cmux_surface(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("CMUX_BUNDLED_CLI_PATH", "/Applications/cmux.app/cmux")
    monkeypatch.setenv("CMUX_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("CMUX_SURFACE_ID", "surface-1")
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert notify_api_retry_exhausted(3) is True
    assert calls[0][0] == [
        "/Applications/cmux.app/cmux",
        "notify",
        "--title",
        "Hermes API failure",
        "--subtitle",
        "3 retries exhausted",
        "--body",
        "API call failed after 3 retries",
        "--workspace",
        "workspace-1",
        "--surface",
        "surface-1",
    ]


def test_retry_exhaustion_skips_subagents(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()),
    )

    assert notify_api_retry_exhausted(3, platform="subagent") is False


def test_retry_exhaustion_is_fail_open(monkeypatch):
    monkeypatch.setenv("CMUX_BUNDLED_CLI_PATH", "/Applications/cmux.app/cmux")
    monkeypatch.setenv("CMUX_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("CMUX_SURFACE_ID", "surface-1")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("cmux", 3)
        ),
    )

    assert notify_api_retry_exhausted(3) is False