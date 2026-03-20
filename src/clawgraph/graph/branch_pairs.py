"""Comparable branch pairing helpers for supervision and dataset export."""

from __future__ import annotations

from dataclasses import dataclass

from clawgraph.graph.inspect import BranchInspectSummary


@dataclass(slots=True)
class ComparableBranchPair:
    """A related chosen/rejected branch pair suitable for preference-style data."""

    chosen_branch_id: str
    rejected_branch_id: str
    source: str
    reason: str


def build_comparable_branch_pairs(
    branches: list[BranchInspectSummary],
) -> list[ComparableBranchPair]:
    """Return related branch pairs instead of all succeeded-versus-failed combinations."""

    branch_by_id = {branch.branch_id: branch for branch in branches}
    seen: set[tuple[str, str, str]] = set()
    pairs: list[ComparableBranchPair] = []

    def add_pair(
        *,
        chosen: BranchInspectSummary,
        rejected: BranchInspectSummary,
        source: str,
        reason: str,
    ) -> None:
        if chosen.branch_id == rejected.branch_id:
            return
        key = (chosen.branch_id, rejected.branch_id, source)
        if key in seen:
            return
        pairs.append(
            ComparableBranchPair(
                chosen_branch_id=chosen.branch_id,
                rejected_branch_id=rejected.branch_id,
                source=source,
                reason=reason,
            )
        )
        seen.add(key)

    # Prefer direct parent-child repairs such as retry/fallback after a failed parent.
    for branch in branches:
        if branch.parent_branch_id is None:
            continue
        parent = branch_by_id.get(branch.parent_branch_id)
        if parent is None:
            continue
        if branch.status == "succeeded" and parent.status == "failed":
            add_pair(
                chosen=branch,
                rejected=parent,
                source="parent_child_outcome",
                reason=f"{branch.branch_id} succeeded after parent {parent.branch_id} failed",
            )
        elif branch.status == "failed" and parent.status == "succeeded":
            add_pair(
                chosen=parent,
                rejected=branch,
                source="parent_child_outcome",
                reason=f"parent {parent.branch_id} succeeded while child {branch.branch_id} failed",
            )

    # Compare sibling alternatives that share the same parent branch.
    siblings_by_parent: dict[str, list[BranchInspectSummary]] = {}
    for branch in branches:
        if branch.parent_branch_id is None:
            continue
        siblings_by_parent.setdefault(branch.parent_branch_id, []).append(branch)

    for parent_branch_id, siblings in siblings_by_parent.items():
        succeeded = [branch for branch in siblings if branch.status == "succeeded"]
        failed = [branch for branch in siblings if branch.status == "failed"]
        for chosen in succeeded:
            for rejected in failed:
                add_pair(
                    chosen=chosen,
                    rejected=rejected,
                    source="sibling_outcome",
                    reason=(
                        f"{chosen.branch_id} succeeded while sibling {rejected.branch_id} "
                        f"under parent {parent_branch_id} failed"
                    ),
                )

    return pairs
