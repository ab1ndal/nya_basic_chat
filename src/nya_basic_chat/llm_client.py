from __future__ import annotations
import os
from typing import Iterable, Optional, Dict, Any, Sequence
from dataclasses import dataclass
from dotenv import load_dotenv
from openai import OpenAI
from helpers import _build_user_content
import streamlit as st

load_dotenv()

SUPPORTED_MODELS = {"gpt-5", "gpt-5-mini", "gpt-5-nano"}


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    model: str
    base_url: Optional[str] = None


def get_secret(key, default=None):
    try:
        return st.secrets.get(key) or os.getenv(key) or default
    except Exception:
        return os.getenv(key) or default


def _cfg() -> LLMConfig:
    api_key = get_secret("OPENAI_API_KEY").strip()
    model = get_secret("OPENAI_MODEL", "gpt-5-mini").strip()
    base_url = get_secret("OPENAI_BASE_URL", "").strip() or None
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Put it in your .env")
    if model not in SUPPORTED_MODELS:
        raise RuntimeError(
            f"Unsupported model: {model}. OPENAI_MODEL must be one of {sorted(SUPPORTED_MODELS)}"
        )
    return LLMConfig(api_key=api_key, model=model, base_url=base_url)


def _client() -> OpenAI:
    cfg = _cfg()
    kwargs = {"api_key": cfg.api_key}
    if cfg.base_url:
        kwargs["base_url"] = cfg.base_url
    return OpenAI(**kwargs)


def _build_params(
    *,
    model: str,
    messages: Sequence[Dict[str, Any]],
    stream: bool = False,
    max_completion_tokens: int = 512,
    verbosity: Optional[str] = None,  # "low" | "medium" | "high"
    reasoning_effort: Optional[str] = None,  # "minimal" | "low" | "medium" | "high"
    stop: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "model": model,
        "messages": list(messages),
        "stream": stream,
        "max_completion_tokens": max_completion_tokens,
    }
    if verbosity is not None:
        params["verbosity"] = verbosity
    if reasoning_effort is not None:
        params["reasoning_effort"] = reasoning_effort
    if stop:
        params["stop"] = list(stop)
    return params


def chat_once(
    prompt: str,
    *,
    system: str = "You are a helpful assistant.",
    max_completion_tokens: int = 512,
    model: Optional[str] = None,
    attachments: Optional[Sequence[Dict[str, Any]]] = None,
    pdf_mode: str = "text",  # "image" or "text"
    verbosity: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    stop: Optional[Sequence[str]] = None,
) -> str:
    """One-shot non-streaming call; returns the full text."""
    cfg = _cfg()
    client = _client()
    content = _build_user_content(prompt, attachments, pdf_mode=pdf_mode)
    params = _build_params(
        model=model or cfg.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        max_completion_tokens=max_completion_tokens,
        verbosity=verbosity,
        reasoning_effort=reasoning_effort,
        stop=stop,
        stream=False,
    )
    resp = client.chat.completions.create(**params)
    return resp.choices[0].message.content or ""


def chat_stream(
    prompt: str,
    *,
    system: str = "You are a helpful assistant.",
    max_completion_tokens: int = 512,
    model: Optional[str] = None,
    attachments: Optional[Sequence[Dict[str, Any]]] = None,
    pdf_mode: str = "text",  # "image" or "text"
    verbosity: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    stop: Optional[Sequence[str]] = None,
) -> Iterable[str]:
    """Streaming generator yielding text deltas (great for Streamlit)."""
    cfg = _cfg()
    client = _client()
    content = _build_user_content(prompt, attachments, pdf_mode=pdf_mode)
    params = _build_params(
        model=model or cfg.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        max_completion_tokens=max_completion_tokens,
        verbosity=verbosity,
        reasoning_effort=reasoning_effort,
        stop=stop,
        stream=True,
    )
    stream = client.chat.completions.create(**params)
    for event in stream:
        delta = event.choices[0].delta.content
        if delta:
            yield delta
