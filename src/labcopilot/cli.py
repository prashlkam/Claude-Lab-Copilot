"""Command-line interface.

    labcopilot guide URL            # explained step-by-step guide
    labcopilot chat URL             # interactive troubleshooting while you work
    labcopilot ask URL "question"   # one-off question
    labcopilot show URL             # just print the extracted lab text (no API call)

Every command also accepts --file PATH or --stdin instead of a URL, which is the way
to go when the lab sits behind a login.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .core import ChatSession, ask, make_guide
from .fetch import FetchError, LabDocument, load
from .llm import LLMError, anthropic_completer, model_name


def _add_source_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("url", nargs="?", help="Lab page URL (http/https)")
    p.add_argument("--file", help="Read the lab from a saved .html/.txt/.md file instead")
    p.add_argument("--stdin", action="store_true", help="Read the lab text from stdin")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="labcopilot",
        description="Understand hands-on labs faster. You run the steps; the copilot explains them.",
    )
    parser.add_argument("--version", action="version", version=f"labcopilot {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("guide", help="Generate an explained step-by-step guide")
    _add_source_args(g)
    g.add_argument("-o", "--output", help="Also save the guide to this Markdown file")
    g.add_argument("--focus", help="Topic to emphasise, e.g. 'IAM permissions'")

    c = sub.add_parser("chat", help="Interactive help while you work through the lab")
    _add_source_args(c)

    a = sub.add_parser("ask", help="Ask one question about the lab")
    _add_source_args(a)
    a.add_argument("question", nargs="?", help="Your question (or use -q)")
    a.add_argument("-q", "--q", dest="question_opt", help="Your question")

    s = sub.add_parser("show", help="Print the extracted lab text (no API call)")
    _add_source_args(s)
    return parser


def _load(args: argparse.Namespace) -> LabDocument:
    if args.stdin and (args.url or args.file):
        raise FetchError("Use only one of URL, --file or --stdin.")
    doc = load(source=args.url, file=args.file, use_stdin=args.stdin)
    if doc.warning:
        print(f"warning: {doc.warning}", file=sys.stderr)
    if doc.truncated:
        print("warning: lab text was long and has been truncated.", file=sys.stderr)
    if not doc.text.strip():
        raise FetchError("No lab text could be extracted.")
    return doc


def _stream(chunk: str) -> None:
    sys.stdout.write(chunk)
    sys.stdout.flush()


CHAT_HELP = """\
Commands: /guide  print the full guide   /paste  send multi-line text (end with a line 'EOF')
          /reset  clear the conversation  /help   this help   /quit  leave
Tip: paste the exact error message or command output when something fails."""


def _read_paste() -> str:
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "EOF":
            break
        lines.append(line)
    return "\n".join(lines)


def _run_chat(doc: LabDocument, complete) -> int:
    session = ChatSession(doc=doc, complete=complete)
    print(f"Lab Copilot ({model_name()}) — {doc.title}")
    print("You run the steps; I explain and help debug. /help for commands.\n")
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not user:
            continue
        if user in {"/quit", "/exit", "/q"}:
            return 0
        if user == "/help":
            print(CHAT_HELP)
            continue
        if user == "/reset":
            session.reset()
            print("(conversation cleared)")
            continue
        if user == "/paste":
            print("(paste now; finish with a line containing only EOF)")
            user = _read_paste().strip()
            if not user:
                continue
        if user == "/guide":
            user = "Give me the full step-by-step guide for this lab."
        try:
            print()
            session.send(user, on_text=_stream)
            print("\n")
        except LLMError as exc:
            print(f"\nerror: {exc}\n", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        doc = _load(args)
        if args.command == "show":
            print(f"# {doc.title}\n\n{doc.text}")
            return 0

        complete = anthropic_completer()
        if args.command == "guide":
            guide = make_guide(doc, complete, on_text=_stream, focus=args.focus)
            print()
            if args.output:
                Path(args.output).write_text(guide + "\n", encoding="utf-8")
                print(f"\nSaved to {args.output}", file=sys.stderr)
            return 0
        if args.command == "ask":
            question = args.question_opt or args.question
            if not question:
                print("error: give a question, e.g. labcopilot ask URL \"why did step 3 fail?\"",
                      file=sys.stderr)
                return 2
            ask(doc, question, complete, on_text=_stream)
            print()
            return 0
        if args.command == "chat":
            return _run_chat(doc, complete)
    except (FetchError, LLMError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
