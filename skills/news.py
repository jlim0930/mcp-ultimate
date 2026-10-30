import os
import re

import httpx

from skills.config import HTTP_TIMEOUT, SEARCH_PREFER_BROWSER, random_headers
from skills.search_engines import bing_news_search

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://searxng.local:8080").rstrip("/")


def _one_sentence(text: str, max_len: int = 200) -> str:
    text = " ".join(text.split())
    if not text:
        return ""
    match = re.search(r"(.+?[.!?])(\s|$)", text)
    sentence = match.group(1) if match else text
    if len(sentence) > max_len:
        sentence = sentence[:max_len].rsplit(" ", 1)[0] + "..."
    return sentence


async def _searxng_news_search(query: str, max_results: int) -> list[dict]:
    params = {"q": query, "format": "json", "categories": "news"}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(f"{SEARXNG_URL}/search", params=params, headers=random_headers())
        resp.raise_for_status()
        data = resp.json()
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "source": r.get("engine") or "",
            "published": r.get("publishedDate") or "",
            "content": r.get("content", ""),
        }
        for r in data.get("results", [])[:max_results]
    ]


def _format(results: list[dict]) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        summary = _one_sentence(r.get("content", "") or r["title"])
        meta = " | ".join(filter(None, [r.get("source", ""), r.get("published", "")]))
        header = f"{i}. {r['title']}" + (f" ({meta})" if meta else "")
        # Bing News cards carry no snippet, so the "summary" would just repeat
        # the title verbatim -- skip that line rather than show the duplicate.
        body = f"\n   {summary}" if summary and summary != r["title"] else ""
        lines.append(f"{header}{body}\n   {r['url']}")
    return "\n\n".join(lines)


def register(mcp):
    @mcp.tool()
    async def search_news(query: str, max_results: int = 5) -> str:
        """Search recent news.

        Tries Bing News (scraped directly -- HTTP first, headless browser as
        a fallback) before your SearXNG instance by default; set
        SEARCH_PREFER_BROWSER=false to reverse that order (SearXNG first,
        faster and self-hosted, with Bing News as the fallback instead).
        """
        order = (
            [("bing", bing_news_search), ("searxng", _searxng_news_search)]
            if SEARCH_PREFER_BROWSER
            else [("searxng", _searxng_news_search), ("bing", bing_news_search)]
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

        return f"No news found for: {query}\n" + "\n".join(errors)
