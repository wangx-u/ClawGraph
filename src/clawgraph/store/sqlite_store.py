"""SQLite-backed append-only fact store for ClawGraph."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from clawgraph.protocol.models import ArtifactRecord, FactEvent


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
    else:
        resolved = Path(path.lstrip("/"))

    return resolved.expanduser()


class SQLiteFactStore:
    """Append-only fact store backed by sqlite."""

    def __init__(self, store_uri: str) -> None:
        self.store_uri = store_uri
        self.path = parse_store_uri(store_uri)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with closing(self._connect()) as connection:
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

        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO facts (
                    fact_id, schema_version, run_id, session_id, request_id,
                    user_id, thread_id,
                    task_id, parent_ref, branch_id, timestamp, actor, kind,
                    payload_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
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
                ),
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

    def append_artifact(self, artifact: ArtifactRecord) -> None:
        """Persist an external supervision artifact."""

        created_at = artifact.created_at or datetime.now().astimezone()
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO artifacts (
                    artifact_id, schema_version, artifact_type, target_ref, producer,
                    version, session_id, run_id, created_at, status, confidence,
                    supersedes_artifact_id, payload_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.artifact_id,
                    artifact.schema_version,
                    artifact.artifact_type,
                    artifact.target_ref,
                    artifact.producer,
                    artifact.version,
                    artifact.session_id,
                    artifact.run_id,
                    created_at.isoformat(),
                    artifact.status,
                    artifact.confidence,
                    artifact.supersedes_artifact_id,
                    json.dumps(artifact.payload, ensure_ascii=True, sort_keys=True),
                    json.dumps(artifact.metadata, ensure_ascii=True, sort_keys=True),
                ),
            )
            connection.commit()

    def list_artifacts(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        target_ref: str | None = None,
        artifact_type: str | None = None,
        producer: str | None = None,
        version: str | None = None,
        status: str | None = None,
        latest_only: bool = False,
    ) -> list[ArtifactRecord]:
        """List artifacts filtered by session or target."""

        query = "SELECT * FROM artifacts"
        clauses: list[str] = []
        values: list[str] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            values.append(session_id)
        if run_id is not None:
            clauses.append("run_id = ?")
            values.append(run_id)
        if target_ref is not None:
            clauses.append("target_ref = ?")
            values.append(target_ref)
        if artifact_type is not None:
            clauses.append("artifact_type = ?")
            values.append(artifact_type)
        if producer is not None:
            clauses.append("producer = ?")
            values.append(producer)
        if version is not None:
            clauses.append("version = ?")
            values.append(version)
        if status is not None:
            clauses.append("status = ?")
            values.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at ASC, seq ASC"

        with closing(self._connect()) as connection:
            rows = connection.execute(query, values).fetchall()

        artifacts = [self._row_to_artifact(row) for row in rows]
        if latest_only:
            superseded_ids = {
                artifact.supersedes_artifact_id
                for artifact in artifacts
                if artifact.supersedes_artifact_id is not None
            }
            filtered = [
                artifact
                for artifact in artifacts
                if artifact.artifact_id not in superseded_ids
                and (status is not None or artifact.status != "superseded")
            ]
            return filtered
        return artifacts

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
