import pytest
from pydantic import ValidationError

from schemas.llm_providers import LLMProviderChatRequest


def test_chat_request_accepts_legacy_message_only():
    body = LLMProviderChatRequest(
        provider_name="anthropic",
        message="hello",
    )

    compiled = body.build_messages()
    assert compiled[-1]["role"] == "user"
    assert compiled[-1]["content"] == "hello"
    assert body.latest_user_message() == "hello"


def test_chat_request_accepts_messages_only():
    body = LLMProviderChatRequest(
        provider_name="anthropic",
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "summarize"},
        ],
    )

    compiled = body.build_messages()
    assert len(compiled) == 3
    assert body.latest_user_message() == "summarize"


def test_chat_request_rejects_missing_message_and_messages():
    with pytest.raises(ValidationError):
        LLMProviderChatRequest(provider_name="anthropic")


def test_chat_request_applies_memory_window_strategy():
    body = LLMProviderChatRequest(
        provider_name="anthropic",
        system_prompt="You are concise.",
        short_term_memory=[
            {"role": "user", "content": "m1"},
            {"role": "assistant", "content": "m2"},
        ],
        messages=[
            {"role": "user", "content": "m3"},
            {"role": "assistant", "content": "m4"},
            {"role": "user", "content": "m5"},
        ],
        memory_strategy="window",
        memory_window_size=2,
    )

    compiled = body.build_messages()
    assert compiled[0] == {"role": "system", "content": "You are concise."}
    assert [m["content"] for m in compiled[1:]] == ["m4", "m5"]


def test_chat_request_rejects_out_of_range_temperature():
    with pytest.raises(ValidationError):
        LLMProviderChatRequest(
            provider_name="anthropic",
            message="hello",
            temperature=3.2,
        )
