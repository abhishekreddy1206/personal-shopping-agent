"""Deprecated module.

The previous `LiveBestBuySearchAdapter` class is removed; the live Best Buy lane is
constructed from `GenericRetailLiveAdapter` inside `SourceRegistry`. The shared helper
`extract_bestbuy_candidate` now lives in `app.sources.search_utils` so existing tests
keep working. Re-exported here as a thin alias for any external caller still importing
from this path.
"""

from app.sources.search_utils import extract_bestbuy_candidate  # noqa: F401

__all__ = ["extract_bestbuy_candidate"]
