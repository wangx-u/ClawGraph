"""Programmatic query helpers for ClawGraph scopes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from clawgraph.protocol.models import (
    ArtifactRecord,
    CohortMemberRecord,
    CohortRecord,
    DatasetSnapshotRecord,
    EvalSuiteRecord,
    FactEvent,
    FeedbackQueueRecord,
    PromotionDecisionRecord,
    ScorecardRecord,
    SliceRecord,
    TrainingAssetRecord,
)
from clawgraph.store import SQLiteFactStore


@dataclass(slots=True)
class GraphScope:
    """Resolved fact and artifact scope for one session or run."""

    session_id: str
    run_id: str | None
    facts: list[FactEvent]
    artifacts: list[ArtifactRecord]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ClawGraphQueryService:
    """Resolve session and run scopes without going through the CLI."""

    def __init__(
        self,
        *,
        store_uri: str | None = None,
        store: SQLiteFactStore | None = None,
    ) -> None:
        if store is None and store_uri is None:
            raise ValueError("store or store_uri is required")
        self.store = store or SQLiteFactStore(str(store_uri))

    def resolve_session_id(
        self,
        *,
        session: str | None = "latest",
        run_id: str | None = None,
    ) -> str | None:
        """Resolve a session id from a session selector and optional run."""

        if session not in {None, "latest"}:
            return session
        if run_id is not None:
            return self.store.get_session_id_for_run(run_id)
        return self.store.get_latest_session_id()

    def resolve_run_id(
        self,
        *,
        session: str | None = "latest",
        run_id: str | None = None,
        default_latest_run: bool = False,
    ) -> str | None:
        """Resolve a run id from session selectors."""

        if run_id is not None:
            return run_id
        if not default_latest_run:
            return None
        session_id = self.resolve_session_id(session=session)
        if session_id is None:
            return None
        return self.store.get_latest_run_id(session_id=session_id)

    def load_scope(
        self,
        *,
        session: str | None = "latest",
        run_id: str | None = None,
        default_latest_run: bool = False,
        latest_only_artifacts: bool = False,
    ) -> GraphScope:
        """Load facts and artifacts for one resolved scope."""

        effective_run_id = self.resolve_run_id(
            session=session,
            run_id=run_id,
            default_latest_run=default_latest_run,
        )
        session_id = self.resolve_session_id(session=session, run_id=effective_run_id)
        if session_id is None and effective_run_id is None:
            raise ValueError("no sessions found in store")

        facts = self.store.list_facts(session_id=session_id, run_id=effective_run_id)
        if not facts:
            raise ValueError("no facts found in scope")

        artifacts = self.store.list_artifacts(
            session_id=session_id,
            run_id=effective_run_id,
            latest_only=latest_only_artifacts,
        )
        return GraphScope(
            session_id=facts[0].session_id,
            run_id=effective_run_id,
            facts=facts,
            artifacts=artifacts,
        )

    def list_runs(self, *, session: str | None = "latest") -> list[str]:
        """List runs for one resolved session."""

        session_id = self.resolve_session_id(session=session)
        if session_id is None:
            return []
        return list(self.store.iter_runs(session_id=session_id))

    def get_slice(self, slice_id: str) -> SliceRecord | None:
        """Return one registered slice by id."""

        return self.store.get_slice(slice_id)

    def list_slices(
        self,
        *,
        task_family: str | None = None,
        task_type: str | None = None,
        taxonomy_version: str | None = None,
        default_use: str | None = None,
    ) -> list[SliceRecord]:
        """List registered slices."""

        return self.store.list_slices(
            task_family=task_family,
            task_type=task_type,
            taxonomy_version=taxonomy_version,
            default_use=default_use,
        )

    def get_cohort(self, cohort_id: str) -> CohortRecord | None:
        """Return one frozen cohort by id."""

        return self.store.get_cohort(cohort_id)

    def list_cohorts(
        self,
        *,
        slice_id: str | None = None,
        status: str | None = None,
    ) -> list[CohortRecord]:
        """List frozen cohorts."""

        return self.store.list_cohorts(slice_id=slice_id, status=status)

    def list_cohort_members(
        self,
        cohort_id: str,
        *,
        slice_id: str | None = None,
    ) -> list[CohortMemberRecord]:
        """List all members of one frozen cohort."""

        return self.store.list_cohort_members(cohort_id, slice_id=slice_id)

    def get_dataset_snapshot(
        self,
        dataset_snapshot_id: str,
    ) -> DatasetSnapshotRecord | None:
        """Return one persisted dataset snapshot."""

        return self.store.get_dataset_snapshot(dataset_snapshot_id)

    def list_dataset_snapshots(
        self,
        *,
        cohort_id: str | None = None,
        builder: str | None = None,
    ) -> list[DatasetSnapshotRecord]:
        """List persisted dataset snapshots."""

        return self.store.list_dataset_snapshots(cohort_id=cohort_id, builder=builder)

    def get_eval_suite(self, eval_suite_id: str) -> EvalSuiteRecord | None:
        """Return one eval suite."""

        return self.store.get_eval_suite(eval_suite_id)

    def list_eval_suites(
        self,
        *,
        slice_id: str | None = None,
        suite_kind: str | None = None,
    ) -> list[EvalSuiteRecord]:
        """List eval suites."""

        return self.store.list_eval_suites(slice_id=slice_id, suite_kind=suite_kind)

    def get_scorecard(self, scorecard_id: str) -> ScorecardRecord | None:
        """Return one scorecard."""

        return self.store.get_scorecard(scorecard_id)

    def list_scorecards(
        self,
        *,
        eval_suite_id: str | None = None,
        slice_id: str | None = None,
    ) -> list[ScorecardRecord]:
        """List scorecards."""

        return self.store.list_scorecards(eval_suite_id=eval_suite_id, slice_id=slice_id)

    def list_promotion_decisions(
        self,
        *,
        slice_id: str | None = None,
        scorecard_id: str | None = None,
    ) -> list[PromotionDecisionRecord]:
        """List promotion decisions."""

        return self.store.list_promotion_decisions(
            slice_id=slice_id,
            scorecard_id=scorecard_id,
        )

    def list_feedback_queue(
        self,
        *,
        slice_id: str | None = None,
        status: str | None = None,
    ) -> list[FeedbackQueueRecord]:
        """List feedback queue items."""

        return self.store.list_feedback_queue(slice_id=slice_id, status=status)

    def get_feedback_queue_item(self, feedback_id: str) -> FeedbackQueueRecord | None:
        """Return one feedback queue item by id."""

        return self.store.get_feedback_queue_item(feedback_id)

    def get_training_asset(self, asset_id: str) -> TrainingAssetRecord | None:
        """Return one persisted training asset by id."""

        return self.store.get_training_asset(asset_id)

    def list_training_assets(
        self,
        *,
        asset_kind: str | None = None,
        training_request_id: str | None = None,
        candidate_model_id: str | None = None,
        eval_suite_id: str | None = None,
        dataset_snapshot_id: str | None = None,
    ) -> list[TrainingAssetRecord]:
        """List persisted training assets."""

        return self.store.list_training_assets(
            asset_kind=asset_kind,
            training_request_id=training_request_id,
            candidate_model_id=candidate_model_id,
            eval_suite_id=eval_suite_id,
            dataset_snapshot_id=dataset_snapshot_id,
        )
