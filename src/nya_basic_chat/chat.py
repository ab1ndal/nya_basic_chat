# Location: src/nya_basic_chat/chat.py
from nya_basic_chat.llm_client import chat as _chat


def _build_call_kwargs(content, system, model, max_completion_tokens, verbosity, reasoning):
    """Build kwargs for chat_once and chat_stream."""
    kwargs = dict(
        content=content,
        system=system,
        max_completion_tokens=max_completion_tokens,
        model=model,
    )
    # Requires llm_client.chat_once and chat_stream to accept these optional kwargs
    if verbosity:
        kwargs["verbosity"] = verbosity
    if reasoning:
        kwargs["reasoning_effort"] = reasoning
    return kwargs


def run_once(**kwargs):
    """Run chat_once with kwargs."""
    return _chat(**kwargs, streaming=False)


def run_stream(**kwargs):
    """Run chat_stream with kwargs."""
    return _chat(**kwargs, streaming=True)
