"""CLI entrypoint for the early ClawGraph skeleton."""

from __future__ import annotations

import argparse
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawgraph")
    subparsers = parser.add_subparsers(dest="command")

    proxy = subparsers.add_parser("proxy", help="Start the proxy server")
    proxy.add_argument("--model-upstream")
    proxy.add_argument("--tool-upstream")
    proxy.add_argument("--store")

    replay = subparsers.add_parser("replay", help="Inspect a session replay")
    replay.add_argument("--session", required=True)

    export = subparsers.add_parser("export", help="Export reusable datasets")
    export_subparsers = export.add_subparsers(dest="export_command")
    dataset = export_subparsers.add_parser("dataset", help="Export a dataset")
    dataset.add_argument("--builder", required=True)
    dataset.add_argument("--session", required=True)
    dataset.add_argument("--out", type=Path, required=True)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "proxy":
        print("proxy command scaffolded; implementation pending")
        return 0

    if args.command == "replay":
        print(f"replay command scaffolded for session={args.session}")
        return 0

    if args.command == "export" and args.export_command == "dataset":
        print(
            "dataset export scaffolded; "
            f"builder={args.builder} session={args.session} out={args.out}"
        )
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
