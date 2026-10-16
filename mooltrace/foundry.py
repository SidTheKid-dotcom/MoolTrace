"""Optional Azure AI Foundry chat. The rewrite falls back if this is unset."""

from __future__ import annotations

import os
from typing import Any

import httpx

from mooltrace.clients import MoolTraceError


def _settings() -> tuple[str, str, str] | None:
    endpoint = (
        os.environ.get("AZURE_INFERENCE_ENDPOINT")
        or os.environ.get("AZURE_OPENAI_ENDPOINT")
        or ""
    ).strip()
    key = (
        os.environ.get("AZURE_INFERENCE_API_KEY")
        or os.environ.get("AZURE_OPENAI_API_KEY")
        or ""
    ).strip()
    model = (
        os.environ.get("AZURE_INFERENCE_MODEL")
        or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
        or ""
    ).strip()
    if not endpoint or not key or not model:
        return None
    return endpoint, key, model


def available() -> bool:
    return _settings() is not None


def complete(prompt: str, *, timeout_s: float = 20.0) -> str:
    """One chat completion. Never logs the key. Raises MoolTraceError on miss."""
    settings = _settings()
    if settings is None:
        raise MoolTraceError("Azure AI Foundry is not configured")
    endpoint, key, model = settings
    base = endpoint.rstrip("/")
    azure_openai = "openai.azure.com" in base
    if azure_openai:
        url = f"{base}/openai/deployments/{model}/chat/completions?api-version=2024-10-21"
        body: dict[str, Any] = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Rewrite a health-AI draft so it no longer cites flagged "
                        "pages or studies. Do not give medical advice. Do not call "
                        "an Expression of Concern a retraction."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 400,
            "temperature": 0,
        }
    else:
        url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
        body = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Rewrite a health-AI draft so it no longer cites flagged "
                        "pages or studies. Do not give medical advice. Do not call "
                        "an Expression of Concern a retraction."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 400,
            "temperature": 0,
        }
    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(
                url,
                headers={"api-key": key, "Content-Type": "application/json"},
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise MoolTraceError("Azure AI Foundry request failed") from exc
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise MoolTraceError("Azure AI Foundry returned no text") from exc
    if not isinstance(text, str) or not text.strip():
        raise MoolTraceError("Azure AI Foundry returned no text")
    return text.strip()
