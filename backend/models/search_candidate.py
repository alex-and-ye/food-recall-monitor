from __future__ import annotations

import hashlib
import ipaddress
import posixpath
from datetime import datetime
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, Field, field_validator

_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref",
    "ref_src",
}
_TRACKING_QUERY_PREFIXES = ("utm_",)

def canonicalize_url(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("URL must be non-empty")
    parsed = urlsplit(text)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("URL scheme must be http or https")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must not contain user information")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must contain a hostname")
    try:
        ascii_hostname = hostname.rstrip(".").encode("idna").decode("ascii").lower()
        port = parsed.port
    except (UnicodeError, ValueError) as exc:
        raise ValueError("URL contains an invalid hostname or port") from exc
    if not ascii_hostname:
        raise ValueError("URL must contain a hostname")
    if ascii_hostname == "localhost" or ascii_hostname.endswith((".localhost", ".local")):
        raise ValueError("URL must not target a local hostname")
    try:
        address = ipaddress.ip_address(ascii_hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("URL must target a public IP address")
    netloc = ascii_hostname
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{netloc}:{port}"

    raw_path = parsed.path or "/"
    normalized_path = posixpath.normpath(raw_path)
    if raw_path.startswith("/") and not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    if normalized_path == "/.":
        normalized_path = "/"
    if normalized_path != "/":
        normalized_path = normalized_path.rstrip("/")
    normalized_path = quote(normalized_path, safe="/:@-._~!$&'()*+,;=%")

    query_items = [
        (key, item_value)
        for key, item_value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS
        and not key.lower().startswith(_TRACKING_QUERY_PREFIXES)
    ]
    query_items.sort(key=lambda item: (item[0].casefold(), item[1]))
    query = urlencode(query_items, doseq=True)
    return urlunsplit((scheme, netloc, normalized_path, query, ""))

def stable_search_id(*parts: str) -> str:
    payload = "\0".join(part.strip() for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

class SearchQuery(BaseModel):
    query_id: str
    text: str = Field(min_length=1)
    country: str = Field(min_length=2, max_length=2)
    language: str = Field(min_length=2, max_length=3)
    domain: str | None = None

    @classmethod
    def create(
        cls,
        *,
        text: str,
        country: str,
        language: str,
        domain: str | None = None,
    ) -> SearchQuery:
        normalized_text = " ".join(text.split())
        normalized_country = country.strip().upper()
        normalized_language = language.strip().lower()
        normalized_domain = domain.strip().lower() if domain else None
        return cls(
            query_id=stable_search_id(
                normalized_text,
                normalized_country,
                normalized_language,
                normalized_domain or "",
            ),
            text=normalized_text,
            country=normalized_country,
            language=normalized_language,
            domain=normalized_domain,
        )

class SearchCandidate(BaseModel):
    title: str = Field(min_length=1)
    url: str
    description: str = ""
    age: str | None = None
    page_age: datetime | None = None
    rank: int = Field(ge=1)
    query_id: str
    query: str
    country: str
    language: str

    @field_validator("title", "description", "age", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> str | None:
        if value is None:
            return None
        return str(value).strip()

    @field_validator("url", mode="before")
    @classmethod
    def _validate_url(cls, value: object) -> str:
        return canonicalize_url(str(value))

class SearchResponse(BaseModel):
    query: SearchQuery
    candidates: list[SearchCandidate] = Field(default_factory=list)
    total_count: int | None = Field(default=None, ge=0)
    offset: int = Field(default=0, ge=0, le=9)
    more_results_available: bool = False
