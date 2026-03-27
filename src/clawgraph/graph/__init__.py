"""Derived graph and replay views."""

from clawgraph.graph.branch_pairs import ComparableBranchPair, build_comparable_branch_pairs
from clawgraph.graph.correlation import (
    CorrelatedRequestGroup,
    correlate_request_groups,
    infer_branches,
    partition_facts_by_run,
)
from clawgraph.graph.inspect import (
    ArtifactInspectSummary,
    BranchInspectSummary,
    PayloadSpillSummary,
    RequestSpanSummary,
    SessionInspectSummary,
    build_branch_inspect_summaries,
    build_request_span_summaries,
    build_session_inspect_summary,
    get_branch_inspect_summary,
    get_request_span_summary,
    render_branch_inspect,
    render_request_inspect,
    render_session_inspect,
)
from clawgraph.graph.replay import render_session_replay

__all__ = [
    "BranchInspectSummary",
    "ComparableBranchPair",
    "CorrelatedRequestGroup",
    "ArtifactInspectSummary",
    "PayloadSpillSummary",
    "RequestSpanSummary",
    "SessionInspectSummary",
    "build_branch_inspect_summaries",
    "build_comparable_branch_pairs",
    "build_request_span_summaries",
    "build_session_inspect_summary",
    "correlate_request_groups",
    "get_branch_inspect_summary",
    "get_request_span_summary",
    "infer_branches",
    "partition_facts_by_run",
    "render_branch_inspect",
    "render_request_inspect",
    "render_session_inspect",
    "render_session_replay",
]
