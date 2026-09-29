"""Load lab instructions from a URL, a saved file, or stdin and reduce them to text.

Code blocks are preserved verbatim (fenced), because commands and configs are the
part of a lab you least want mangled.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag

MAX_CHARS = 60_000  # keep the prompt bounded; long labs get truncated with a note

_NOISE_TAGS = ["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"]
_BLOCK_TAGS = {"p", "div", "section", "article", "li", "ul", "ol", "table", "tr", "br",
               "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
_LOGIN_HINTS = re.compile(
    r"(sign in|log in|login|authenticate|enable javascript|access denied|single sign-on)", re.I
)


class FetchError(RuntimeError):
    pass


@dataclass
class LabDocument:
    source: str
    title: str
    text: str
    truncated: bool = False
    warning: str | None = None


def _render(node: Tag | NavigableString, out: list[str]) -> None:
    if isinstance(node, NavigableString):
        out.append(str(node))
        return
    name = node.name
    if name == "pre":
        out.append("\n```\n" + node.get_text().strip("\n") + "\n```\n")
        return
    if name == "code":
        out.append("`" + node.get_text() + "`")
        return
    if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        level = int(name[1])
        out.append("\n\n" + "#" * level + " " + node.get_text(" ", strip=True) + "\n")
        return
    if name == "li":
        out.append("\n- ")
    elif name in _BLOCK_TAGS:
        out.append("\n")
    for child in node.children:
        _render(child, out)
    if name in _BLOCK_TAGS:
        out.append("\n")


def html_to_text(html: str) -> tuple[str, str]:
    """Return (title, text) for an HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else "") or ""
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    parts: list[str] = []
    _render(root, parts)
    text = "".join(parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return title, text


def _finish(source: str, title: str, text: str) -> LabDocument:
    warning = None
    if len(text) < 400 and _LOGIN_HINTS.search(text):
        warning = (
            "The page looks like a login wall or a JavaScript-only app, so the instructions "
            "may be missing. Save the lab page (or copy its text) to a file and run "
            "`labcopilot guide --file lab.txt` instead."
        )
    elif len(text) < 200:
        warning = "Very little text was extracted; the page may need JavaScript or a login."
    truncated = len(text) > MAX_CHARS
    if truncated:
        text = text[:MAX_CHARS] + "\n\n[... lab text truncated ...]"
    return LabDocument(source=source, title=title or source, text=text,
                       truncated=truncated, warning=warning)


def load(source: str | None = None, file: str | None = None, use_stdin: bool = False) -> LabDocument:
    """Load a lab from exactly one of: URL/`source`, `file`, or stdin."""
    if use_stdin:
        text = sys.stdin.read()
        return _finish("stdin", "Pasted lab", text.strip())
    if file:
        path = Path(file).expanduser()
        if not path.is_file():
            raise FetchError(f"File not found: {path}")
        raw = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() in {".html", ".htm"}:
            title, text = html_to_text(raw)
            return _finish(str(path), title or path.name, text)
        return _finish(str(path), path.name, raw.strip())
    if source:
        if not re.match(r"^https?://", source):
            raise FetchError("Lab source must be an http(s) URL. For a local file use --file.")
        try:
            resp = httpx.get(
                source,
                follow_redirects=True,
                timeout=30,
                headers={"User-Agent": "labcopilot/0.1 (study helper)"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise FetchError(f"Could not fetch {source}: {exc}") from exc
        ctype = resp.headers.get("content-type", "")
        if "html" in ctype or resp.text.lstrip().startswith("<"):
            title, text = html_to_text(resp.text)
        else:
            title, text = source, resp.text.strip()
        return _finish(source, title, text)
    raise FetchError("Provide a lab URL, --file PATH, or --stdin.")
