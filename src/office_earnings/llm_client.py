from __future__ import annotations
import os
from typing import Iterable, Optional
from dataclasses import dataclass
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    model: str
    base_url: Optional[str] = None


def _cfg() -> LLMConfig:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Put it in your .env")
    return LLMConfig(api_key=api_key, model=model, base_url=base_url)


def _client() -> OpenAI:
    cfg = _cfg()
    kwargs = {"api_key": cfg.api_key}
    if cfg.base_url:
        kwargs["base_url"] = cfg.base_url
    return OpenAI(**kwargs)


def chat_once(
    prompt: str,
    *,
    system: str = "You are a helpful assistant.",
    temperature: float = 0.2,
    max_tokens: int = 512,
    model: Optional[str] = None,
) -> str:
    """One-shot non-streaming call; returns the full text."""
    cfg = _cfg()
    client = _client()
    resp = client.chat.completions.create(
        model=model or cfg.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


def chat_stream(
    prompt: str,
    *,
    system: str = "You are a helpful assistant.",
    temperature: float = 0.2,
    max_tokens: int = 512,
    model: Optional[str] = None,
) -> Iterable[str]:
    """Streaming generator yielding text deltas (great for Streamlit)."""
    cfg = _cfg()
    client = _client()
    stream = client.chat.completions.create(
        model=model or cfg.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    for event in stream:
        delta = event.choices[0].delta.content
        if delta:
            yield delta
