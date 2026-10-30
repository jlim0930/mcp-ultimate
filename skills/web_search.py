import os

import httpx

from skills.config import HTTP_TIMEOUT, SEARCH_PREFER_BROWSER, random_headers
from skills.search_engines import bing_web_search

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://192.168.1.20:8080").rstrip("/")


async def _searxng_web_search(query: str, max_results: int) -> list[dict]:
    params = {"q": query, "format": "json"}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(f"{SEARXNG_URL}/search", params=params, headers=random_headers())
        resp.raise_for_status()
        data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in data.get("results", [])[:max_results]
    ]


def _format(results: list[dict]) -> str:
    lines = [f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}" for i, r in enumerate(results, 1)]
    return "\n\n".join(lines)


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web.

    Tries Bing (scraped directly -- HTTP first, headless browser as a
    fallback) before your SearXNG instance by default; set
    SEARCH_PREFER_BROWSER=false to reverse that order (SearXNG first,
    faster and self-hosted, with Bing as the fallback instead).
    """
    order = (
        [("bing", bing_web_search), ("searxng", _searxng_web_search)]
        if SEARCH_PREFER_BROWSER
        else [("searxng", _searxng_web_search), ("bing", bing_web_search)]
    )

    errors = []
    for name, fn in order:
        try:
            results = await fn(query, max_results)
            if results:
                return _format(results)
            errors.append(f"{name}: no results")
        except Exception as e:
            errors.append(f"{name}: {e}")

    return f"No results found for: {query}\n" + "\n".join(errors)


def register(mcp):
    mcp.tool()(web_search)
