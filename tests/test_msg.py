import io

from telemetry_cli._msg import Messenger


def test_default_tag_and_explicit_tag():
    out = io.StringIO()
    msg = Messenger(out)
    msg("Checking Record Lengths 1, 2 bytes")
    msg(48, "RESULT")
    assert out.getvalue() == "NOTE Checking Record Lengths 1, 2 bytes\nRESULT 48\n"
    assert msg.counts == {"NOTE": 1, "RESULT": 1}


def test_hidden_tags_are_not_printed_or_counted():
    out = io.StringIO()
    msg = Messenger(out, hide={"NOTE"})
    msg("hidden")
    msg("shown", "WARN")
    assert out.getvalue() == "WARN shown\n"
    assert msg.counts == {"WARN": 1}


def test_defaults_to_stderr(capsys):
    Messenger()("hello", "WARN")
    assert capsys.readouterr().err == "WARN hello\n"
