from __future__ import annotations

from typing import Any, Protocol


class ProgressReporter(Protocol):
    def log(
        self,
        *,
        stage: str,
        message: str,
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        ...
