from __future__ import annotations

import unittest
from pathlib import Path


class DocsAlignmentTest(unittest.TestCase):
    def test_docs_and_examples_do_not_reintroduce_deprecated_identity_patterns(self) -> None:
        root = Path(__file__).resolve().parents[1]
        targets = [root / "docs", root / "examples"]

        banned_substrings = (
            "x-clawgraph-run-id: sess_",
            "--run-id sess_",
            '"run_id": "sess_',
        )

        offenders: list[str] = []
        for target in targets:
            for path in target.rglob("*"):
                if not path.is_file() or path.suffix not in {".md", ".json", ".yaml", ".yml"}:
                    continue
                text = path.read_text(encoding="utf-8")
                for banned in banned_substrings:
                    if banned in text:
                        offenders.append(f"{path.relative_to(root)} contains {banned!r}")

        self.assertFalse(offenders, "\n".join(offenders))

    def test_session_latest_shortcut_is_only_documented_as_an_explicit_exception(self) -> None:
        root = Path(__file__).resolve().parents[1]
        allowed = {
            root / "docs" / "reference" / "cli_reference.md",
            root / "docs" / "zh-CN" / "cli_reference.md",
        }

        offenders: list[str] = []
        for target in (root / "docs", root / "examples"):
            for path in target.rglob("*"):
                if not path.is_file() or path.suffix not in {".md", ".json", ".yaml", ".yml"}:
                    continue
                text = path.read_text(encoding="utf-8")
                if "session:latest" in text and path not in allowed:
                    offenders.append(str(path.relative_to(root)))

        self.assertFalse(
            offenders,
            "session:latest should only remain in the CLI reference as an explicit session-scoped exception: "
            + ", ".join(offenders),
        )
