"""Thin wrapper over the Anthropic SDK so the rest of the code (and tests) stay simple."""

from __future__ import annotations

import os
from typing import Callable, Iterable

DEFAULT_MODEL = "claude-sonnet-5-5"

Message = dict  # {"role": "user"|"assistant", "content": str}
# A completer takes (system, messages) and yields text chunks.
Completer = Callable[[str, list[Message]], Iterable[str]]


class LLMError(RuntimeError):
    pass


def model_name() -> str:
    return os.environ.get("LABCOPILOT_MODEL", DEFAULT_MODEL)


def anthropic_completer(max_tokens: int = 4096) -> Completer:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise LLMError("ANTHROPIC_API_KEY is not set. Export it and try again.")

    import anthropic

    client = anthropic.Anthropic()

    def complete(system: str, messages: list[Message]) -> Iterable[str]:
        try:
            with client.messages.stream(
                model=model_name(),
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc

    return complete
