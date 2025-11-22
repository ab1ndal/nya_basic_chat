# Location: src/nya_basic_chat/llm_client.py

from __future__ import annotations
import os
import json
from typing import Optional, Dict, Any, Sequence, List
from dataclasses import dataclass
from dotenv import load_dotenv
from openai import OpenAI
from nya_basic_chat.helpers import _format_history
from nya_basic_chat.web import fetch_url, tavily_search
import streamlit as st
import logging
import openai

load_dotenv()

SUPPORTED_MODELS = {"gpt-5", "gpt-5-mini", "gpt-5-nano"}
DEFAULT_HISTORY_TURNS = 10
DEFAULT_HISTORY_CHARS = 2000

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


def _tool_defs() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "web_fetch",
                "description": "Fetch and clean visible text from a web page for the given URL",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web and return a short list of results",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "k": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                    "required": ["query"],
                },
            },
        },
    ]


def _exec_tool(name: str, arguments_json: str) -> str:
    try:
        args = json.loads(arguments_json or "{}")
    except Exception:
        args = {}
    if name == "web_fetch":
        url = args.get("url", "")
        page = fetch_url(url)
        return json.dumps({"url": page.url, "title": page.title, "text": page.text})
    if name == "web_search":
        q = args.get("query", "")
        k = int(args.get("k") or 5)
        results = tavily_search(q, k=k, api_key=get_secret("TAVILY_API_KEY"))
        return json.dumps({"results": results})
    return json.dumps({"error": f"unknown tool {name}"})


def _build_params(
    *,
    model: str,
    messages: Sequence[Dict[str, Any]],
    stream: bool = False,
    max_completion_tokens: int = 512,
    verbosity: Optional[str] = None,  # "low" | "medium" | "high"
    reasoning_effort: Optional[str] = None,  # "minimal" | "low" | "medium" | "high"
    stop: Optional[Sequence[str]] = None,
    tools: Optional[Sequence[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,  # "auto" or "none"
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
    if tools:
        params["tools"] = list(tools)
    if tool_choice:
        params["tool_choice"] = tool_choice
    return params


def _resolve_tools_until_ready(
    client: OpenAI,
    model: str,
    messages: List[Dict[str, Any]],
    max_completion_tokens: int,
    verbosity: Optional[str],
    reasoning_effort: Optional[str],
    stop: Optional[Sequence[str]],
    max_loops: int = 4,
) -> List[Dict[str, Any]]:
    tools = _tool_defs()
    for i in range(max_loops):
        tool_choice = None
        params = _build_params(
            model=model,
            messages=messages,
            stream=False,
            max_completion_tokens=max_completion_tokens,
            verbosity=verbosity,
            reasoning_effort=reasoning_effort,
            stop=stop,
            tools=tools,
            tool_choice=tool_choice or "auto",
        )
        try:
            resp = client.chat.completions.create(**params)
        except openai.RateLimitError as e:
            logger.error("Rate limit hit in _resolve_tools_until_ready", exc_info=True)
            logger.error("Error details: %s", getattr(e, "__dict__", {}))
            st.error("⚠️ OpenAI rate limit reached. Please wait a moment and try again.")
            return messages + [
                {"role": "assistant", "content": "Rate limit reached. Try again later."}
            ]
        except Exception as e:
            logger.error("Unexpected error in _resolve_tools_until_ready", exc_info=True)
            st.error(f"⚠️ Unexpected error: {str(e)}")
            return messages
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)

        if not tool_calls:
            if msg.content:
                messages.append({"role": "assistant", "content": msg.content})
            return messages

        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [tc.model_dump() for tc in tool_calls],
            }
        )

        for tc in tool_calls:
            name = tc.function.name
            arguments_json = tc.function.arguments
            result_json = _exec_tool(name, arguments_json)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": result_json,
                }
            )

    messages.append(
        {"role": "assistant", "content": "Tool loop limit reached. Proceeding with available data."}
    )
    return messages


def sanitize_for_openai(blocks):
    clean = []
    for b in blocks:
        if b["type"] == "text":
            clean.append({"type": "text", "text": b["text"]})
        elif b["type"] == "image_url":
            clean.append({"type": "image_url", "image_url": b["image_url"]})
    return clean


def chat(
    *,
    system: str = "You are a helpful assistant.",
    max_completion_tokens: int = 512,
    model: Optional[str] = None,
    content: Optional[Sequence[Dict[str, Any]]] = None,
    verbosity: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    stop: Optional[Sequence[str]] = None,
    streaming: bool = True,
) -> str:
    """Calls LLM with the given prompt and attachments."""
    cfg = _cfg()
    client = _client()

    history_block = _format_history(
        st.session_state.get("history", []),
        max_turns=DEFAULT_HISTORY_TURNS,
        max_chars=DEFAULT_HISTORY_CHARS,
    )

    # System Prompt:
    system = f"""
        {system}. 
        You are an assistant designed for professional engineering and technical tasks only. You should not provide help or generate output for personal use, entertainment, creative writing, emotional support, relationship advice, medical advice, legal advice, travel planning, personal finance, or any unrelated personal matter. If a request falls outside professional or technical scope, politely decline.
        Use math formatted in LaTeX when needed. Inline expressions should appear inside dollar signs and block expressions should appear inside double dollar signs.
        Use only the current conversation as context. Do not assume or create information about earlier messages.
        Do not guess or speculate. If you cannot verify information or if the answer is not clearly supported by reliable sources, respond with “I do not know the response to the question”.
        Provide a source for factual claims. Acceptable sources include reputable textbooks, peer reviewed papers, authoritative technical standards, or widely recognized engineering references. Never fabricate citations.
        Keep responses concise, professional, and technical.
    """

    print("---------------")
    print(sanitize_for_openai(content) + [{"type": "text", "text": history_block}])
    print("---------------")

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": sanitize_for_openai(content) + [{"type": "text", "text": history_block}],
        },
    ]
    # Resolve any tool requests first
    messages = _resolve_tools_until_ready(
        client=client,
        model=model or cfg.model,
        messages=messages,
        max_completion_tokens=max_completion_tokens,
        verbosity=verbosity,
        reasoning_effort=reasoning_effort,
        stop=stop,
    )
    # Final non streaming response with tools disabled, to avoid new tool calls
    params = _build_params(
        model=model or cfg.model,
        messages=messages,
        stream=streaming,
        max_completion_tokens=max_completion_tokens,
        verbosity=verbosity,
        reasoning_effort=reasoning_effort,
        stop=stop,
    )
    try:
        if streaming:
            resp = client.chat.completions.create(**params)
            for event in resp:
                delta = event.choices[0].delta.content
                if delta:
                    yield delta
        else:
            resp = client.chat.completions.create(**params)
            return resp.choices[0].message.content or ""
    except openai.RateLimitError as e:
        logger.error("Rate limit hit in chat()", exc_info=True)
        logger.error("Error details: %s", getattr(e, "__dict__", {}))
        st.error(f"⚠️ OpenAI rate limit reached. {str(e)}")
        return
    except Exception as e:
        logger.error("Unexpected error in chat()", exc_info=True)
        st.error(f"⚠️ Unexpected error: {str(e)}")
        return
