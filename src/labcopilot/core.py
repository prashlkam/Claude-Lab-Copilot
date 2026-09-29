"""Guide generation, one-shot questions and the troubleshooting chat session."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterator

from . import prompts
from .fetch import LabDocument
from .llm import Completer, Message

MAX_HISTORY_MESSAGES = 30  # keep chats bounded; oldest turns are dropped first


def _join(chunks: Iterator[str], on_text: Callable[[str], None] | None) -> str:
    parts: list[str] = []
    for chunk in chunks:
        parts.append(chunk)
        if on_text:
            on_text(chunk)
    return "".join(parts)


def make_guide(doc: LabDocument, complete: Completer,
               on_text: Callable[[str], None] | None = None, focus: str | None = None) -> str:
    """Turn a lab into an explained step-by-step study guide (Markdown)."""
    system = prompts.with_lab(prompts.GUIDE, doc.title, doc.text)
    request = "Write the study guide for this lab."
    if focus:
        request += f" Pay particular attention to: {focus}"
    return _join(iter(complete(system, [{"role": "user", "content": request}])), on_text)


def ask(doc: LabDocument, question: str, complete: Completer,
        on_text: Callable[[str], None] | None = None) -> str:
    system = prompts.with_lab(prompts.ASK, doc.title, doc.text)
    return _join(iter(complete(system, [{"role": "user", "content": question}])), on_text)


@dataclass
class ChatSession:
    doc: LabDocument
    complete: Completer
    history: list[Message] = field(default_factory=list)

    @property
    def system(self) -> str:
        return prompts.with_lab(prompts.CHAT, self.doc.title, self.doc.text)

    def send(self, user_text: str, on_text: Callable[[str], None] | None = None) -> str:
        self.history.append({"role": "user", "content": user_text})
        window = self._window()
        try:
            reply = _join(iter(self.complete(self.system, window)), on_text)
        except Exception:
            self.history.pop()  # don't keep a turn that never got an answer
            raise
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def _window(self) -> list[Message]:
        window = self.history[-MAX_HISTORY_MESSAGES:]
        # The API requires the first message to be from the user.
        while window and window[0]["role"] != "user":
            window = window[1:]
        return window

    def reset(self) -> None:
        self.history.clear()
