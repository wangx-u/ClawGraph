#!/usr/bin/env python3
"""Resolve one named SWE-bench Lite instance pack to a concrete instance list."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", required=True)
    parser.add_argument("--format", choices=("csv", "json", "lines"), default="csv")
    parser.add_argument(
        "--packs-file",
        type=Path,
        default=Path(__file__).with_name("instance_packs.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    packs = json.loads(args.packs_file.read_text(encoding="utf-8"))
    if args.pack not in packs:
        raise SystemExit(f"unknown pack: {args.pack}")
    instance_ids = packs[args.pack]
    if not isinstance(instance_ids, list) or not all(
        isinstance(item, str) and item for item in instance_ids
    ):
        raise SystemExit(f"invalid pack contents: {args.pack}")

    if args.format == "json":
        print(json.dumps(instance_ids, ensure_ascii=False, indent=2))
        return 0
    if args.format == "lines":
        print("\n".join(instance_ids))
        return 0
    print(",".join(instance_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
