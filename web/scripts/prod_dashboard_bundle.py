#!/usr/bin/env python3
"""Build one ClawGraph dashboard bundle directly from a local sqlite store."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from clawgraph.dashboard_bundle import build_web_dashboard_bundle, normalize_store_uri  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--session-limit", type=int, default=12)
    parser.add_argument("--run-limit", type=int, default=24)
    parser.add_argument("--artifact-limit", type=int, default=40)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundle = build_web_dashboard_bundle(
        store_uri=normalize_store_uri(args.store),
        session_limit=args.session_limit,
        run_limit=args.run_limit,
        artifact_limit=args.artifact_limit,
    )
    sys.stdout.write(json.dumps(bundle, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
