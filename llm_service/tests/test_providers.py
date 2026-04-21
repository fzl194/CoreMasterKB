import pytest

pytestmark = pytest.mark.asyncio


async def test_mock_provider_returns_preset_response():
    from llm_service.providers.mock import MockProvider

    provider = MockProvider(
        responses=[{"choices": [{"message": {"content": '{"answer": 42}'}}]}]
    )
    resp = await provider.complete(
        messages=[{"role": "user", "content": "test"}],
        params={},
    )
    assert resp.output_text == '{"answer": 42}'
    assert provider.provider_name == "mock"


async def test_mock_provider_cycles_responses():
    from llm_service.providers.mock import MockProvider

    provider = MockProvider(
        responses=[
            {"choices": [{"message": {"content": "first"}}]},
            {"choices": [{"message": {"content": "second"}}]},
        ]
    )
    r1 = await provider.complete(messages=[], params={})
    r2 = await provider.complete(messages=[], params={})
    assert r1.output_text == "first"
    assert r2.output_text == "second"


async def test_mock_provider_can_raise_error():
    from llm_service.providers.mock import MockProvider
    from llm_service.providers.base import ProviderError

    provider = MockProvider(error=ProviderError("timeout", "connection timed out"))
    with pytest.raises(ProviderError):
        await provider.complete(messages=[], params={})


async def test_openai_compatible_builds_correct_url():
    from llm_service.providers.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        base_url="http://localhost:11434/v1",
        api_key="test-key",
        model="llama3",
    )
    assert provider.provider_name == "openai_compatible"
    assert provider.default_model == "llama3"
