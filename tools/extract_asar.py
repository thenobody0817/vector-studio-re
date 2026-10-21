#!/usr/bin/env python3
"""Dependency-free reader/writer for Electron .asar archives.

The asar container is a Chromium Pickle header (JSON directory tree) followed by
a flat blob of file contents. Header offsets are relative to the start of the
data section, so extraction is a pure copy - no decompression, no patching.

Usage:
    extract_asar.py list   <archive.asar> [--json]
    extract_asar.py extract <archive.asar> <dest-dir> [--only <path-prefix>]
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys

PREFIX_LEN = 16  # 4 x uint32: pickle size, header size, pickle size, string size
DATA_OFFSET_BASE = 8  # the file data section starts 8 bytes past the size pickle


def read_header(archive: str) -> tuple[dict, int]:
    """Return (directory tree, absolute offset of the file data section).

    Layout: [u32 payload][u32 header_size][u32 payload][u32 json_len][json][data]
    The header pickle occupies 8 + header_size bytes, so data starts there.
    """
    with open(archive, "rb") as fh:
        prefix = fh.read(PREFIX_LEN)
        if len(prefix) < PREFIX_LEN:
            raise ValueError("archive too small to contain an asar header")
        _, header_size, _, string_size = struct.unpack("<IIII", prefix)
        header_json = fh.read(string_size).decode("utf-8")
        data_offset = DATA_OFFSET_BASE + header_size
    return json.loads(header_json), data_offset


def walk(node: dict, prefix: str = ""):
    """Yield (relative_path, file_entry) for every file in the tree."""
    for name, entry in node.get("files", {}).items():
        path = f"{prefix}{name}"
        if "files" in entry:
            yield from walk(entry, path + "/")
        else:
            yield path, entry


def cmd_list(archive: str, as_json: bool) -> int:
    header, _ = read_header(archive)
    files = list(walk(header))
    if as_json:
        json.dump([{"path": p, "size": e.get("size", 0)} for p, e in files], sys.stdout, indent=2)
        print()
        return 0
    for path, entry in files:
        print(f"{entry.get('size', 0):>12}  {path}")
    print(f"\n{len(files)} files", file=sys.stderr)
    return 0


def cmd_extract(archive: str, dest: str, only: str | None) -> int:
    header, data_offset = read_header(archive)
    written = 0
    with open(archive, "rb") as fh:
        for path, entry in walk(header):
            if only and not path.startswith(only):
                continue
            offset = entry.get("offset")
            if offset is None:
                continue  # unpacked (stored next to the archive)
            size = entry.get("size", 0)
            fh.seek(data_offset + int(offset))
            data = fh.read(size)
            out = os.path.join(dest, path)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "wb") as out_fh:
                out_fh.write(data)
            written += size
    print(f"extracted {written} bytes to {dest}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list archive contents")
    p_list.add_argument("archive")
    p_list.add_argument("--json", action="store_true")

    p_extract = sub.add_parser("extract", help="extract archive contents")
    p_extract.add_argument("archive")
    p_extract.add_argument("dest")
    p_extract.add_argument("--only", default=None, help="path prefix filter")

    args = parser.parse_args()
    if args.cmd == "list":
        return cmd_list(args.archive, args.json)
    return cmd_extract(args.archive, args.dest, args.only)


if __name__ == "__main__":
    raise SystemExit(main())
