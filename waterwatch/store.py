"""Persistence for complaints and the civic (pincode) index — the memory layer.

Default backend is a local JSON file (zero-setup, used for the offline demo and tests).
A Firestore backend is selected with ``STORE_BACKEND=firestore`` for the live GCP
deployment described in the plan. Both expose the same interface.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get_settings
from .exceptions import StoreError

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalStore:
    """File-backed JSON store. Writes are serialised with a lock and written atomically."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        if not self._path.exists():
            self._write({"complaints": {}})

    def _read(self) -> dict[str, Any]:
        try:
            with self._path.open(encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"complaints": {}}

    def _write(self, data: dict[str, Any]) -> None:
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        tmp.replace(self._path)

    def save_complaint(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            data["complaints"][record["id"]] = record
            self._write(data)
            return record

    def get_complaint(self, complaint_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._read()["complaints"].get(complaint_id)

    def list_complaints(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(
                self._read()["complaints"].values(),
                key=lambda r: r.get("created_at", ""),
                reverse=True,
            )

    def update_complaint(self, complaint_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            record = data["complaints"].get(complaint_id)
            if record is None:
                raise StoreError(f"complaint not found: {complaint_id}")
            record.update(changes)
            record["updated_at"] = _now_iso()
            self._write(data)
            return record

    def add_event(self, complaint_id: str, event: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            record = data["complaints"].get(complaint_id)
            if record is None:
                raise StoreError(f"complaint not found: {complaint_id}")
            record.setdefault("events", []).append({**event, "at": _now_iso()})
            record["updated_at"] = _now_iso()
            self._write(data)
            return record


class FirestoreStore:  # pragma: no cover - exercised only on GCP
    """Firestore-backed store for the live deployment."""

    def __init__(self, project: str | None) -> None:
        from google.cloud import firestore  # type: ignore

        self._db = firestore.Client(project=project)
        self._col = self._db.collection("waterwatch_complaints")

    def save_complaint(self, record: dict[str, Any]) -> dict[str, Any]:
        self._col.document(record["id"]).set(record)
        return record

    def get_complaint(self, complaint_id: str) -> dict[str, Any] | None:
        doc = self._col.document(complaint_id).get()
        return doc.to_dict() if doc.exists else None

    def list_complaints(self) -> list[dict[str, Any]]:
        return [d.to_dict() for d in self._col.order_by("created_at", direction="DESCENDING").stream()]

    def update_complaint(self, complaint_id: str, **changes: Any) -> dict[str, Any]:
        ref = self._col.document(complaint_id)
        changes["updated_at"] = _now_iso()
        ref.update(changes)
        return ref.get().to_dict()  # type: ignore[return-value]

    def add_event(self, complaint_id: str, event: dict[str, Any]) -> dict[str, Any]:
        from google.cloud import firestore  # type: ignore

        ref = self._col.document(complaint_id)
        ref.update(
            {
                "events": firestore.ArrayUnion([{**event, "at": _now_iso()}]),
                "updated_at": _now_iso(),
            }
        )
        return ref.get().to_dict()  # type: ignore[return-value]


_store: LocalStore | FirestoreStore | None = None


def get_store() -> LocalStore | FirestoreStore:
    """Return the configured store singleton."""
    global _store
    if _store is not None:
        return _store
    settings = get_settings()
    if settings.store_backend == "firestore":
        try:
            _store = FirestoreStore(settings.firestore_project)
            logger.info("Using Firestore store (project=%s).", settings.firestore_project)
            return _store
        except Exception as exc:  # pragma: no cover
            logger.warning("Firestore unavailable, falling back to local store: %s", exc)
    _store = LocalStore(settings.local_store_path)
    logger.info("Using local JSON store at %s.", settings.local_store_path)
    return _store


def reset_store_for_tests(path: Path) -> LocalStore:
    """Helper for tests: bind a fresh local store to a temp path."""
    global _store
    _store = LocalStore(path)
    return _store
