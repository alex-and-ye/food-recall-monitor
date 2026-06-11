from __future__ import annotations

class SourceFetchError(Exception):
    def __init__(self, failures: dict[str, str]) -> None:
        self.failures = failures
        super().__init__(_format_failures(failures))

def _format_failures(failures: dict[str, str]) -> str:
    details = "; ".join(f"{source}: {error}" for source, error in failures.items())
    return f"Failed to fetch requested source(s): {details}"
