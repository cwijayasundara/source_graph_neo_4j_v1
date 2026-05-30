"""Gemini client exposing an Anthropic-shaped messages API.

The BRD Generator/Judge and the semantic enricher were written against the
Anthropic SDK call site ``client.messages.create(model=, max_tokens=, system=, messages=)``
returning ``response.content[0].text`` and ``response.usage.input_tokens``.

This module provides a thin wrapper around Google's Gemini REST endpoint with
the same surface, so callers do not need provider-specific branching.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv


DEFAULT_MODEL = "gemini-3.5-flash"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"


class _ContentBlock:
    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


class _Usage:
    __slots__ = ("input_tokens", "output_tokens",
                 "cache_read_input_tokens", "cache_creation_input_tokens")

    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        # Gemini context caching is not wired up here; expose zeros so callers
        # that read these attributes (BRD Generator) do not need to special-case.
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0


class _Response:
    __slots__ = ("content", "usage")

    def __init__(self, text: str, usage: _Usage) -> None:
        self.content = [_ContentBlock(text)]
        self.usage = usage


class _MessagesNamespace:
    def __init__(self, client: "GeminiMessagesClient") -> None:
        self._client = client

    def create(self, *, model: str, max_tokens: int,
               messages: list[dict[str, Any]],
               system: str | None = None,
               temperature: float = 0.1,
               response_json: bool = True) -> _Response:
        return self._client._create(
            model=model, max_tokens=max_tokens, messages=messages,
            system=system, temperature=temperature, response_json=response_json,
        )


class GeminiMessagesClient:
    """Gemini REST client exposing an Anthropic-style ``.messages.create`` API.

    All BRD prompts ask the model to return raw JSON, so by default the request
    sets ``response_mime_type=application/json`` — this gives more reliable JSON
    than relying on prompt instructions alone.
    """

    def __init__(self, api_key: str | None = None,
                 model: str | None = None,
                 timeout: float = 60.0) -> None:
        load_dotenv()
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY", "")
        self.default_model = model or os.getenv("CODE_GRAPH_LLM_MODEL", DEFAULT_MODEL)
        self.timeout = timeout
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set")
        self.messages = _MessagesNamespace(self)

    def _create(self, *, model: str, max_tokens: int,
                messages: list[dict[str, Any]],
                system: str | None,
                temperature: float,
                response_json: bool) -> _Response:
        contents = [
            {"role": _map_role(m["role"]),
             "parts": [{"text": _stringify_content(m["content"])}]}
            for m in messages
        ]
        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if response_json:
            generation_config["responseMimeType"] = "application/json"
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        url = f"{GEMINI_ENDPOINT}/{model}:generateContent"
        with httpx.Client(timeout=self.timeout) as http:
            resp = http.post(url, params={"key": self.api_key}, json=payload)
            resp.raise_for_status()
            data = resp.json()

        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Gemini returned an unexpected response shape: {data}") from exc

        usage_md = data.get("usageMetadata") or {}
        usage = _Usage(
            input_tokens=int(usage_md.get("promptTokenCount", 0) or 0),
            output_tokens=int(usage_md.get("candidatesTokenCount", 0) or 0),
        )
        return _Response(text=text, usage=usage)


def _map_role(role: str) -> str:
    # Gemini accepts "user" and "model"; Anthropic uses "user" and "assistant".
    if role == "assistant":
        return "model"
    return role


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)
