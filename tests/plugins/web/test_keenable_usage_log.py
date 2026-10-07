"""Keenable requests are counted in Houston's usage ledger (~/.hermes/lib/_usage_log.py).

Neither vendor publishes a usage endpoint, so the provider logs each request itself.
"""

import json
import sys
import types

from plugins.web.keenable import provider as keenable_provider


def _fake_usage_log(calls):
    mod = types.ModuleType("_usage_log")
    mod.append = lambda name, fields: calls.append((name, fields))
    return mod


def test_log_usage_writes_one_ledger_entry(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "_usage_log", _fake_usage_log(calls))

    keenable_provider._log_usage("extract", 3)

    assert calls == [("keenable", {"kind": "extract", "n": 3, "label": "hermes-web", "ok": True})]


def test_log_usage_falls_back_to_jsonl_and_never_raises(monkeypatch, tmp_path):
    class _Broken(types.ModuleType):
        def __getattr__(self, name):
            raise RuntimeError("ledger unavailable")

    monkeypatch.setitem(sys.modules, "_usage_log", _Broken("_usage_log"))
    monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path / "usage.jsonl") if p.endswith(".jsonl") else p)

    keenable_provider._log_usage("search")  # must not raise

    line = json.loads((tmp_path / "usage.jsonl").read_text().strip())
    assert line["kind"] == "search" and line["n"] == 1


def test_search_logs_before_the_request(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "_usage_log", _fake_usage_log(calls))
    monkeypatch.setattr(keenable_provider, "provider_env", lambda name: "")
    monkeypatch.setattr(keenable_provider, "use_keyless", lambda *a, **k: True)
    monkeypatch.setattr(keenable_provider, "keyless_search", lambda *a, **k: {"success": True, "data": {"web": []}})

    keenable_provider.KeenableWebSearchProvider().search("q")

    assert [c[1]["kind"] for c in calls] == ["search"]
