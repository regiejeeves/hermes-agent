"""Regression coverage for the cron-only forced Rich Message delivery path."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def _install_telegram(monkeypatch, bot):
    telegram = SimpleNamespace(
        Bot=MagicMock(return_value=bot),
        constants=SimpleNamespace(ParseMode=SimpleNamespace(MARKDOWN_V2="MarkdownV2", HTML="HTML")),
    )
    monkeypatch.setitem(sys.modules, "telegram", telegram)
    monkeypatch.setitem(sys.modules, "telegram.constants", telegram.constants)


def test_telegram_adapter_force_rich_metadata_bypasses_shape_heuristic(monkeypatch):
    """A generic cron report uses rich transport even without a table/details block."""
    from plugins.platforms.telegram.adapter import TelegramAdapter

    adapter = object.__new__(TelegramAdapter)
    adapter._rich_messages_enabled = True
    adapter._rich_send_disabled = False
    monkeypatch.setattr(adapter, "_rich_content_ok", lambda content: True)

    assert adapter._should_attempt_rich("ordinary cron report", metadata={"force_rich": True})
    assert not adapter._should_attempt_rich("ordinary chat reply", metadata={})


def test_standalone_telegram_force_rich_uses_native_endpoint(monkeypatch):
    """The cron fallback lane must not silently downgrade to sendMessage."""
    from tools.send_message_senders import _send_telegram

    bot = MagicMock()
    bot.do_api_request = AsyncMock(return_value={"message_id": 314, "rich_message": {"markdown": "Cron report"}})
    _install_telegram(monkeypatch, bot)
    monkeypatch.setattr("gateway.platforms.base.resolve_proxy_url", lambda *args, **kwargs: None)

    result = asyncio.run(_send_telegram("token", "156986272", "Cron report", force_rich=True))

    assert result["success"] is True
    assert result["message_id"] == "314"
    bot.do_api_request.assert_awaited_once_with(
        "sendRichMessage",
        api_kwargs={"chat_id": 156986272, "rich_message": {"markdown": "Cron report"}},
    )
    bot.send_message.assert_not_called()


def test_cron_force_rich_config_is_opt_in_and_tolerates_bad_config():
    from cron.scheduler_delivery import _cron_force_rich_telegram_enabled

    assert _cron_force_rich_telegram_enabled({"cron": {"delivery": {"force_rich_telegram": True}}})
    assert not _cron_force_rich_telegram_enabled({"cron": {"delivery": {}}})
    assert not _cron_force_rich_telegram_enabled({"cron": {"delivery": "oops"}})
    assert not _cron_force_rich_telegram_enabled(None)


def test_standalone_prose_goes_native_only_when_forced(monkeypatch):
    """rich_messages alone keeps the structural heuristic; force_rich sends plain prose natively."""
    from tools.send_message_senders import _send_telegram

    bot = MagicMock()
    bot.do_api_request = AsyncMock(return_value={"message_id": 7, "rich_message": {}})
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=8))
    _install_telegram(monkeypatch, bot)
    monkeypatch.setattr("gateway.platforms.base.resolve_proxy_url", lambda *args, **kwargs: None)

    asyncio.run(_send_telegram("token", "156986272", "just some prose", rich_messages=True))
    bot.do_api_request.assert_not_awaited()

    asyncio.run(_send_telegram("token", "156986272", "just some prose", force_rich=True))
    bot.do_api_request.assert_awaited_once()
    assert "disable_notification" not in bot.do_api_request.await_args.kwargs["api_kwargs"]
