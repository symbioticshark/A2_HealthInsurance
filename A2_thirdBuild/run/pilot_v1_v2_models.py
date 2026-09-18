#!/usr/bin/env python3
"""Retired compatibility entry point for the former standalone pilot."""


def main(argv=None):
    print("The standalone model-selection pilot has been retired.")
    print("Run ordinary evaluation sessions, then use:")
    print("  python run/compare_v1_v2.py")
    print("Existing pilot sessions remain available in normal run_history.jsonl files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
