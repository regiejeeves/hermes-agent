"""Regression tests for Telegram Rich Messages in the standalone send path."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("telegram", reason="python-telegram-bot not installed")

from gateway.config import Platform
from plugins.platforms.telegram.adapter import _standalone_send
from telegram.error import BadRequest, NetworkError
from tools.send_message_tool import _send_to_platform


RICH_CONTENT = (
    "## Results\n\n"
    "| Case | Status |\n"
    "|---|---|\n"
    "| standalone | ✅ |\n\n"
    "- [x] Rich Message"
)


class _RetryableRichError(Exception):
    retry_after = 23


@pytest.fixture
def rich_bot(monkeypatch):
    # Load the adapter while telegram.Bot is still the real PTB class; replacing
    # Bot before telegram.ext imports would break ExtBot's class definition.
    from plugins.platforms.telegram import adapter as _telegram_adapter  # noqa: F401
    import telegram
    from gateway.platforms import base

    bot = MagicMock()
    bot.do_api_request = AsyncMock(return_value={"message_id": 321})
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=1))
    bot.send_photo = AsyncMock(return_value=SimpleNamespace(message_id=9))
    bot.send_video = AsyncMock(return_value=SimpleNamespace(message_id=10))
    bot.send_voice = AsyncMock(return_value=SimpleNamespace(message_id=11))
    bot.send_audio = AsyncMock(return_value=SimpleNamespace(message_id=12))
    bot.send_document = AsyncMock(return_value=SimpleNamespace(message_id=13))

    monkeypatch.setattr(telegram, "Bot", lambda token, **kwargs: bot)
    monkeypatch.setattr(base, "resolve_proxy_url", lambda *args, **kwargs: None)
    return bot


@pytest.mark.asyncio
async def test_configured_standalone_telegram_send_uses_rich_message(rich_bot):
    pconfig = SimpleNamespace(
        enabled=True,
        token="fake-token",
        extra={"rich_messages": True},
    )

    result = await _send_to_platform(
        Platform.TELEGRAM,
        pconfig,
        "12345",
        RICH_CONTENT,
    )

    assert result["success"] is True
    assert result["message_id"] == "321"
    assert result["chat_id"] == "12345"
    assert isinstance(result["chat_id"], str)
    rich_bot.do_api_request.assert_awaited_once()
    call = rich_bot.do_api_request.await_args
    assert call.args[0] == "sendRichMessage"
    assert call.kwargs["api_kwargs"]["rich_message"]["markdown"] == RICH_CONTENT
    rich_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_disabled_rich_messages_keeps_legacy_delivery(rich_bot):
    pconfig = SimpleNamespace(
        enabled=True,
        token="fake-token",
        extra={"rich_messages": False},
    )

    result = await _send_to_platform(
        Platform.TELEGRAM, pconfig, "12345", RICH_CONTENT
    )

    assert result["message_id"] == "1"
    rich_bot.do_api_request.assert_not_called()
    rich_bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_rich_enabled_ordinary_text_stays_on_legacy_path(rich_bot):
    pconfig = SimpleNamespace(
        enabled=True,
        token="fake-token",
        extra={"rich_messages": True},
    )

    result = await _send_to_platform(
        Platform.TELEGRAM, pconfig, "12345", "Ordinary **Markdown** text"
    )

    assert result["message_id"] == "1"
    rich_bot.do_api_request.assert_not_called()
    rich_bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_permanent_rich_rejection_falls_back_to_legacy(rich_bot):
    rich_bot.do_api_request.side_effect = BadRequest("Bad rich message")
    pconfig = SimpleNamespace(
        enabled=True,
        token="fake-token",
        extra={"rich_messages": True},
    )

    result = await _send_to_platform(
        Platform.TELEGRAM, pconfig, "12345", RICH_CONTENT
    )

    assert result["message_id"] == "1"
    rich_bot.do_api_request.assert_awaited_once()
    rich_bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_transient_rich_failure_does_not_legacy_resend(rich_bot):
    rich_bot.do_api_request.side_effect = NetworkError("connection dropped")
    pconfig = SimpleNamespace(
        enabled=True,
        token="fake-token",
        extra={"rich_messages": True},
    )

    result = await _send_to_platform(
        Platform.TELEGRAM, pconfig, "12345", RICH_CONTENT
    )

    assert "error" in result
    assert result["retryable"] is True
    rich_bot.do_api_request.assert_awaited_once()
    rich_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_rich_message_preserves_forum_thread_routing(rich_bot):
    pconfig = SimpleNamespace(
        enabled=True,
        token="fake-token",
        extra={"rich_messages": True},
    )

    await _send_to_platform(
        Platform.TELEGRAM,
        pconfig,
        "-1001234567890",
        RICH_CONTENT,
        thread_id="17585",
    )

    payload = rich_bot.do_api_request.await_args.kwargs["api_kwargs"]
    assert payload["message_thread_id"] == 17585


@pytest.mark.asyncio
async def test_media_caption_preserves_legacy_media_delivery(rich_bot, tmp_path):
    image = tmp_path / "chart.png"
    image.write_bytes(b"not-a-real-png-but-sufficient-for-mocked-upload")
    pconfig = SimpleNamespace(
        enabled=True,
        token="fake-token",
        extra={"rich_messages": True},
    )

    result = await _send_to_platform(
        Platform.TELEGRAM,
        pconfig,
        "12345",
        RICH_CONTENT,
        media_files=[(str(image), False)],
    )

    assert result["message_id"] == "9"
    rich_bot.do_api_request.assert_not_called()
    rich_bot.send_photo.assert_awaited_once()
    assert rich_bot.send_photo.await_args.kwargs["caption"]


@pytest.mark.asyncio
async def test_plugin_standalone_sender_honors_rich_config(rich_bot):
    pconfig = SimpleNamespace(
        enabled=True,
        token="fake-token",
        extra={"rich_messages": True},
    )

    result = await _standalone_send(pconfig, "12345", RICH_CONTENT)

    assert result["message_id"] == "321"
    rich_bot.do_api_request.assert_awaited_once()
    rich_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_string_false_rich_config_keeps_legacy_delivery(rich_bot):
    pconfig = SimpleNamespace(
        enabled=True,
        token="fake-token",
        extra={"rich_messages": "false"},
    )

    result = await _send_to_platform(
        Platform.TELEGRAM, pconfig, "12345", RICH_CONTENT
    )

    assert result["message_id"] == "1"
    rich_bot.do_api_request.assert_not_called()
    rich_bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_plugin_standalone_sender_respects_string_false(rich_bot):
    pconfig = SimpleNamespace(
        enabled=True,
        token="fake-token",
        extra={"rich_messages": "false"},
    )

    result = await _standalone_send(pconfig, "12345", RICH_CONTENT)

    assert result["message_id"] == "1"
    rich_bot.do_api_request.assert_not_called()
    rich_bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_transient_rich_failure_preserves_retry_after(rich_bot):
    rich_bot.do_api_request.side_effect = _RetryableRichError("retry later")
    pconfig = SimpleNamespace(
        enabled=True,
        token="fake-token",
        extra={"rich_messages": True},
    )

    result = await _send_to_platform(
        Platform.TELEGRAM, pconfig, "12345", RICH_CONTENT
    )

    assert result["retryable"] is True
    assert result["retry_after"] == 23
    rich_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_rich_message_omits_general_topic_thread_id(rich_bot):
    pconfig = SimpleNamespace(
        enabled=True,
        token="fake-token",
        extra={"rich_messages": True},
    )

    await _send_to_platform(
        Platform.TELEGRAM,
        pconfig,
        "-1001234567890",
        RICH_CONTENT,
        thread_id="1",
    )

    payload = rich_bot.do_api_request.await_args.kwargs["api_kwargs"]
    assert "message_thread_id" not in payload


@pytest.mark.asyncio
async def test_rich_message_preserves_disabled_link_previews(rich_bot):
    pconfig = SimpleNamespace(
        enabled=True,
        token="fake-token",
        extra={"rich_messages": True, "disable_link_previews": True},
    )

    await _send_to_platform(
        Platform.TELEGRAM, pconfig, "12345", RICH_CONTENT
    )

    payload = rich_bot.do_api_request.await_args.kwargs["api_kwargs"]
    assert payload["link_preview_options"] == {"is_disabled": True}
