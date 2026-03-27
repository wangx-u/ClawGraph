"""Local spillover storage for oversized proxy payloads."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from clawgraph.store import parse_store_uri

_MANAGED_ROOT_MARKER = ".clawgraph-payload-root"
_TEMP_FILE_PREFIX = ".tmp-"
_MANAGED_FILE_SUFFIXES = (".sse.gz", ".json.gz", ".txt.gz", ".bin.gz")
_DEFAULT_GC_GRACE_SECONDS = 300


def default_payload_dir(store_uri: str) -> Path:
    """Derive a local payload directory from the sqlite store path."""

    store_path = parse_store_uri(store_uri)
    stem = store_path.stem or store_path.name or "clawgraph"
    return store_path.parent / f"{stem}.payloads"


def _safe_segment(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in value
    )
    cleaned = cleaned.strip("._")
    return cleaned or "unknown"


def _suffix_for_content_type(content_type: str) -> str:
    lower = content_type.lower()
    if "event-stream" in lower:
        return ".sse.gz"
    if "json" in lower:
        return ".json.gz"
    if lower.startswith("text/"):
        return ".txt.gz"
    return ".bin.gz"


class LocalPayloadWriter:
    """Incrementally write a payload blob to local compressed storage."""

    def __init__(
        self,
        *,
        root_dir: Path,
        relative_path: Path,
        content_type: str,
        temp_path: Path,
        raw_handle: Any,
        gzip_handle: gzip.GzipFile,
    ) -> None:
        self._root_dir = root_dir
        self._relative_path = relative_path
        self._content_type = content_type
        self._temp_path = temp_path
        self._raw_handle = raw_handle
        self._gzip_handle = gzip_handle
        self._sha256 = hashlib.sha256()
        self._raw_size = 0
        self._closed = False
        self._discarded = False
        self._body_ref: dict[str, Any] | None = None

    def write(self, chunk: bytes) -> None:
        if self._closed:
            raise ValueError("payload writer is already closed")
        self._raw_size += len(chunk)
        self._sha256.update(chunk)
        self._gzip_handle.write(chunk)

    def commit(self) -> dict[str, Any]:
        if self._discarded:
            raise ValueError("cannot commit a discarded payload writer")
        if self._body_ref is not None:
            return dict(self._body_ref)

        self._close_handles()
        compressed_size = self._temp_path.stat().st_size
        final_path = self._root_dir / self._relative_path
        final_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(self._temp_path, final_path)
        self._body_ref = {
            "storage": "local_file",
            "relative_path": str(self._relative_path),
            "encoding": "gzip",
            "content_type": self._content_type,
            "byte_size": self._raw_size,
            "compressed_size": compressed_size,
            "sha256": self._sha256.hexdigest(),
        }
        return dict(self._body_ref)

    def discard(self) -> None:
        if self._discarded:
            return
        self._close_handles()
        self._temp_path.unlink(missing_ok=True)
        self._discarded = True

    def _close_handles(self) -> None:
        if self._closed:
            return
        try:
            self._gzip_handle.close()
        finally:
            try:
                self._raw_handle.close()
            finally:
                self._closed = True


class LocalPayloadStore:
    """Persist oversized payloads to local gzip-compressed sidecar files."""

    def __init__(
        self,
        *,
        root_dir: str | Path | None = None,
        store_uri: str | None = None,
    ) -> None:
        if root_dir is None:
            if store_uri is None:
                raise ValueError("store_uri is required when payload_dir is not configured")
            resolved_root = default_payload_dir(store_uri)
        else:
            resolved_root = Path(root_dir).expanduser()

        self.root_dir = resolved_root
        self._marker_path = self.root_dir / _MANAGED_ROOT_MARKER

    def _ensure_managed_root(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        if self._marker_path.exists():
            return
        marker_payload = {
            "format": "clawgraph-payload-root",
            "version": 1,
        }
        self._marker_path.write_text(
            json.dumps(marker_payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _is_managed_payload_path(self, path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            relative_path = path.resolve().relative_to(self.root_dir.resolve())
        except ValueError:
            return False
        if len(relative_path.parts) < 4:
            return False
        name = relative_path.name
        if name == _MANAGED_ROOT_MARKER or name.startswith(_TEMP_FILE_PREFIX):
            return False
        return any(name.endswith(suffix) for suffix in _MANAGED_FILE_SUFFIXES)

    def resolve_body_path(
        self,
        body_ref: dict[str, Any],
        *,
        require_within_root: bool = True,
    ) -> Path:
        """Resolve a stored body reference to a concrete path."""

        if body_ref.get("storage") != "local_file":
            raise ValueError("unsupported payload storage backend")

        relative_path = body_ref.get("relative_path")
        absolute_path = body_ref.get("path")
        candidate: Path | None = None
        if isinstance(relative_path, str) and relative_path:
            candidate = (self.root_dir / relative_path).expanduser()
        elif isinstance(absolute_path, str) and absolute_path:
            candidate = Path(absolute_path).expanduser()
        if candidate is None:
            raise ValueError("body_ref does not include a readable path")

        resolved = candidate.resolve()
        if require_within_root:
            root = self.root_dir.resolve()
            if resolved != root and root not in resolved.parents:
                raise ValueError("body_ref path escapes the payload root")
        return resolved

    def read_bytes(self, body_ref: dict[str, Any]) -> bytes:
        """Read one spilled payload back into memory."""

        resolved = self.resolve_body_path(body_ref, require_within_root=True)
        try:
            with gzip.open(resolved, "rb") as handle:
                body = handle.read()
        except FileNotFoundError as exc:
            raise ValueError(f"payload body not found: {resolved}") from exc
        except PermissionError as exc:
            raise ValueError(f"payload body is not readable: {resolved}") from exc
        except OSError as exc:
            raise ValueError(f"payload body could not be decoded: {resolved}") from exc

        expected_size = body_ref.get("byte_size")
        if expected_size is not None and expected_size != len(body):
            raise ValueError(
                f"payload body size mismatch for {resolved}: expected {expected_size}, got {len(body)}"
            )
        expected_sha256 = body_ref.get("sha256")
        if isinstance(expected_sha256, str):
            actual_sha256 = hashlib.sha256(body).hexdigest()
            if actual_sha256 != expected_sha256:
                raise ValueError(f"payload body sha256 mismatch for {resolved}")
        return body

    def garbage_collect(
        self,
        *,
        referenced_body_refs: Iterable[dict[str, Any]],
        dry_run: bool = False,
        grace_period_seconds: int = _DEFAULT_GC_GRACE_SECONDS,
    ) -> dict[str, Any]:
        """Delete local payload files that are no longer referenced by facts."""

        if grace_period_seconds < 0:
            raise ValueError("grace_period_seconds must be non-negative")
        if not self.root_dir.exists():
            return {
                "root_dir": str(self.root_dir),
                "managed_root": False,
                "dry_run": dry_run,
                "grace_period_seconds": grace_period_seconds,
                "referenced_files": 0,
                "referenced_outside_root": 0,
                "scanned_files": 0,
                "managed_files": 0,
                "skipped_unmanaged_files": 0,
                "orphan_files": 0,
                "skipped_recent_files": 0,
                "would_delete_files": 0,
                "would_delete_bytes": 0,
                "deleted_files": 0,
                "deleted_bytes": 0,
            }
        scanned_files = [path for path in self.root_dir.rglob("*") if path.is_file()]
        if not self._marker_path.exists():
            if scanned_files:
                raise ValueError(
                    "payload root is not managed by ClawGraph; refusing to garbage-collect"
                )
            return {
                "root_dir": str(self.root_dir),
                "managed_root": False,
                "dry_run": dry_run,
                "grace_period_seconds": grace_period_seconds,
                "referenced_files": 0,
                "referenced_outside_root": 0,
                "scanned_files": 0,
                "managed_files": 0,
                "skipped_unmanaged_files": 0,
                "orphan_files": 0,
                "skipped_recent_files": 0,
                "would_delete_files": 0,
                "would_delete_bytes": 0,
                "deleted_files": 0,
                "deleted_bytes": 0,
            }

        root = self.root_dir.resolve()
        referenced_paths: set[Path] = set()
        referenced_outside_root = 0
        for body_ref in referenced_body_refs:
            try:
                resolved = self.resolve_body_path(body_ref, require_within_root=False)
            except ValueError:
                continue
            if resolved == root or root in resolved.parents:
                referenced_paths.add(resolved)
            else:
                referenced_outside_root += 1

        managed_files = [path for path in scanned_files if self._is_managed_payload_path(path)]
        orphan_files = [path for path in managed_files if path.resolve() not in referenced_paths]
        now = time.time()
        eligible_orphans: list[Path] = []
        skipped_recent_files = 0
        for orphan in orphan_files:
            age_seconds = max(0.0, now - orphan.stat().st_mtime)
            if age_seconds < grace_period_seconds:
                skipped_recent_files += 1
                continue
            eligible_orphans.append(orphan)

        would_delete_files = len(eligible_orphans)
        would_delete_bytes = sum(path.stat().st_size for path in eligible_orphans)
        deleted_files = 0
        deleted_bytes = 0
        for orphan in eligible_orphans:
            size = orphan.stat().st_size
            if not dry_run:
                orphan.unlink(missing_ok=True)
                deleted_files += 1
                deleted_bytes += size

        return {
            "root_dir": str(self.root_dir),
            "managed_root": True,
            "dry_run": dry_run,
            "grace_period_seconds": grace_period_seconds,
            "referenced_files": len(referenced_paths),
            "referenced_outside_root": referenced_outside_root,
            "scanned_files": len(scanned_files),
            "managed_files": len(managed_files),
            "skipped_unmanaged_files": len(scanned_files) - len(managed_files),
            "orphan_files": len(orphan_files),
            "skipped_recent_files": skipped_recent_files,
            "would_delete_files": would_delete_files,
            "would_delete_bytes": would_delete_bytes,
            "deleted_files": deleted_files,
            "deleted_bytes": deleted_bytes,
        }

    def write_bytes(
        self,
        *,
        session_id: str,
        run_id: str,
        request_id: str,
        body_kind: str,
        request_path: str,
        content_type: str,
        body: bytes,
    ) -> dict[str, Any]:
        self._ensure_managed_root()
        writer = self.start_writer(
            session_id=session_id,
            run_id=run_id,
            request_id=request_id,
            body_kind=body_kind,
            request_path=request_path,
            content_type=content_type,
        )
        writer.write(body)
        return writer.commit()

    def start_writer(
        self,
        *,
        session_id: str,
        run_id: str,
        request_id: str,
        body_kind: str,
        request_path: str,
        content_type: str,
    ) -> LocalPayloadWriter:
        self._ensure_managed_root()
        safe_content_type = content_type or "application/octet-stream"
        suffix = _suffix_for_content_type(safe_content_type)
        endpoint_hint = _safe_segment(request_path.strip("/") or "root")
        relative_path = (
            Path(_safe_segment(session_id))
            / _safe_segment(run_id)
            / _safe_segment(request_id)
            / f"{_safe_segment(body_kind)}-{endpoint_hint}-{uuid4().hex}{suffix}"
        )
        file_descriptor, temp_name = tempfile.mkstemp(
            dir=self.root_dir,
            prefix=_TEMP_FILE_PREFIX,
            suffix=suffix,
        )
        os.close(file_descriptor)
        raw_handle = open(temp_name, "wb")
        gzip_handle = gzip.GzipFile(fileobj=raw_handle, mode="wb", mtime=0)
        return LocalPayloadWriter(
            root_dir=self.root_dir,
            relative_path=relative_path,
            content_type=safe_content_type,
            temp_path=Path(temp_name),
            raw_handle=raw_handle,
            gzip_handle=gzip_handle,
        )
