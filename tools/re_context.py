#!/usr/bin/env python3
"""Print context windows around needle occurrences inside minified bundles.

Minified JavaScript is a handful of multi-megabyte lines, so `grep -n` is
useless for locating a symbol. This tool prints every match with N characters
of surrounding source, which is enough to recover wire-format details
(transport, socket paths, JSON-RPC method names) from a bundle.

Usage:
    re_context.py <file> <needle> [--before 200] [--after 400] [--max 20]
"""

from __future__ import annotations

import argparse
import re
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file")
    parser.add_argument("needle")
    parser.add_argument("--before", type=int, default=200)
    parser.add_argument("--after", type=int, default=400)
    parser.add_argument("--max", type=int, default=20)
    parser.add_argument("--regex", action="store_true")
    args = parser.parse_args()

    with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
        source = fh.read()

    if args.regex:
        pattern = re.compile(args.needle)
        matches = list(pattern.finditer(source))
    else:
        matches = [m for m in re.finditer(re.escape(args.needle), source)]

    for i, match in enumerate(matches[: args.max]):
        start = max(0, match.start() - args.before)
        end = min(len(source), match.end() + args.after)
        snippet = source[start:end].replace("\n", "\\n")
        print(f"--- match {i + 1} @ {match.start()}")
        print(snippet)
    print(f"\n{len(matches)} matches", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
