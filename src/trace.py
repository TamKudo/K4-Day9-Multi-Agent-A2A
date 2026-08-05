"""Trace sink owned by the release layer. Implements the TraceSink protocol."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Dict, List, Optional, Type


class JsonlTrace:
    """Append-per-run trace writer.

    The submitted ``trace.jsonl`` must hold the latest run only, so the file is
    truncated on open rather than appended across runs.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: Optional[IO[str]] = None

    def __enter__(self) -> "JsonlTrace":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", encoding="utf-8", newline="\n")
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()

    def record(self, case_id: str, agent: str, event: str, **details: object) -> None:
        if self._handle is None:
            raise RuntimeError("trace used outside of its context manager")
        entry: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "case_id": case_id,
            "agent": agent,
            "event": event,
        }
        if details:
            entry["details"] = details
        self._handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._handle.flush()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


class MemoryTrace:
    """In-memory sink for tests and dry runs."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def record(self, case_id: str, agent: str, event: str, **details: object) -> None:
        self.events.append(
            {"case_id": case_id, "agent": agent, "event": event, "details": details}
        )
