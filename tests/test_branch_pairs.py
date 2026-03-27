from __future__ import annotations

import unittest

from clawgraph.graph import BranchInspectSummary, build_comparable_branch_pairs


class BranchPairingTest(unittest.TestCase):
    def test_pairs_only_related_branches(self) -> None:
        branches = [
            BranchInspectSummary(
                run_id="run_1",
                branch_id="br_main",
                branch_type="mainline",
                status="failed",
                source="inferred",
                parent_branch_id=None,
                open_reason=None,
                request_count=1,
                request_ids=["req_main"],
                request_fact_ids=["fact_req_main"],
                success_count=0,
                failure_count=1,
            ),
            BranchInspectSummary(
                run_id="run_1",
                branch_id="br_retry",
                branch_type="retry",
                status="succeeded",
                source="declared",
                parent_branch_id="br_main",
                open_reason="semantic:retry_declared",
                request_count=1,
                request_ids=["req_retry"],
                request_fact_ids=["fact_req_retry"],
                success_count=1,
                failure_count=0,
            ),
            BranchInspectSummary(
                run_id="run_1",
                branch_id="br_fallback",
                branch_type="fallback",
                status="failed",
                source="declared",
                parent_branch_id="br_main",
                open_reason="semantic:fallback_declared",
                request_count=1,
                request_ids=["req_fallback"],
                request_fact_ids=["fact_req_fallback"],
                success_count=0,
                failure_count=1,
            ),
            BranchInspectSummary(
                run_id="run_2",
                branch_id="br_other_parent",
                branch_type="mainline",
                status="failed",
                source="inferred",
                parent_branch_id=None,
                open_reason=None,
                request_count=1,
                request_ids=["req_other_parent"],
                request_fact_ids=["fact_req_other_parent"],
                success_count=0,
                failure_count=1,
            ),
            BranchInspectSummary(
                run_id="run_2",
                branch_id="br_other_retry",
                branch_type="retry",
                status="succeeded",
                source="declared",
                parent_branch_id="br_other_parent",
                open_reason="semantic:retry_declared",
                request_count=1,
                request_ids=["req_other_retry"],
                request_fact_ids=["fact_req_other_retry"],
                success_count=1,
                failure_count=0,
            ),
        ]

        pairs = build_comparable_branch_pairs(branches)
        pair_ids = {(pair.chosen_branch_id, pair.rejected_branch_id) for pair in pairs}

        self.assertIn(("br_retry", "br_main"), pair_ids)
        self.assertIn(("br_other_retry", "br_other_parent"), pair_ids)
        self.assertIn(("br_retry", "br_fallback"), pair_ids)
        self.assertNotIn(("br_retry", "br_other_parent"), pair_ids)
        self.assertNotIn(("br_other_retry", "br_main"), pair_ids)


if __name__ == "__main__":
    unittest.main()
