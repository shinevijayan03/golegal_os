"""
GoLegal LLM Gateway

A thin, provider-agnostic wrapper around the Anthropic Messages API used by
every agent in the platform. When no API key is configured the gateway reports
`available = False` and callers fall back to deterministic rule-based logic,
so the whole application (and its test suite) works offline.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config import settings

log = logging.getLogger("golegal.ai")


class LLMUnavailableError(RuntimeError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    input: Dict[str, Any]


@dataclass
class LLMResponse:
    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0
    raw_content: Any = None  # provider content blocks, replayed verbatim into history
    refusal_category: Optional[str] = None

    @property
    def wants_tools(self) -> bool:
        return self.stop_reason == "tool_use" and bool(self.tool_calls)


class LLMClient:
    """Interface. `complete` returns an LLMResponse; `available` says whether calls will work."""

    available: bool = False
    model: str = "rule-based"

    def complete(self, system: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None,
                 max_tokens: Optional[int] = None) -> LLMResponse:
        raise LLMUnavailableError("No language model configured. Set ANTHROPIC_API_KEY to enable AI features.")


class NullLLMClient(LLMClient):
    available = False
    model = "rule-based"


class AnthropicLLMClient(LLMClient):
    """Claude via the official SDK. Uses adaptive thinking (default on Opus 5) and a configurable effort."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        import anthropic  # imported lazily so the app runs without the SDK installed

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key or settings.anthropic_api_key)
        self.model = model or settings.llm_model
        self.available = True

    def complete(self, system: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None,
                 max_tokens: Optional[int] = None) -> LLMResponse:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or settings.llm_max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "output_config": {"effort": settings.llm_effort},
        }
        if tools:
            kwargs["tools"] = tools
        try:
            response = self._client.messages.create(**kwargs)
        except self._anthropic.RateLimitError as exc:
            raise LLMUnavailableError("The AI service is rate limited right now. Try again shortly.") from exc
        except self._anthropic.APIStatusError as exc:
            raise LLMUnavailableError(f"The AI service returned an error ({exc.status_code}).") from exc
        except self._anthropic.APIConnectionError as exc:
            raise LLMUnavailableError("Could not reach the AI service. Check network connectivity.") from exc

        text_parts: List[str] = []
        tool_calls: List[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=dict(block.input)))
        refusal = None
        if response.stop_reason == "refusal" and getattr(response, "stop_details", None):
            refusal = getattr(response.stop_details, "category", None)
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text="\n".join(text_parts).strip(),
            tool_calls=tool_calls,
            stop_reason=response.stop_reason or "end_turn",
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            raw_content=response.content,
            refusal_category=refusal,
        )


_client_singleton: Optional[LLMClient] = None


def get_llm_client(force: Optional[LLMClient] = None) -> LLMClient:
    """Return the process-wide LLM client (Anthropic when configured, otherwise the null client)."""
    global _client_singleton
    if force is not None:
        _client_singleton = force
        return force
    if _client_singleton is None:
        if settings.llm_available:
            try:
                _client_singleton = AnthropicLLMClient()
            except Exception as exc:  # SDK missing or misconfigured
                log.warning("Anthropic client unavailable, using rule-based fallback: %s", exc)
                _client_singleton = NullLLMClient()
        else:
            _client_singleton = NullLLMClient()
    return _client_singleton


def reset_llm_client() -> None:
    global _client_singleton
    _client_singleton = None


def extract_json(text: str) -> Optional[Any]:
    """Best-effort JSON extraction from a model reply (handles code fences and prose)."""
    if not text:
        return None
    candidate = text.strip()
    if "```" in candidate:
        parts = candidate.split("```")
        for part in parts[1::2]:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except ValueError:
                continue
    openers = [(candidate.find(o), o, c) for o, c in (("{", "}"), ("[", "]")) if candidate.find(o) != -1]
    for start, opener, closer in sorted(openers):
        end = candidate.rfind(closer)
        if end > start:
            try:
                return json.loads(candidate[start:end + 1])
            except ValueError:
                pass
    return None
