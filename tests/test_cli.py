"""The entry point has to work before anything is on PATH.

``pip3 install`` with Apple's Python puts console scripts in a directory that is not
on ``PATH``, so ``smsledger-setup`` is "command not found" on a machine where the
install succeeded. ``python3 -m smsledger <command>`` is resolved by the interpreter
instead. These tests keep that promise from rotting: every command reachable, and no
message telling a beginner to type something their shell cannot find.
"""
from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest

from smsledger.__main__ import COMMANDS, main

ROOT = Path(__file__).resolve().parents[1]
MESSAGES = ROOT / "src" / "smsledger" / "messages"


@pytest.mark.parametrize("cmd", sorted(COMMANDS))
def test_every_command_resolves_to_a_callable_entry_point(cmd: str) -> None:
    module = importlib.import_module(COMMANDS[cmd])
    assert callable(getattr(module, "main"))


def test_every_console_script_is_also_a_subcommand() -> None:
    """A shortcut that has no ``-m`` equivalent is a command nobody can be told to run."""
    toml = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    scripts = set(re.findall(r"^smsledger-(\w+) =", toml, re.M))
    assert scripts == set(COMMANDS), scripts ^ set(COMMANDS)


def test_no_argument_lists_the_commands(capsys: pytest.CaptureFixture) -> None:
    assert main([]) == 0
    out = capsys.readouterr().out
    for cmd in COMMANDS:
        assert f"python3 -m smsledger {cmd}" in out


def test_unknown_command_explains_instead_of_crashing(capsys: pytest.CaptureFixture) -> None:
    assert main(["nosuchthing"]) == 2
    assert "nosuchthing" in capsys.readouterr().err


@pytest.mark.parametrize("catalogue", sorted(MESSAGES.glob("*.json")), ids=lambda p: p.stem)
def test_no_message_tells_the_reader_to_run_a_bare_script(catalogue: Path) -> None:
    """The console scripts may not be findable. Never instruct someone to type one."""
    text = json.dumps(json.loads(catalogue.read_text(encoding="utf-8")), ensure_ascii=False)
    offenders = re.findall(r"smsledger-\w+", text)
    assert not offenders, offenders
