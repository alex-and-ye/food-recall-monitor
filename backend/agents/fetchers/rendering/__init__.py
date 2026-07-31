"""Page rendering fetchers for static HTTP and browser-based retrieval.

Re-exports helpers that download recall source pages as HTML, either via a
plain HTTP client or a headless Chromium browser when JavaScript is required.
"""

from agents.fetchers.rendering.browser_fetch import fetch_browser_html
from agents.fetchers.rendering.static_fetch import fetch_static_html

__all__ = [
    "fetch_browser_html",
    "fetch_static_html",
]
