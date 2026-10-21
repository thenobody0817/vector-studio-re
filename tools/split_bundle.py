#!/usr/bin/env python3
"""Split an esbuild-style bundle back into its original modules.

Vector Studio ships a bundle that keeps the original TypeScript sources inline,
each preceded by a `// path/to/module.ts` marker. This tool slices the bundle
on those markers so every module can be read (and diffed) on its own.

Usage:
    split_bundle.py <bundle.js> <out-dir>
"""

from __future__ import annotations

import os
import re
import sys

MARKER = re.compile(r"^// ([A-Za-z0-9_./@+-]+\.tsx?)\n", re.MULTILINE)


def safe_name(marker: str) -> str:
    return marker.replace("/", "__").replace("..", "__")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    bundle_path, out_dir = sys.argv[1], sys.argv[2]
    with open(bundle_path, "r", encoding="utf-8", errors="replace") as fh:
        source = fh.read()

    markers = list(MARKER.finditer(source))
    if not markers:
        print("no module markers found", file=sys.stderr)
        return 1

    os.makedirs(out_dir, exist_ok=True)
    for index, marker in enumerate(markers):
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(source)
        body = source[start:end]
        with open(os.path.join(out_dir, f"{index:03d}_{safe_name(marker.group(1))}"), "w", encoding="utf-8") as fh:
            fh.write(body)

    print(f"{len(markers)} modules written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
