#!/usr/bin/env python3
"""Thin program entry point for the Problem A agent."""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from run import command_cli, interactive_cli


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        return command_cli.run(argv)
    return interactive_cli.run()


if __name__ == "__main__":
    raise SystemExit(main())
