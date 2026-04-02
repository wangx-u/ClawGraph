"""SQLite-backed append-only fact store for ClawGraph."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

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
)
from clawgraph.protocol.validation import (
    validate_artifact_record,
    validate_cohort_member_record,
    validate_cohort_record,
    validate_dataset_snapshot_record,
    validate_eval_suite_record,
    validate_fact_event,
    validate_feedback_queue_record,
    validate_promotion_decision_record,
    validate_scorecard_record,
    validate_slice_record,
)

_ANNOTATION_ARTIFACT_TYPE = "annotation"
_E1_ANNOTATION_KIND = "e1"


def parse_store_uri(store_uri: str) -> Path:
    """Parse a sqlite URI into a concrete filesystem path."""

    parsed = urlparse(store_uri)
    if parsed.scheme != "sqlite":
        raise ValueError(f"unsupported store scheme: {parsed.scheme}")

    path = parsed.path
    if not path:
        raise ValueError("sqlite store URI must include a path")

    if path.startswith("//"):
        resolved = Path(path[1:])
    elif path.startswith("/"):
        parts = Path(path).parts[1:]
        if len(parts) <= 1:
            resolved = Path(*parts)
        else:
            resolved = Path(path)
    else:
        resolved = Path(path)

    return resolved.expanduser()


class SQLiteFactStore:
    """Append-only fact store backed by sqlite."""

    def __init__(self, store_uri: str) -> None:
        self.store_uri = store_uri
        self.path = parse_store_uri(store_uri)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _init_db(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact_id TEXT UNIQUE NOT NULL,
                    schema_version TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    request_id TEXT,
                    user_id TEXT,
                    thread_id TEXT,
                    task_id TEXT,
                    parent_ref TEXT,
                    branch_id TEXT,
                    timestamp TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_facts_session_ts
                    ON facts(session_id, timestamp, seq);
                CREATE INDEX IF NOT EXISTS idx_facts_run_ts
                    ON facts(run_id, timestamp, seq);
                CREATE INDEX IF NOT EXISTS idx_facts_request_ts
                    ON facts(request_id, timestamp, seq);

                CREATE TABLE IF NOT EXISTS artifacts (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id TEXT UNIQUE NOT NULL,
                    schema_version TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    target_ref TEXT NOT NULL,
                    producer TEXT NOT NULL,
                    version TEXT,
                    session_id TEXT,
                    run_id TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    confidence REAL,
                    supersedes_artifact_id TEXT,
                    payload_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_artifacts_session_created
                    ON artifacts(session_id, created_at, seq);
                CREATE INDEX IF NOT EXISTS idx_artifacts_target_created
                    ON artifacts(target_ref, created_at, seq);

                CREATE TABLE IF NOT EXISTS annotation_index (
                    artifact_id TEXT PRIMARY KEY,
                    artifact_type TEXT NOT NULL,
                    annotation_kind TEXT,
                    target_kind TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    target_ref TEXT NOT NULL,
                    session_id TEXT,
                    run_id TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    supersedes_artifact_id TEXT,
                    task_family TEXT,
                    task_type TEXT,
                    taxonomy_version TEXT,
                    task_instance_key TEXT,
                    task_template_hash TEXT,
                    verifier_name TEXT,
                    verifier_score REAL,
                    quality_confidence REAL,
                    source_channel TEXT,
                    annotation_version TEXT,
                    difficulty TEXT,
                    teacher_model TEXT,
                    policy_version TEXT,
                    new_subtype INTEGER,
                    novel_path INTEGER,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_annotation_index_slice_lookup
                    ON annotation_index(
                        annotation_kind, task_family, task_type, taxonomy_version, created_at
                    );
                CREATE INDEX IF NOT EXISTS idx_annotation_index_target_lookup
                    ON annotation_index(annotation_kind, target_kind, target_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_annotation_index_run_lookup
                    ON annotation_index(annotation_kind, run_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_annotation_index_session_lookup
                    ON annotation_index(annotation_kind, session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_annotation_index_instance_lookup
                    ON annotation_index(task_instance_key, task_template_hash, created_at);

                CREATE TABLE IF NOT EXISTS session_owners (
                    session_id TEXT PRIMARY KEY,
                    owner_key TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS slices (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    slice_id TEXT UNIQUE NOT NULL,
                    schema_version TEXT NOT NULL,
                    task_family TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    taxonomy_version TEXT NOT NULL,
                    sample_unit TEXT NOT NULL,
                    verifier_contract TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    default_use TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_slices_taxonomy
                    ON slices(task_family, task_type, taxonomy_version, default_use);

                CREATE TABLE IF NOT EXISTS cohorts (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    cohort_id TEXT UNIQUE NOT NULL,
                    schema_version TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_cohorts_created
                    ON cohorts(created_at DESC, seq DESC);

                CREATE TABLE IF NOT EXISTS cohort_slice_links (
                    cohort_id TEXT NOT NULL,
                    slice_id TEXT NOT NULL,
                    PRIMARY KEY (cohort_id, slice_id)
                );

                CREATE INDEX IF NOT EXISTS idx_cohort_slice_links_slice
                    ON cohort_slice_links(slice_id, cohort_id);

                CREATE TABLE IF NOT EXISTS cohort_members (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    member_id TEXT UNIQUE NOT NULL,
                    cohort_id TEXT NOT NULL,
                    slice_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    annotation_artifact_id TEXT NOT NULL,
                    task_instance_key TEXT NOT NULL,
                    task_template_hash TEXT,
                    quality_confidence REAL,
                    verifier_score REAL,
                    source_channel TEXT,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_cohort_members_cohort_created
                    ON cohort_members(cohort_id, created_at, seq);
                CREATE INDEX IF NOT EXISTS idx_cohort_members_run
                    ON cohort_members(run_id, cohort_id);
                CREATE INDEX IF NOT EXISTS idx_cohort_members_slice
                    ON cohort_members(slice_id, cohort_id);

                CREATE TABLE IF NOT EXISTS dataset_snapshots (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_snapshot_id TEXT UNIQUE NOT NULL,
                    schema_version TEXT NOT NULL,
                    dataset_recipe_id TEXT NOT NULL,
                    builder TEXT NOT NULL,
                    sample_unit TEXT NOT NULL,
                    cohort_id TEXT,
                    output_path TEXT,
                    record_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_dataset_snapshots_cohort_created
                    ON dataset_snapshots(cohort_id, created_at DESC, seq DESC);
                CREATE INDEX IF NOT EXISTS idx_dataset_snapshots_builder_created
                    ON dataset_snapshots(builder, created_at DESC, seq DESC);

                CREATE TABLE IF NOT EXISTS eval_suites (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    eval_suite_id TEXT UNIQUE NOT NULL,
                    schema_version TEXT NOT NULL,
                    slice_id TEXT NOT NULL,
                    suite_kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    cohort_id TEXT,
                    dataset_snapshot_id TEXT,
                    created_at TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_eval_suites_slice_created
                    ON eval_suites(slice_id, created_at DESC, seq DESC);

                CREATE TABLE IF NOT EXISTS scorecards (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    scorecard_id TEXT UNIQUE NOT NULL,
                    schema_version TEXT NOT NULL,
                    eval_suite_id TEXT NOT NULL,
                    slice_id TEXT NOT NULL,
                    candidate_model TEXT NOT NULL,
                    baseline_model TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    thresholds_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_scorecards_suite_created
                    ON scorecards(eval_suite_id, created_at DESC, seq DESC);

                CREATE TABLE IF NOT EXISTS promotion_decisions (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    promotion_decision_id TEXT UNIQUE NOT NULL,
                    schema_version TEXT NOT NULL,
                    slice_id TEXT NOT NULL,
                    scorecard_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    coverage_policy_version TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    rollback_conditions_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_promotion_decisions_slice_created
                    ON promotion_decisions(slice_id, created_at DESC, seq DESC);

                CREATE TABLE IF NOT EXISTS feedback_queue (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    feedback_id TEXT UNIQUE NOT NULL,
                    schema_version TEXT NOT NULL,
                    slice_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    target_ref TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_feedback_queue_slice_created
                    ON feedback_queue(slice_id, created_at DESC, seq DESC);
                """
            )
            self._ensure_column(connection, "facts", "request_id", "TEXT")
            self._ensure_column(connection, "facts", "user_id", "TEXT")
            self._ensure_column(
                connection,
                "artifacts",
                "status",
                "TEXT NOT NULL DEFAULT 'active'",
            )
            self._ensure_column(connection, "artifacts", "confidence", "REAL")
            self._ensure_column(connection, "artifacts", "supersedes_artifact_id", "TEXT")
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_artifacts_lookup
                ON artifacts(artifact_type, producer, status, created_at, seq)
                """
            )
            self._backfill_annotation_index(connection)
            connection.commit()

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_definition: str,
    ) -> None:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        known_columns = {str(row["name"]) for row in rows}
        if column_name in known_columns:
            return
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )

    def append_fact(self, fact: FactEvent) -> None:
        """Persist a fact event."""

        self.append_facts([fact])

    def append_facts(self, facts: Iterable[FactEvent]) -> None:
        """Persist multiple fact events in a single transaction."""

        validated_facts = list(facts)
        for fact in validated_facts:
            validate_fact_event(fact)
        fact_rows = [
            (
                fact.fact_id,
                fact.schema_version,
                fact.run_id,
                fact.session_id,
                fact.request_id,
                fact.user_id,
                fact.thread_id,
                fact.task_id,
                fact.parent_ref,
                fact.branch_id,
                fact.timestamp.isoformat(),
                fact.actor,
                fact.kind,
                json.dumps(fact.payload, ensure_ascii=True, sort_keys=True),
                json.dumps(fact.metadata, ensure_ascii=True, sort_keys=True),
            )
            for fact in validated_facts
        ]
        if not fact_rows:
            return

        with closing(self._connect()) as connection:
            connection.executemany(
                """
                INSERT INTO facts (
                    fact_id, schema_version, run_id, session_id, request_id,
                    user_id, thread_id,
                    task_id, parent_ref, branch_id, timestamp, actor, kind,
                    payload_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                fact_rows,
            )
            connection.commit()

    def list_facts(
        self,
        session_id: str | None = None,
        *,
        request_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> list[FactEvent]:
        """Return facts filtered by session or request id ordered by insertion."""

        if session_id is None and request_id is None and run_id is None and task_id is None:
            raise ValueError("session_id, request_id, run_id, or task_id is required")

        clauses: list[str] = []
        values: list[str] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            values.append(session_id)
        if request_id is not None:
            clauses.append("request_id = ?")
            values.append(request_id)
        if run_id is not None:
            clauses.append("run_id = ?")
            values.append(run_id)
        if task_id is not None:
            clauses.append("task_id = ?")
            values.append(task_id)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                (
                    "SELECT * FROM facts WHERE "
                    + " AND ".join(clauses)
                    + " ORDER BY timestamp ASC, seq ASC"
                ),
                values,
            ).fetchall()

        return [self._row_to_fact(row) for row in rows]

    def get_latest_request_id(
        self,
        session_id: str | None = None,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> str | None:
        """Return the most recently seen request id."""

        query = "SELECT request_id FROM facts"
        values: list[str] = []
        clauses: list[str] = ["request_id IS NOT NULL"]
        if session_id is not None:
            clauses.append("session_id = ?")
            values.append(session_id)
        if run_id is not None:
            clauses.append("run_id = ?")
            values.append(run_id)
        if task_id is not None:
            clauses.append("task_id = ?")
            values.append(task_id)
        query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY timestamp DESC, seq DESC LIMIT 1"

        with closing(self._connect()) as connection:
            row = connection.execute(query, values).fetchone()
        if row is None:
            return None
        return str(row["request_id"])

    def claim_session_owner(self, *, session_id: str, owner_key: str) -> str | None:
        """Claim a session for one owner key or return the conflicting existing owner."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT owner_key
                FROM session_owners
                WHERE session_id = ?
                """,
                [session_id],
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO session_owners(session_id, owner_key, first_seen_at)
                    VALUES (?, ?, ?)
                    """,
                    [session_id, owner_key, datetime.now().isoformat()],
                )
                connection.commit()
                return None
            existing_owner = str(row["owner_key"])
            if existing_owner == owner_key:
                return None
            return existing_owner

    def get_session_owner(self, session_id: str) -> str | None:
        """Return the current owner key for a session, if claimed."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT owner_key
                FROM session_owners
                WHERE session_id = ?
                """,
                [session_id],
            ).fetchone()
        if row is None:
            return None
        return str(row["owner_key"])

    def put_slice(self, slice_record: SliceRecord) -> SliceRecord:
        """Create or update one slice registry record."""

        validate_slice_record(slice_record)
        existing = self.get_slice(slice_record.slice_id)
        created_at = (
            existing.created_at
            if existing is not None and existing.created_at is not None
            else slice_record.created_at or datetime.now().astimezone()
        )
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO slices (
                    slice_id, schema_version, task_family, task_type, taxonomy_version,
                    sample_unit, verifier_contract, risk_level, default_use, owner,
                    description, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slice_id) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    task_family = excluded.task_family,
                    task_type = excluded.task_type,
                    taxonomy_version = excluded.taxonomy_version,
                    sample_unit = excluded.sample_unit,
                    verifier_contract = excluded.verifier_contract,
                    risk_level = excluded.risk_level,
                    default_use = excluded.default_use,
                    owner = excluded.owner,
                    description = excluded.description,
                    created_at = excluded.created_at,
                    metadata_json = excluded.metadata_json
                """,
                [
                    slice_record.slice_id,
                    slice_record.schema_version,
                    slice_record.task_family,
                    slice_record.task_type,
                    slice_record.taxonomy_version,
                    slice_record.sample_unit,
                    slice_record.verifier_contract,
                    slice_record.risk_level,
                    slice_record.default_use,
                    slice_record.owner,
                    slice_record.description,
                    created_at.isoformat(),
                    json.dumps(slice_record.metadata, ensure_ascii=True, sort_keys=True),
                ],
            )
            connection.commit()
        persisted = self.get_slice(slice_record.slice_id)
        if persisted is None:
            raise ValueError(f"failed to persist slice: {slice_record.slice_id}")
        return persisted

    def get_slice(self, slice_id: str) -> SliceRecord | None:
        """Return one registered slice by id."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM slices
                WHERE slice_id = ?
                LIMIT 1
                """,
                [slice_id],
            ).fetchone()
        if row is None:
            return None
        return self._row_to_slice(row)

    def list_slices(
        self,
        *,
        task_family: str | None = None,
        task_type: str | None = None,
        taxonomy_version: str | None = None,
        default_use: str | None = None,
    ) -> list[SliceRecord]:
        """List slice registry records in creation order."""

        query = "SELECT * FROM slices"
        clauses: list[str] = []
        values: list[str] = []
        for value, label in (
            (task_family, "task_family"),
            (task_type, "task_type"),
            (taxonomy_version, "taxonomy_version"),
            (default_use, "default_use"),
        ):
            if value is None:
                continue
            clauses.append(f"{label} = ?")
            values.append(value)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at ASC, seq ASC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._row_to_slice(row) for row in rows]

    def append_cohort(
        self,
        cohort: CohortRecord,
        *,
        members: Iterable[CohortMemberRecord],
    ) -> None:
        """Persist one frozen cohort and its membership rows."""

        validate_cohort_record(cohort)
        validated_members = list(members)
        if not validated_members:
            raise ValueError("cohort members must not be empty")
        for member in validated_members:
            validate_cohort_member_record(member)
            if member.cohort_id != cohort.cohort_id:
                raise ValueError("cohort member cohort_id must match cohort")
        known_slice_ids = {slice_record.slice_id for slice_record in self.list_slices()}
        missing_slice_ids = [slice_id for slice_id in cohort.slice_ids if slice_id not in known_slice_ids]
        if missing_slice_ids:
            raise ValueError(
                "unknown slice ids in cohort: " + ", ".join(sorted(missing_slice_ids))
            )
        created_at = cohort.created_at or datetime.now().astimezone()
        with closing(self._connect()) as connection:
            existing = connection.execute(
                """
                SELECT cohort_id
                FROM cohorts
                WHERE cohort_id = ?
                LIMIT 1
                """,
                [cohort.cohort_id],
            ).fetchone()
            if existing is not None:
                raise ValueError(f"cohort already exists: {cohort.cohort_id}")
            connection.execute(
                """
                INSERT INTO cohorts (
                    cohort_id, schema_version, name, status, created_at, manifest_json,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    cohort.cohort_id,
                    cohort.schema_version,
                    cohort.name,
                    cohort.status,
                    created_at.isoformat(),
                    json.dumps(cohort.manifest, ensure_ascii=True, sort_keys=True),
                    json.dumps(cohort.metadata, ensure_ascii=True, sort_keys=True),
                ],
            )
            connection.executemany(
                """
                INSERT INTO cohort_slice_links (cohort_id, slice_id)
                VALUES (?, ?)
                """,
                [(cohort.cohort_id, slice_id) for slice_id in cohort.slice_ids],
            )
            connection.executemany(
                """
                INSERT INTO cohort_members (
                    member_id, cohort_id, slice_id, session_id, run_id,
                    annotation_artifact_id, task_instance_key, task_template_hash,
                    quality_confidence, verifier_score, source_channel, created_at,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        member.member_id,
                        member.cohort_id,
                        member.slice_id,
                        member.session_id,
                        member.run_id,
                        member.annotation_artifact_id,
                        member.task_instance_key,
                        member.task_template_hash,
                        member.quality_confidence,
                        member.verifier_score,
                        member.source_channel,
                        (member.created_at or datetime.now().astimezone()).isoformat(),
                        json.dumps(member.metadata, ensure_ascii=True, sort_keys=True),
                    )
                    for member in validated_members
                ],
            )
            connection.commit()

    def get_cohort(self, cohort_id: str) -> CohortRecord | None:
        """Return one frozen cohort by id."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM cohorts
                WHERE cohort_id = ?
                LIMIT 1
                """,
                [cohort_id],
            ).fetchone()
            if row is None:
                return None
            slice_rows = connection.execute(
                """
                SELECT slice_id
                FROM cohort_slice_links
                WHERE cohort_id = ?
                ORDER BY slice_id ASC
                """,
                [cohort_id],
            ).fetchall()
        return self._row_to_cohort(
            row,
            slice_ids=[str(slice_row["slice_id"]) for slice_row in slice_rows],
        )

    def list_cohorts(
        self,
        *,
        slice_id: str | None = None,
        status: str | None = None,
    ) -> list[CohortRecord]:
        """List known cohorts in reverse creation order."""

        query = """
            SELECT DISTINCT cohorts.*
            FROM cohorts
            LEFT JOIN cohort_slice_links
                ON cohort_slice_links.cohort_id = cohorts.cohort_id
        """
        clauses: list[str] = []
        values: list[str] = []
        if slice_id is not None:
            clauses.append("cohort_slice_links.slice_id = ?")
            values.append(slice_id)
        if status is not None:
            clauses.append("cohorts.status = ?")
            values.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY cohorts.created_at DESC, cohorts.seq DESC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, values).fetchall()
            cohort_ids = [str(row["cohort_id"]) for row in rows]
            if not cohort_ids:
                return []
            placeholders = ", ".join("?" for _ in cohort_ids)
            slice_rows = connection.execute(
                f"""
                SELECT cohort_id, slice_id
                FROM cohort_slice_links
                WHERE cohort_id IN ({placeholders})
                ORDER BY cohort_id ASC, slice_id ASC
                """,
                cohort_ids,
            ).fetchall()
        slice_ids_by_cohort: dict[str, list[str]] = {}
        for slice_row in slice_rows:
            slice_ids_by_cohort.setdefault(str(slice_row["cohort_id"]), []).append(
                str(slice_row["slice_id"])
            )
        return [
            self._row_to_cohort(
                row,
                slice_ids=slice_ids_by_cohort.get(str(row["cohort_id"]), []),
            )
            for row in rows
        ]

    def list_cohort_members(
        self,
        cohort_id: str,
        *,
        slice_id: str | None = None,
    ) -> list[CohortMemberRecord]:
        """List all members for one frozen cohort."""

        query = "SELECT * FROM cohort_members WHERE cohort_id = ?"
        values: list[str] = [cohort_id]
        if slice_id is not None:
            query += " AND slice_id = ?"
            values.append(slice_id)
        query += " ORDER BY created_at ASC, seq ASC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._row_to_cohort_member(row) for row in rows]

    def append_dataset_snapshot(self, snapshot: DatasetSnapshotRecord) -> None:
        """Persist one dataset snapshot manifest."""

        validate_dataset_snapshot_record(snapshot)
        created_at = snapshot.created_at or datetime.now().astimezone()
        with closing(self._connect()) as connection:
            existing = connection.execute(
                """
                SELECT dataset_snapshot_id
                FROM dataset_snapshots
                WHERE dataset_snapshot_id = ?
                LIMIT 1
                """,
                [snapshot.dataset_snapshot_id],
            ).fetchone()
            if existing is not None:
                raise ValueError(
                    f"dataset snapshot already exists: {snapshot.dataset_snapshot_id}"
                )
            connection.execute(
                """
                INSERT INTO dataset_snapshots (
                    dataset_snapshot_id, schema_version, dataset_recipe_id, builder,
                    sample_unit, cohort_id, output_path, record_count, created_at,
                    manifest_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    snapshot.dataset_snapshot_id,
                    snapshot.schema_version,
                    snapshot.dataset_recipe_id,
                    snapshot.builder,
                    snapshot.sample_unit,
                    snapshot.cohort_id,
                    snapshot.output_path,
                    snapshot.record_count,
                    created_at.isoformat(),
                    json.dumps(snapshot.manifest, ensure_ascii=True, sort_keys=True),
                    json.dumps(snapshot.metadata, ensure_ascii=True, sort_keys=True),
                ],
            )
            connection.commit()

    def get_dataset_snapshot(self, dataset_snapshot_id: str) -> DatasetSnapshotRecord | None:
        """Return one persisted dataset snapshot by id."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM dataset_snapshots
                WHERE dataset_snapshot_id = ?
                LIMIT 1
                """,
                [dataset_snapshot_id],
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dataset_snapshot(row)

    def list_dataset_snapshots(
        self,
        *,
        cohort_id: str | None = None,
        builder: str | None = None,
    ) -> list[DatasetSnapshotRecord]:
        """List persisted dataset snapshots in reverse creation order."""

        query = "SELECT * FROM dataset_snapshots"
        clauses: list[str] = []
        values: list[str] = []
        if cohort_id is not None:
            clauses.append("cohort_id = ?")
            values.append(cohort_id)
        if builder is not None:
            clauses.append("builder = ?")
            values.append(builder)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC, seq DESC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._row_to_dataset_snapshot(row) for row in rows]

    def append_eval_suite(self, suite: EvalSuiteRecord) -> None:
        """Persist one eval suite manifest."""

        validate_eval_suite_record(suite)
        created_at = suite.created_at or datetime.now().astimezone()
        with closing(self._connect()) as connection:
            existing = connection.execute(
                """
                SELECT eval_suite_id
                FROM eval_suites
                WHERE eval_suite_id = ?
                LIMIT 1
                """,
                [suite.eval_suite_id],
            ).fetchone()
            if existing is not None:
                raise ValueError(f"eval suite already exists: {suite.eval_suite_id}")
            connection.execute(
                """
                INSERT INTO eval_suites (
                    eval_suite_id, schema_version, slice_id, suite_kind, name, status,
                    cohort_id, dataset_snapshot_id, created_at, manifest_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    suite.eval_suite_id,
                    suite.schema_version,
                    suite.slice_id,
                    suite.suite_kind,
                    suite.name,
                    suite.status,
                    suite.cohort_id,
                    suite.dataset_snapshot_id,
                    created_at.isoformat(),
                    json.dumps(suite.manifest, ensure_ascii=True, sort_keys=True),
                    json.dumps(suite.metadata, ensure_ascii=True, sort_keys=True),
                ],
            )
            connection.commit()

    def get_eval_suite(self, eval_suite_id: str) -> EvalSuiteRecord | None:
        """Return one eval suite by id."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM eval_suites
                WHERE eval_suite_id = ?
                LIMIT 1
                """,
                [eval_suite_id],
            ).fetchone()
        if row is None:
            return None
        return self._row_to_eval_suite(row)

    def list_eval_suites(
        self,
        *,
        slice_id: str | None = None,
        suite_kind: str | None = None,
    ) -> list[EvalSuiteRecord]:
        """List eval suites in reverse creation order."""

        query = "SELECT * FROM eval_suites"
        clauses: list[str] = []
        values: list[str] = []
        if slice_id is not None:
            clauses.append("slice_id = ?")
            values.append(slice_id)
        if suite_kind is not None:
            clauses.append("suite_kind = ?")
            values.append(suite_kind)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC, seq DESC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._row_to_eval_suite(row) for row in rows]

    def append_scorecard(self, scorecard: ScorecardRecord) -> None:
        """Persist one scorecard."""

        validate_scorecard_record(scorecard)
        created_at = scorecard.created_at or datetime.now().astimezone()
        with closing(self._connect()) as connection:
            existing = connection.execute(
                """
                SELECT scorecard_id
                FROM scorecards
                WHERE scorecard_id = ?
                LIMIT 1
                """,
                [scorecard.scorecard_id],
            ).fetchone()
            if existing is not None:
                raise ValueError(f"scorecard already exists: {scorecard.scorecard_id}")
            connection.execute(
                """
                INSERT INTO scorecards (
                    scorecard_id, schema_version, eval_suite_id, slice_id, candidate_model,
                    baseline_model, verdict, created_at, metrics_json, thresholds_json,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    scorecard.scorecard_id,
                    scorecard.schema_version,
                    scorecard.eval_suite_id,
                    scorecard.slice_id,
                    scorecard.candidate_model,
                    scorecard.baseline_model,
                    scorecard.verdict,
                    created_at.isoformat(),
                    json.dumps(scorecard.metrics, ensure_ascii=True, sort_keys=True),
                    json.dumps(scorecard.thresholds, ensure_ascii=True, sort_keys=True),
                    json.dumps(scorecard.metadata, ensure_ascii=True, sort_keys=True),
                ],
            )
            connection.commit()

    def get_scorecard(self, scorecard_id: str) -> ScorecardRecord | None:
        """Return one scorecard by id."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM scorecards
                WHERE scorecard_id = ?
                LIMIT 1
                """,
                [scorecard_id],
            ).fetchone()
        if row is None:
            return None
        return self._row_to_scorecard(row)

    def list_scorecards(
        self,
        *,
        eval_suite_id: str | None = None,
        slice_id: str | None = None,
    ) -> list[ScorecardRecord]:
        """List scorecards in reverse creation order."""

        query = "SELECT * FROM scorecards"
        clauses: list[str] = []
        values: list[str] = []
        if eval_suite_id is not None:
            clauses.append("eval_suite_id = ?")
            values.append(eval_suite_id)
        if slice_id is not None:
            clauses.append("slice_id = ?")
            values.append(slice_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC, seq DESC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._row_to_scorecard(row) for row in rows]

    def append_promotion_decision(self, decision: PromotionDecisionRecord) -> None:
        """Persist one promotion decision."""

        validate_promotion_decision_record(decision)
        created_at = decision.created_at or datetime.now().astimezone()
        with closing(self._connect()) as connection:
            existing = connection.execute(
                """
                SELECT promotion_decision_id
                FROM promotion_decisions
                WHERE promotion_decision_id = ?
                LIMIT 1
                """,
                [decision.promotion_decision_id],
            ).fetchone()
            if existing is not None:
                raise ValueError(
                    f"promotion decision already exists: {decision.promotion_decision_id}"
                )
            connection.execute(
                """
                INSERT INTO promotion_decisions (
                    promotion_decision_id, schema_version, slice_id, scorecard_id, stage,
                    decision, coverage_policy_version, summary, rollback_conditions_json,
                    created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    decision.promotion_decision_id,
                    decision.schema_version,
                    decision.slice_id,
                    decision.scorecard_id,
                    decision.stage,
                    decision.decision,
                    decision.coverage_policy_version,
                    decision.summary,
                    json.dumps(decision.rollback_conditions, ensure_ascii=True, sort_keys=True),
                    created_at.isoformat(),
                    json.dumps(decision.metadata, ensure_ascii=True, sort_keys=True),
                ],
            )
            connection.commit()

    def get_promotion_decision(
        self,
        promotion_decision_id: str,
    ) -> PromotionDecisionRecord | None:
        """Return one promotion decision by id."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM promotion_decisions
                WHERE promotion_decision_id = ?
                LIMIT 1
                """,
                [promotion_decision_id],
            ).fetchone()
        if row is None:
            return None
        return self._row_to_promotion_decision(row)

    def list_promotion_decisions(
        self,
        *,
        slice_id: str | None = None,
        scorecard_id: str | None = None,
    ) -> list[PromotionDecisionRecord]:
        """List promotion decisions in reverse creation order."""

        query = "SELECT * FROM promotion_decisions"
        clauses: list[str] = []
        values: list[str] = []
        if slice_id is not None:
            clauses.append("slice_id = ?")
            values.append(slice_id)
        if scorecard_id is not None:
            clauses.append("scorecard_id = ?")
            values.append(scorecard_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC, seq DESC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._row_to_promotion_decision(row) for row in rows]

    def append_feedback_queue_item(self, feedback: FeedbackQueueRecord) -> None:
        """Persist one feedback queue item."""

        validate_feedback_queue_record(feedback)
        created_at = feedback.created_at or datetime.now().astimezone()
        with closing(self._connect()) as connection:
            existing = connection.execute(
                """
                SELECT feedback_id
                FROM feedback_queue
                WHERE feedback_id = ?
                LIMIT 1
                """,
                [feedback.feedback_id],
            ).fetchone()
            if existing is not None:
                raise ValueError(f"feedback item already exists: {feedback.feedback_id}")
            connection.execute(
                """
                INSERT INTO feedback_queue (
                    feedback_id, schema_version, slice_id, source, status, target_ref, reason,
                    created_at, payload_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    feedback.feedback_id,
                    feedback.schema_version,
                    feedback.slice_id,
                    feedback.source,
                    feedback.status,
                    feedback.target_ref,
                    feedback.reason,
                    created_at.isoformat(),
                    json.dumps(feedback.payload, ensure_ascii=True, sort_keys=True),
                    json.dumps(feedback.metadata, ensure_ascii=True, sort_keys=True),
                ],
            )
            connection.commit()

    def list_feedback_queue(
        self,
        *,
        slice_id: str | None = None,
        status: str | None = None,
    ) -> list[FeedbackQueueRecord]:
        """List feedback queue items in reverse creation order."""

        query = "SELECT * FROM feedback_queue"
        clauses: list[str] = []
        values: list[str] = []
        if slice_id is not None:
            clauses.append("slice_id = ?")
            values.append(slice_id)
        if status is not None:
            clauses.append("status = ?")
            values.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC, seq DESC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._row_to_feedback_queue(row) for row in rows]

    def append_artifact(self, artifact: ArtifactRecord) -> None:
        """Persist an external supervision artifact."""

        self.append_artifacts([artifact])

    def append_artifacts(self, artifacts: Iterable[ArtifactRecord]) -> None:
        """Persist multiple artifacts in a single transaction."""

        validated_artifacts = list(artifacts)
        artifact_rows = []
        indexed_artifacts: list[tuple[ArtifactRecord, str]] = []
        for artifact in validated_artifacts:
            validate_artifact_record(artifact)
            created_at = artifact.created_at or datetime.now().astimezone()
            created_at_iso = created_at.isoformat()
            artifact_rows.append(
                (
                    artifact.artifact_id,
                    artifact.schema_version,
                    artifact.artifact_type,
                    artifact.target_ref,
                    artifact.producer,
                    artifact.version,
                    artifact.session_id,
                    artifact.run_id,
                    created_at_iso,
                    artifact.status,
                    artifact.confidence,
                    artifact.supersedes_artifact_id,
                    json.dumps(artifact.payload, ensure_ascii=True, sort_keys=True),
                    json.dumps(artifact.metadata, ensure_ascii=True, sort_keys=True),
                )
            )
            indexed_artifacts.append((artifact, created_at_iso))
        if not artifact_rows:
            return

        with closing(self._connect()) as connection:
            connection.executemany(
                """
                INSERT INTO artifacts (
                    artifact_id, schema_version, artifact_type, target_ref, producer,
                    version, session_id, run_id, created_at, status, confidence,
                    supersedes_artifact_id, payload_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                artifact_rows,
            )
            self._index_annotation_artifacts(connection, indexed_artifacts)
            connection.commit()

    def list_e1_candidate_annotations(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        task_family: str,
        task_type: str,
        taxonomy_version: str,
        task_instance_key: str | None = None,
        task_template_hash: str | None = None,
        min_quality_confidence: float | None = None,
        min_verifier_score: float | None = None,
        source_channel: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return merged run-level E1 annotation candidates using indexed SQL lookups."""

        runs_query = """
            SELECT run_id, MIN(session_id) AS session_id, MAX(timestamp) AS latest_timestamp
            FROM facts
        """
        run_clauses: list[str] = []
        run_values: list[Any] = []
        if session_id is not None:
            run_clauses.append("session_id = ?")
            run_values.append(session_id)
        if run_id is not None:
            run_clauses.append("run_id = ?")
            run_values.append(run_id)
        if run_clauses:
            runs_query += " WHERE " + " AND ".join(run_clauses)
        runs_query += " GROUP BY run_id"

        query = f"""
            WITH runs AS (
                {runs_query}
            ),
            latest_session_annotations AS (
                SELECT idx.*
                FROM annotation_index idx
                WHERE idx.annotation_kind = '{_E1_ANNOTATION_KIND}'
                  AND idx.target_kind = 'session'
                  AND idx.status != 'superseded'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM annotation_index newer
                      WHERE newer.supersedes_artifact_id = idx.artifact_id
                  )
            ),
            latest_run_annotations AS (
                SELECT idx.*
                FROM annotation_index idx
                WHERE idx.annotation_kind = '{_E1_ANNOTATION_KIND}'
                  AND idx.target_kind = 'run'
                  AND idx.status != 'superseded'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM annotation_index newer
                      WHERE newer.supersedes_artifact_id = idx.artifact_id
                  )
            )
            SELECT
                runs.run_id AS run_id,
                runs.session_id AS session_id,
                runs.latest_timestamp AS latest_timestamp,
                session_annotations.artifact_id AS session_artifact_id,
                session_annotations.payload_json AS session_payload_json,
                run_annotations.artifact_id AS run_artifact_id,
                run_annotations.payload_json AS run_payload_json,
                COALESCE(run_annotations.task_family, session_annotations.task_family) AS task_family,
                COALESCE(run_annotations.task_type, session_annotations.task_type) AS task_type,
                COALESCE(
                    run_annotations.taxonomy_version,
                    session_annotations.taxonomy_version
                ) AS taxonomy_version,
                COALESCE(
                    run_annotations.task_instance_key,
                    session_annotations.task_instance_key
                ) AS task_instance_key,
                COALESCE(
                    run_annotations.task_template_hash,
                    session_annotations.task_template_hash
                ) AS task_template_hash,
                COALESCE(
                    run_annotations.verifier_name,
                    session_annotations.verifier_name
                ) AS verifier_name,
                COALESCE(
                    run_annotations.verifier_score,
                    session_annotations.verifier_score
                ) AS verifier_score,
                COALESCE(
                    run_annotations.quality_confidence,
                    session_annotations.quality_confidence
                ) AS quality_confidence,
                COALESCE(
                    run_annotations.source_channel,
                    session_annotations.source_channel
                ) AS source_channel,
                COALESCE(
                    run_annotations.annotation_version,
                    session_annotations.annotation_version
                ) AS annotation_version
            FROM runs
            LEFT JOIN latest_session_annotations AS session_annotations
                ON session_annotations.target_id = runs.session_id
            LEFT JOIN latest_run_annotations AS run_annotations
                ON run_annotations.target_id = runs.run_id
        """
        clauses = [
            "COALESCE(run_annotations.task_family, session_annotations.task_family) = ?",
            "COALESCE(run_annotations.task_type, session_annotations.task_type) = ?",
            "COALESCE(run_annotations.taxonomy_version, session_annotations.taxonomy_version) = ?",
            "COALESCE(run_annotations.task_instance_key, session_annotations.task_instance_key) IS NOT NULL",
            "COALESCE(run_annotations.task_template_hash, session_annotations.task_template_hash) IS NOT NULL",
            "COALESCE(run_annotations.verifier_name, session_annotations.verifier_name) IS NOT NULL",
            "COALESCE(run_annotations.verifier_score, session_annotations.verifier_score) IS NOT NULL",
            "COALESCE(run_annotations.quality_confidence, session_annotations.quality_confidence) IS NOT NULL",
            "COALESCE(run_annotations.source_channel, session_annotations.source_channel) IS NOT NULL",
            "COALESCE(run_annotations.annotation_version, session_annotations.annotation_version) IS NOT NULL",
        ]
        values: list[Any] = [
            *run_values,
            task_family,
            task_type,
            taxonomy_version,
        ]
        if task_instance_key is not None:
            clauses.append(
                "COALESCE(run_annotations.task_instance_key, session_annotations.task_instance_key) = ?"
            )
            values.append(task_instance_key)
        if task_template_hash is not None:
            clauses.append(
                "COALESCE(run_annotations.task_template_hash, session_annotations.task_template_hash) = ?"
            )
            values.append(task_template_hash)
        if min_quality_confidence is not None:
            clauses.append(
                "COALESCE(run_annotations.quality_confidence, session_annotations.quality_confidence) >= ?"
            )
            values.append(min_quality_confidence)
        if min_verifier_score is not None:
            clauses.append(
                "COALESCE(run_annotations.verifier_score, session_annotations.verifier_score) >= ?"
            )
            values.append(min_verifier_score)
        if source_channel is not None:
            clauses.append(
                "COALESCE(run_annotations.source_channel, session_annotations.source_channel) = ?"
            )
            values.append(source_channel)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY runs.latest_timestamp DESC, runs.run_id ASC"
        if limit is not None:
            query += " LIMIT ?"
            values.append(limit)

        with closing(self._connect()) as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._row_to_e1_candidate(row) for row in rows]

    def list_artifacts(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        artifact_ids: list[str] | None = None,
        target_ref: str | None = None,
        artifact_type: str | None = None,
        producer: str | None = None,
        version: str | None = None,
        status: str | None = None,
        latest_only: bool = False,
    ) -> list[ArtifactRecord]:
        """List artifacts filtered by session or target."""

        if artifact_ids == []:
            return []
        query = "SELECT artifacts.* FROM artifacts"
        clauses: list[str] = []
        values: list[str] = []
        if session_id is not None:
            clauses.append("artifacts.session_id = ?")
            values.append(session_id)
        if run_id is not None:
            clauses.append("artifacts.run_id = ?")
            values.append(run_id)
        if artifact_ids is not None:
            placeholders = ", ".join("?" for _ in artifact_ids)
            clauses.append(f"artifacts.artifact_id IN ({placeholders})")
            values.extend(artifact_ids)
        if target_ref is not None:
            clauses.append("artifacts.target_ref = ?")
            values.append(target_ref)
        if artifact_type is not None:
            clauses.append("artifacts.artifact_type = ?")
            values.append(artifact_type)
        if producer is not None:
            clauses.append("artifacts.producer = ?")
            values.append(producer)
        if version is not None:
            clauses.append("artifacts.version = ?")
            values.append(version)
        if status is not None:
            clauses.append("artifacts.status = ?")
            values.append(status)
        if latest_only:
            clauses.append(
                "NOT EXISTS ("
                "SELECT 1 FROM artifacts newer "
                "WHERE newer.supersedes_artifact_id = artifacts.artifact_id"
                ")"
            )
            if status is None:
                clauses.append("artifacts.status != 'superseded'")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY artifacts.created_at ASC, artifacts.seq ASC"

        with closing(self._connect()) as connection:
            rows = connection.execute(query, values).fetchall()

        return [self._row_to_artifact(row) for row in rows]

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        """Return one artifact by artifact id."""

        rows = self.list_artifacts(artifact_ids=[artifact_id])
        if not rows:
            return None
        return rows[0]

    def get_latest_session_id(self) -> str | None:
        """Return the most recently seen session id."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT session_id
                FROM facts
                ORDER BY timestamp DESC, seq DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return str(row["session_id"])

    def get_latest_run_id(self, *, session_id: str | None = None) -> str | None:
        """Return the most recently seen run id, optionally scoped to a session."""

        query = "SELECT run_id FROM facts"
        values: list[str] = []
        if session_id is not None:
            query += " WHERE session_id = ?"
            values.append(session_id)
        query += " ORDER BY timestamp DESC, seq DESC LIMIT 1"

        with closing(self._connect()) as connection:
            row = connection.execute(query, values).fetchone()
        if row is None:
            return None
        return str(row["run_id"])

    def get_session_id_for_run(self, run_id: str) -> str | None:
        """Return the session id for one run id."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT session_id
                FROM facts
                WHERE run_id = ?
                ORDER BY timestamp ASC, seq ASC
                LIMIT 1
                """,
                [run_id],
            ).fetchone()
        if row is None:
            return None
        return str(row["session_id"])

    def get_fact(self, fact_id: str) -> FactEvent | None:
        """Return one fact by fact id."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM facts
                WHERE fact_id = ?
                LIMIT 1
                """,
                [fact_id],
            ).fetchone()
        if row is None:
            return None
        return self._row_to_fact(row)

    def get_request_fact(
        self,
        *,
        session_id: str,
        run_id: str,
        request_id: str,
    ) -> FactEvent | None:
        """Return the first request_started fact for one scoped request id."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM facts
                WHERE session_id = ?
                  AND run_id = ?
                  AND request_id = ?
                  AND kind = 'request_started'
                ORDER BY timestamp ASC, seq ASC
                LIMIT 1
                """,
                [session_id, run_id, request_id],
            ).fetchone()
        if row is None:
            return None
        return self._row_to_fact(row)

    def iter_fact_body_refs(self) -> Iterable[tuple[str, dict[str, Any]]]:
        """Iterate fact-level payload sidecar references."""

        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT fact_id, payload_json
                FROM facts
                WHERE instr(payload_json, '"body_ref"') > 0
                ORDER BY seq ASC
                """
            ).fetchall()

        for row in rows:
            payload = json.loads(str(row["payload_json"]))
            body_ref = payload.get("body_ref")
            if isinstance(body_ref, dict):
                yield str(row["fact_id"]), body_ref

    def iter_sessions(self) -> Iterable[str]:
        """Iterate known session ids in recency order."""

        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT session_id, MAX(timestamp) AS latest_timestamp
                FROM facts
                GROUP BY session_id
                ORDER BY latest_timestamp DESC
                """
            ).fetchall()

        for row in rows:
            yield str(row["session_id"])

    def iter_runs(self, *, session_id: str | None = None) -> Iterable[str]:
        """Iterate known run ids in recency order, optionally scoped to a session."""

        query = """
            SELECT run_id, MAX(timestamp) AS latest_timestamp
            FROM facts
        """
        values: list[str] = []
        if session_id is not None:
            query += " WHERE session_id = ?"
            values.append(session_id)
        query += """
            GROUP BY run_id
            ORDER BY latest_timestamp DESC
        """

        with closing(self._connect()) as connection:
            rows = connection.execute(query, values).fetchall()

        for row in rows:
            yield str(row["run_id"])

    @staticmethod
    def _row_to_fact(row: sqlite3.Row) -> FactEvent:
        return FactEvent(
            fact_id=str(row["fact_id"]),
            schema_version=str(row["schema_version"]),
            run_id=str(row["run_id"]),
            session_id=str(row["session_id"]),
            request_id=row["request_id"],
            user_id=row["user_id"],
            thread_id=row["thread_id"],
            task_id=row["task_id"],
            parent_ref=row["parent_ref"],
            branch_id=row["branch_id"],
            timestamp=datetime.fromisoformat(str(row["timestamp"])),
            actor=str(row["actor"]),
            kind=str(row["kind"]),
            payload=json.loads(str(row["payload_json"])),
            metadata=json.loads(str(row["metadata_json"])),
        )

    @staticmethod
    def _row_to_artifact(row: sqlite3.Row) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id=str(row["artifact_id"]),
            schema_version=str(row["schema_version"]),
            artifact_type=str(row["artifact_type"]),
            target_ref=str(row["target_ref"]),
            producer=str(row["producer"]),
            payload=json.loads(str(row["payload_json"])),
            version=row["version"],
            session_id=row["session_id"],
            run_id=row["run_id"],
            created_at=datetime.fromisoformat(str(row["created_at"])),
            status=str(row["status"]),
            confidence=float(row["confidence"]) if row["confidence"] is not None else None,
            supersedes_artifact_id=row["supersedes_artifact_id"],
            metadata=json.loads(str(row["metadata_json"])),
        )

    @staticmethod
    def _row_to_slice(row: sqlite3.Row) -> SliceRecord:
        return SliceRecord(
            slice_id=str(row["slice_id"]),
            schema_version=str(row["schema_version"]),
            task_family=str(row["task_family"]),
            task_type=str(row["task_type"]),
            taxonomy_version=str(row["taxonomy_version"]),
            sample_unit=str(row["sample_unit"]),
            verifier_contract=str(row["verifier_contract"]),
            risk_level=str(row["risk_level"]),
            default_use=str(row["default_use"]),
            owner=str(row["owner"]),
            description=row["description"],
            created_at=datetime.fromisoformat(str(row["created_at"])),
            metadata=json.loads(str(row["metadata_json"])),
        )

    @staticmethod
    def _row_to_cohort(
        row: sqlite3.Row,
        *,
        slice_ids: list[str],
    ) -> CohortRecord:
        return CohortRecord(
            cohort_id=str(row["cohort_id"]),
            schema_version=str(row["schema_version"]),
            name=str(row["name"]),
            status=str(row["status"]),
            slice_ids=slice_ids,
            manifest=json.loads(str(row["manifest_json"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            metadata=json.loads(str(row["metadata_json"])),
        )

    @staticmethod
    def _row_to_cohort_member(row: sqlite3.Row) -> CohortMemberRecord:
        return CohortMemberRecord(
            member_id=str(row["member_id"]),
            cohort_id=str(row["cohort_id"]),
            slice_id=str(row["slice_id"]),
            session_id=str(row["session_id"]),
            run_id=str(row["run_id"]),
            annotation_artifact_id=str(row["annotation_artifact_id"]),
            task_instance_key=str(row["task_instance_key"]),
            task_template_hash=row["task_template_hash"],
            quality_confidence=(
                float(row["quality_confidence"])
                if row["quality_confidence"] is not None
                else None
            ),
            verifier_score=(
                float(row["verifier_score"]) if row["verifier_score"] is not None else None
            ),
            source_channel=row["source_channel"],
            created_at=datetime.fromisoformat(str(row["created_at"])),
            metadata=json.loads(str(row["metadata_json"])),
        )

    @staticmethod
    def _row_to_dataset_snapshot(row: sqlite3.Row) -> DatasetSnapshotRecord:
        return DatasetSnapshotRecord(
            dataset_snapshot_id=str(row["dataset_snapshot_id"]),
            schema_version=str(row["schema_version"]),
            dataset_recipe_id=str(row["dataset_recipe_id"]),
            builder=str(row["builder"]),
            sample_unit=str(row["sample_unit"]),
            cohort_id=row["cohort_id"],
            output_path=row["output_path"],
            record_count=int(row["record_count"]),
            manifest=json.loads(str(row["manifest_json"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            metadata=json.loads(str(row["metadata_json"])),
        )

    @staticmethod
    def _row_to_eval_suite(row: sqlite3.Row) -> EvalSuiteRecord:
        return EvalSuiteRecord(
            eval_suite_id=str(row["eval_suite_id"]),
            schema_version=str(row["schema_version"]),
            slice_id=str(row["slice_id"]),
            suite_kind=str(row["suite_kind"]),
            name=str(row["name"]),
            status=str(row["status"]),
            cohort_id=row["cohort_id"],
            dataset_snapshot_id=row["dataset_snapshot_id"],
            manifest=json.loads(str(row["manifest_json"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            metadata=json.loads(str(row["metadata_json"])),
        )

    @staticmethod
    def _row_to_scorecard(row: sqlite3.Row) -> ScorecardRecord:
        return ScorecardRecord(
            scorecard_id=str(row["scorecard_id"]),
            schema_version=str(row["schema_version"]),
            eval_suite_id=str(row["eval_suite_id"]),
            slice_id=str(row["slice_id"]),
            candidate_model=str(row["candidate_model"]),
            baseline_model=str(row["baseline_model"]),
            verdict=str(row["verdict"]),
            metrics=json.loads(str(row["metrics_json"])),
            thresholds=json.loads(str(row["thresholds_json"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            metadata=json.loads(str(row["metadata_json"])),
        )

    @staticmethod
    def _row_to_promotion_decision(row: sqlite3.Row) -> PromotionDecisionRecord:
        return PromotionDecisionRecord(
            promotion_decision_id=str(row["promotion_decision_id"]),
            schema_version=str(row["schema_version"]),
            slice_id=str(row["slice_id"]),
            scorecard_id=str(row["scorecard_id"]),
            stage=str(row["stage"]),
            decision=str(row["decision"]),
            coverage_policy_version=str(row["coverage_policy_version"]),
            summary=str(row["summary"]),
            rollback_conditions=json.loads(str(row["rollback_conditions_json"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            metadata=json.loads(str(row["metadata_json"])),
        )

    @staticmethod
    def _row_to_feedback_queue(row: sqlite3.Row) -> FeedbackQueueRecord:
        return FeedbackQueueRecord(
            feedback_id=str(row["feedback_id"]),
            schema_version=str(row["schema_version"]),
            slice_id=str(row["slice_id"]),
            source=str(row["source"]),
            status=str(row["status"]),
            target_ref=str(row["target_ref"]),
            reason=str(row["reason"]),
            payload=json.loads(str(row["payload_json"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            metadata=json.loads(str(row["metadata_json"])),
        )

    def _backfill_annotation_index(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT artifact_id, schema_version, artifact_type, target_ref, producer, version,
                   session_id, run_id, created_at, status, confidence,
                   supersedes_artifact_id, payload_json, metadata_json
            FROM artifacts
            WHERE artifact_type = ?
              AND artifact_id NOT IN (SELECT artifact_id FROM annotation_index)
            ORDER BY created_at ASC, seq ASC
            """,
            [_ANNOTATION_ARTIFACT_TYPE],
        ).fetchall()
        artifacts = [
            (
                self._row_to_artifact(row),
                str(row["created_at"]),
            )
            for row in rows
        ]
        self._index_annotation_artifacts(connection, artifacts)

    def _index_annotation_artifacts(
        self,
        connection: sqlite3.Connection,
        artifacts: Iterable[tuple[ArtifactRecord, str]],
    ) -> None:
        rows = []
        for artifact, created_at_iso in artifacts:
            if artifact.artifact_type != _ANNOTATION_ARTIFACT_TYPE:
                continue
            index_row = self._annotation_index_row(artifact, created_at_iso)
            if index_row is not None:
                rows.append(index_row)
        if not rows:
            return
        connection.executemany(
            """
            INSERT OR REPLACE INTO annotation_index (
                artifact_id, artifact_type, annotation_kind, target_kind, target_id, target_ref,
                session_id, run_id, created_at, status, supersedes_artifact_id,
                task_family, task_type, taxonomy_version, task_instance_key,
                task_template_hash, verifier_name, verifier_score, quality_confidence,
                source_channel, annotation_version, difficulty, teacher_model,
                policy_version, new_subtype, novel_path, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    @staticmethod
    def _annotation_index_row(
        artifact: ArtifactRecord,
        created_at_iso: str,
    ) -> tuple[Any, ...] | None:
        target_kind, target_id = SQLiteFactStore._annotation_target(artifact)
        if target_kind is None or target_id is None:
            return None
        payload = artifact.payload
        annotation_kind = payload.get("annotation_kind")
        return (
            artifact.artifact_id,
            artifact.artifact_type,
            annotation_kind if isinstance(annotation_kind, str) else None,
            target_kind,
            target_id,
            artifact.target_ref,
            artifact.session_id,
            artifact.run_id,
            created_at_iso,
            artifact.status,
            artifact.supersedes_artifact_id,
            payload.get("task_family"),
            payload.get("task_type"),
            payload.get("taxonomy_version"),
            payload.get("task_instance_key"),
            payload.get("task_template_hash"),
            payload.get("verifier_name"),
            payload.get("verifier_score"),
            payload.get("quality_confidence"),
            payload.get("source_channel"),
            payload.get("annotation_version"),
            payload.get("difficulty"),
            payload.get("teacher_model"),
            payload.get("policy_version"),
            1 if payload.get("new_subtype") is True else 0,
            1
            if payload.get("new_path") is True or payload.get("novel_path") is True
            else 0,
            json.dumps(payload, ensure_ascii=True, sort_keys=True),
        )

    @staticmethod
    def _annotation_target(artifact: ArtifactRecord) -> tuple[str | None, str | None]:
        if artifact.target_ref.startswith("run:"):
            return "run", artifact.target_ref.split(":", 1)[1]
        if artifact.target_ref.startswith("session:"):
            return "session", artifact.target_ref.split(":", 1)[1]
        if artifact.run_id is not None:
            return "run", artifact.run_id
        if artifact.session_id is not None and ":" not in artifact.target_ref:
            return "session", artifact.session_id
        return None, None

    @staticmethod
    def _row_to_e1_candidate(row: sqlite3.Row) -> dict[str, Any]:
        session_payload = (
            json.loads(str(row["session_payload_json"]))
            if row["session_payload_json"] is not None
            else {}
        )
        run_payload = (
            json.loads(str(row["run_payload_json"]))
            if row["run_payload_json"] is not None
            else {}
        )
        resolved_fields = {
            key: value
            for key, value in {**session_payload, **run_payload}.items()
            if key != "annotation_kind" and value is not None
        }
        artifact_ids = [
            artifact_id
            for artifact_id in [row["session_artifact_id"], row["run_artifact_id"]]
            if isinstance(artifact_id, str) and artifact_id
        ]
        return {
            "run_id": str(row["run_id"]),
            "session_id": str(row["session_id"]),
            "latest_timestamp": str(row["latest_timestamp"]),
            "artifact_ids": artifact_ids,
            "fields": resolved_fields,
        }
