import io
import sys

import pytest

from labcopilot import cli, prompts
from labcopilot.core import MAX_HISTORY_MESSAGES, ChatSession, ask, make_guide
from labcopilot.fetch import FetchError, LabDocument, html_to_text, load

LAB_HTML = """
<html><head><title>Lab 1: Deploy a Web Server</title><style>.x{}</style></head>
<body><nav>Menu Home</nav>
<main>
<h1>Deploy a Web Server</h1>
<p>Create a VM, then install nginx.</p>
<ol><li>Run <code>sudo apt update</code></li><li>Install:</li></ol>
<pre>sudo apt install -y nginx
sudo systemctl start nginx</pre>
<script>alert('x')</script>
</main><footer>Copyright</footer></body></html>
"""


def fake_completer(reply="ok", record=None):
    def complete(system, messages):
        if record is not None:
            record.append((system, list(messages)))
        for word in reply.split(" "):
            yield word + " "
    return complete


def doc(text="Step 1: do a thing."):
    return LabDocument(source="test", title="Test Lab", text=text)


# ---- fetch ----------------------------------------------------------------

def test_html_to_text_keeps_code_and_drops_noise():
    title, text = html_to_text(LAB_HTML)
    assert title == "Lab 1: Deploy a Web Server"
    assert "# Deploy a Web Server" in text
    assert "`sudo apt update`" in text
    assert "```\nsudo apt install -y nginx\nsudo systemctl start nginx\n```" in text
    assert "alert" not in text and "Copyright" not in text and "Menu Home" not in text


def test_load_file_html_and_text(tmp_path):
    h = tmp_path / "lab.html"
    h.write_text(LAB_HTML)
    d = load(file=str(h))
    assert "nginx" in d.text and d.title.startswith("Lab 1")
    t = tmp_path / "lab.txt"
    t.write_text("Step 1: " + "x" * 300)
    assert load(file=str(t)).text.startswith("Step 1")


def test_load_errors(tmp_path):
    with pytest.raises(FetchError):
        load(file=str(tmp_path / "missing.txt"))
    with pytest.raises(FetchError):
        load(source="ftp://nope")
    with pytest.raises(FetchError):
        load()


def test_login_wall_warning(tmp_path):
    p = tmp_path / "wall.html"
    p.write_text("<html><body><p>Please sign in to continue</p></body></html>")
    assert load(file=str(p)).warning


def test_truncation(tmp_path):
    p = tmp_path / "big.txt"
    p.write_text("a" * 70_000)
    d = load(file=str(p))
    assert d.truncated and "truncated" in d.text


# ---- core -----------------------------------------------------------------

def test_guide_puts_lab_in_system_prompt_and_streams():
    rec, seen = [], []
    out = make_guide(doc("Run terraform apply"), fake_completer("a b c", rec),
                     on_text=seen.append, focus="IAM")
    assert out.strip() == "a b c"
    assert "".join(seen) == out
    system, messages = rec[0]
    assert "Run terraform apply" in system and "Test Lab" in system
    assert "IAM" in messages[0]["content"]
    assert "Why:" in system  # guide template present


def test_prompts_do_not_offer_answer_keys():
    assert "do not supply an answer" in prompts.BASE


def test_ask():
    rec = []
    ask(doc(), "why 403?", fake_completer("because", rec))
    assert rec[0][1] == [{"role": "user", "content": "why 403?"}]


def test_chat_history_and_rollback():
    rec = []
    s = ChatSession(doc(), fake_completer("hello there", rec))
    s.send("q1")
    s.send("q2")
    assert [m["role"] for m in s.history] == ["user", "assistant", "user", "assistant"]
    assert len(rec[1][1]) == 3  # q1, a1, q2 sent on second call

    def boom(system, messages):
        raise RuntimeError("api down")
        yield  # pragma: no cover

    s.complete = boom
    with pytest.raises(RuntimeError):
        s.send("q3")
    assert len(s.history) == 4  # failed turn removed


def test_chat_window_starts_with_user():
    s = ChatSession(doc(), fake_completer())
    for i in range(MAX_HISTORY_MESSAGES):
        s.history.append({"role": "user" if i % 2 == 0 else "assistant", "content": str(i)})
    s.history.append({"role": "user", "content": "latest"})
    w = s._window()
    assert w[0]["role"] == "user" and w[-1]["content"] == "latest"


# ---- cli ------------------------------------------------------------------

def test_cli_show_no_api_call(tmp_path, capsys):
    p = tmp_path / "lab.html"
    p.write_text(LAB_HTML)
    assert cli.main(["show", "--file", str(p)]) == 0
    assert "sudo apt install" in capsys.readouterr().out


def test_cli_guide_writes_file(tmp_path, monkeypatch, capsys):
    lab = tmp_path / "lab.txt"
    lab.write_text("Step 1: " + "x" * 300)
    out = tmp_path / "guide.md"
    monkeypatch.setattr(cli, "anthropic_completer", lambda: fake_completer("# Guide"))
    assert cli.main(["guide", "--file", str(lab), "-o", str(out)]) == 0
    assert out.read_text().startswith("# Guide")


def test_cli_ask_requires_question(tmp_path, monkeypatch):
    lab = tmp_path / "lab.txt"
    lab.write_text("Step 1: " + "x" * 300)
    monkeypatch.setattr(cli, "anthropic_completer", lambda: fake_completer())
    assert cli.main(["ask", "--file", str(lab)]) == 2


def test_cli_missing_api_key(tmp_path, monkeypatch, capsys):
    lab = tmp_path / "lab.txt"
    lab.write_text("Step 1: " + "x" * 300)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli.main(["guide", "--file", str(lab)]) == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_cli_chat_loop(tmp_path, monkeypatch, capsys):
    lab = tmp_path / "lab.txt"
    lab.write_text("Step 1: " + "x" * 300)
    monkeypatch.setattr(cli, "anthropic_completer", lambda: fake_completer("sure"))
    monkeypatch.setattr(sys, "stdin", io.StringIO("what is step 1?\n/reset\n/quit\n"))
    monkeypatch.setattr("builtins.input", lambda prompt="": sys.stdin.readline().rstrip("\n") or (_ for _ in ()).throw(EOFError))
    assert cli.main(["chat", "--file", str(lab)]) == 0
    out = capsys.readouterr().out
    assert "sure" in out and "conversation cleared" in out
