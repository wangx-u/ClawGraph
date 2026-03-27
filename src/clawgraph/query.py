"""Programmatic query helpers for ClawGraph scopes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from clawgraph.protocol.models import ArtifactRecord, FactEvent
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
