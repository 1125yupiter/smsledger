#!/usr/bin/env python3
"""One entry point that works before anything is on PATH.

``pip3 install`` on a Mac with only Apple's Python puts console scripts in
``~/Library/Python/3.9/bin``, which is **not** on ``PATH`` by default. So
``smsledger-setup`` is "command not found" on a machine that installed
correctly -- the first thing a non-technical person sees, and the point at which
they stop.

``python3 -m smsledger <command>`` cannot fail that way: it is resolved by the
interpreter, not by the shell's search path. The ``smsledger-*`` scripts stay,
because on a machine where they do resolve they are nicer to type.
"""
from __future__ import annotations

import importlib
import sys

# Subcommand -> module. The module's own ``main`` is the guarded entry point, so a
# failure here is recorded exactly as it is when the script is called directly.
COMMANDS = {
    "setup": "smsledger.setup",
    "doctor": "smsledger.doctor",
    "collect": "smsledger.collect",
    "parse": "smsledger.parse",
    "summary": "smsledger.summary",
    "report": "smsledger.report",
    "refresh": "smsledger.refresh",
    "agent": "smsledger.agent",
    "support": "smsledger.support",
}


def usage() -> int:
    from .i18n import t as _

    print(_("cli.usage"))
    print()
    for name in COMMANDS:
        print(f"  python3 -m smsledger {name:<8} {_('cli.' + name)}")
    print()
    print("  " + _("cli.start"))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        return usage()
    cmd, rest = argv[0], argv[1:]
    if cmd not in COMMANDS:
        from .i18n import t as _

        print(_("cli.unknown", name=cmd), file=sys.stderr)
        usage()
        return 2
    module = importlib.import_module(COMMANDS[cmd])
    # Each command parses sys.argv itself; present it the argv it would have had
    # if its own console script had been invoked.
    sys.argv = [f"smsledger-{cmd}", *rest]
    try:
        module.main()
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
