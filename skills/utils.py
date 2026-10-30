import re
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from selectolax.lexbor import LexborHTMLParser

from skills.config import HTTP_TIMEOUT, random_headers

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
WIKIPEDIA_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary"


async def fetch_url(url: str, max_chars: int = 5000) -> str:
    """Fetch a specific URL and return its readable text content (no JS rendering).

    Use this to read a page you already have the address for (e.g. a link
    returned by web_search or search_news). For pages that require JavaScript
    to render, use the browse tool instead.
    """
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url, headers=random_headers())
        resp.raise_for_status()

    tree = LexborHTMLParser(resp.text)
    for tag in tree.css("script, style, noscript"):
        tag.decompose()

    text = tree.body.text(separator=" ", strip=True) if tree.body else tree.text(strip=True)
    text = " ".join(text.split())
    if len(text) > max_chars:
        text = text[:max_chars] + f"... [truncated, {len(text)} chars total]"
    return text or "(no readable text found)"


def get_time(timezone: str = "UTC") -> str:
    """Get the current date/time in a given IANA timezone (e.g. 'America/New_York', 'Asia/Tokyo')."""
    try:
        now = datetime.now(ZoneInfo(timezone))
    except ZoneInfoNotFoundError:
        return f"error: unknown timezone '{timezone}' (use an IANA name, e.g. 'Europe/London')"
    return now.strftime(f"%Y-%m-%d %H:%M:%S %Z ({timezone})")


async def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert an amount between currencies using ECB daily reference rates (Frankfurter)."""
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(
            FRANKFURTER_URL,
            params={"amount": amount, "base": from_currency, "symbols": to_currency},
        )
        resp.raise_for_status()
        data = resp.json()

    rate = data.get("rates", {}).get(to_currency)
    if rate is None:
        return f"error: could not convert {from_currency} -> {to_currency}"
    return f"{amount} {from_currency} = {rate} {to_currency} (as of {data['date']}, ECB reference rate)"


async def get_crypto_price(coin_id: str, vs_currency: str = "usd") -> str:
    """Get the current price of a cryptocurrency (CoinGecko coin id, e.g. 'bitcoin', 'ethereum')."""
    coin_id = coin_id.lower()
    vs_currency = vs_currency.lower()
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(COINGECKO_URL, params={"ids": coin_id, "vs_currencies": vs_currency})
        resp.raise_for_status()
        data = resp.json()

    price = data.get(coin_id, {}).get(vs_currency)
    if price is None:
        return f"error: no price found for '{coin_id}' in '{vs_currency}' (check the CoinGecko coin id)"
    return f"{coin_id}: {price} {vs_currency.upper()}"


async def wikipedia_lookup(query: str, sentences: int = 3) -> str:
    """Look up a topic on Wikipedia and return a short summary with the article URL."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        search_resp = await client.get(
            WIKIPEDIA_SEARCH_URL,
            params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 1},
            headers=random_headers(),
        )
        search_resp.raise_for_status()
        results = search_resp.json().get("query", {}).get("search", [])
        if not results:
            return f"No Wikipedia article found for: {query}"
        title = results[0]["title"]

        summary_resp = await client.get(f"{WIKIPEDIA_SUMMARY_URL}/{quote(title)}", headers=random_headers())
        summary_resp.raise_for_status()
        data = summary_resp.json()

    extract = data.get("extract", "")
    summary = " ".join(re.split(r"(?<=[.!?])\s+", extract)[:sentences])
    url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
    return f"{data.get('title', title)}\n{summary}\n{url}"


def register(mcp):
    mcp.tool()(fetch_url)
    mcp.tool()(get_time)
    mcp.tool()(convert_currency)
    mcp.tool()(get_crypto_price)
    mcp.tool()(wikipedia_lookup)
