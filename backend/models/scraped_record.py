"""Scraped official-source recall record model.

Holds the source name and raw payload produced by a scraper before agent
processing.
"""

from typing import Any

from pydantic import BaseModel

class ScrapedRecallRecord(BaseModel):
    """A single recall page/payload scraped from an official source."""

    source_name: str
    payload: dict[str, Any]
