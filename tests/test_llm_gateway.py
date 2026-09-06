"""
Tests for the LLM gateway seam (TC-LLM)

The Anthropic SDK is exercised through a stub so response parsing, usage
accounting and error mapping are verified without a network call or an API key.
"""
import sys
import types

import pytest

from ai.llm import AnthropicLLMClient, LLMUnavailableError, NullLLMClient, get_llm_client, reset_llm_client


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Usage:
    def __init__(self, i, o):
        self.input_tokens, self.output_tokens = i, o


class _StubMessages:
    def __init__(self, response=None, error=None):
        self._response, self._error = response, error
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._error:
            raise self._error
        return self._response


class _StubSDKClient:
    def __init__(self, response=None, error=None):
        self.messages = _StubMessages(response, error)


def _install_stub_sdk(monkeypatch, response=None, error=None):
    """Install a fake `anthropic` module so AnthropicLLMClient can be constructed offline."""
    stub = types.ModuleType("anthropic")

    class RateLimitError(Exception):
        pass

    class APIStatusError(Exception):
        def __init__(self, msg="", status_code=500):
            super().__init__(msg)
            self.status_code = status_code

    class APIConnectionError(Exception):
        pass

    sdk_client = _StubSDKClient(response, error)
    stub.Anthropic = lambda **kw: sdk_client
    stub.RateLimitError = RateLimitError
    stub.APIStatusError = APIStatusError
    stub.APIConnectionError = APIConnectionError
    monkeypatch.setitem(sys.modules, "anthropic", stub)
    return stub, sdk_client


class TestAnthropicGateway:
    def test_parses_text_tool_calls_and_usage(self, monkeypatch):
        response = _Block(
            content=[_Block(type="text", text="Karnataka duty is ₹100."),
                     _Block(type="tool_use", id="tu_9", name="calculate_stamp_duty", input={"state_code": "KA"})],
            stop_reason="tool_use", usage=_Usage(140, 22), stop_details=None,
        )
        _, sdk = _install_stub_sdk(monkeypatch, response=response)
        client = AnthropicLLMClient(api_key="test-key", model="claude-opus-5")
        assert client.available is True

        out = client.complete("system prompt", [{"role": "user", "content": "hi"}],
                              tools=[{"name": "calculate_stamp_duty", "description": "", "input_schema": {}}])
        assert out.text == "Karnataka duty is ₹100."
        assert out.wants_tools and out.tool_calls[0].name == "calculate_stamp_duty"
        assert out.tool_calls[0].input == {"state_code": "KA"}
        assert (out.input_tokens, out.output_tokens) == (140, 22)

        sent = sdk.messages.last_kwargs
        assert sent["model"] == "claude-opus-5"
        assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}  # prefix caching enabled
        assert "effort" in sent["output_config"]
        assert sent["tools"]

    def test_refusal_is_surfaced(self, monkeypatch):
        response = _Block(content=[], stop_reason="refusal", usage=_Usage(10, 0),
                          stop_details=_Block(category="cyber"))
        _install_stub_sdk(monkeypatch, response=response)
        out = AnthropicLLMClient(api_key="k").complete("s", [{"role": "user", "content": "x"}])
        assert out.stop_reason == "refusal" and out.refusal_category == "cyber"
        assert out.wants_tools is False

    @pytest.mark.parametrize("err_name,message", [
        ("RateLimitError", "rate limited"),
        ("APIConnectionError", "Could not reach"),
    ])
    def test_errors_map_to_llm_unavailable(self, monkeypatch, err_name, message):
        stub, sdk = _install_stub_sdk(monkeypatch)
        client = AnthropicLLMClient(api_key="k")
        sdk.messages._error = getattr(stub, err_name)("boom")
        with pytest.raises(LLMUnavailableError) as exc:
            client.complete("s", [{"role": "user", "content": "x"}])
        assert message.lower() in str(exc.value).lower()

    def test_api_status_error_reports_code(self, monkeypatch):
        stub, sdk = _install_stub_sdk(monkeypatch)
        client = AnthropicLLMClient(api_key="k")
        sdk.messages._error = stub.APIStatusError("bad", status_code=529)
        with pytest.raises(LLMUnavailableError) as exc:
            client.complete("s", [{"role": "user", "content": "x"}])
        assert "529" in str(exc.value)


class TestClientSelection:
    def test_null_client_without_api_key(self, monkeypatch):
        monkeypatch.setattr("ai.llm.settings", type("S", (), {"llm_available": False, "llm_model": "claude-opus-5"})())
        reset_llm_client()
        client = get_llm_client()
        assert isinstance(client, NullLLMClient) and client.available is False
        with pytest.raises(LLMUnavailableError):
            client.complete("s", [])

    def test_forced_client_is_returned(self):
        forced = NullLLMClient()
        assert get_llm_client(force=forced) is forced
        assert get_llm_client() is forced
