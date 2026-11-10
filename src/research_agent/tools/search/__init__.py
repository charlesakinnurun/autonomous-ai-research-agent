"""Search adapters."""

from research_agent.tools.search.arxiv import ArxivSearchAdapter
from research_agent.tools.search.base import CachedSearchAdapter, SearchAdapter
from research_agent.tools.search.searxng import SearXNGSearchAdapter
from research_agent.tools.search.wikipedia import WikipediaSearchAdapter

__all__ = [
    "ArxivSearchAdapter",
    "CachedSearchAdapter",
    "SearXNGSearchAdapter",
    "SearchAdapter",
    "WikipediaSearchAdapter",
]
