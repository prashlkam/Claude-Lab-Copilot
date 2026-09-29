# labcopilot

A study copilot for hands-on labs. Give it a lab URL and it turns the page into an
explained, step-by-step guide, then stays open as a chat so you can debug as you go.

**You run every step yourself.** The copilot explains what each action does and why,
drafts copy-ready commands and configs, tells you how to check a step worked, and helps
you read errors. It doesn't log in, execute anything, or submit anything. If a lab contains
graded questions or a knowledge check, it teaches the concept and gives hints rather than
an answer key. Use it within your course's or employer's rules on AI assistance.

## Install

```bash
cd labcopilot
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...      # your key
# optional: export LABCOPILOT_MODEL=claude-sonnet-5-5
```

## Use

```bash
# 1. Read the lab first: explained guide, saved for reference
labcopilot guide https://example.com/lab -o lab-guide.md
labcopilot guide https://example.com/lab --focus "IAM permissions"

# 2. Work through the lab with a troubleshooting chat open
labcopilot chat https://example.com/lab

# 3. Quick one-off question
labcopilot ask https://example.com/lab "why would step 4 return a 403?"

# See exactly what text was extracted (no API call)
labcopilot show https://example.com/lab
```

### Labs behind a login

Most lab platforms need you to sign in, so a plain URL fetch only sees the login page
(the tool warns you when that happens). Save the page (Ctrl/Cmd+S, "Webpage, HTML only")
or copy its text, then:

```bash
labcopilot guide --file lab.html
labcopilot chat --file lab.txt
pbpaste | labcopilot guide --stdin     # --stdin works for guide/ask/show, not chat
```

### Chat commands

| Command | What it does |
|---|---|
| `/guide` | Print the full step-by-step guide |
| `/paste` | Send multi-line text (error logs, output); finish with a line `EOF` |
| `/reset` | Clear the conversation |
| `/quit` | Leave |

Tip: paste the *exact* error text or command output. Diagnosis is much better than from a description.

## What the guide contains

Goal · prerequisites · concepts the lab depends on · numbered steps (Do / Why / Check /
If it fails) · common pitfalls · wrap-up and cleanup of billable resources.

## Notes and limits

- Long labs are truncated at 60,000 characters (you're warned).
- Pages that render entirely with JavaScript may extract as nearly empty; save the rendered
  page or copy the text instead.
- Never paste real passwords, keys or tokens into the chat.

## Develop

```bash
pip install -e ".[dev]"
pytest
```

Prompts live in `src/labcopilot/prompts.py`; that is the place to tune tone or guide layout.
