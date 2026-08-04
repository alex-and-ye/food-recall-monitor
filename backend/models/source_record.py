"""In-flight source record shape used during agent processing.

Holds the originating source name plus raw and working JSON payloads as
pipeline nodes transform a scraped item.
"""

from typing import Any

from pydantic import BaseModel

class SourceRecord(BaseModel):
    """Mutable working copy of a scraped source payload during agent steps."""

    source: str
    raw_record: dict[str, Any]
    working_json: dict[str, Any]
