import base64
import urllib.parse

import httpx
from playwright.async_api import async_playwright
from selectolax.lexbor import LexborHTMLParser

from skills.config import BROWSER_TIMEOUT_MS, HTTP_TIMEOUT, random_headers, random_user_agent


def _clean(text: str) -> str:
    return " ".join(text.split())


def _decode_bing_redirect(href: str) -> str:
    """Bing wraps result links in a /ck/a redirect; the real URL is base64 in u=a1<base64>."""
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        u = qs.get("u", [""])[0]
        if u.startswith("a1"):
            u = u[2:]
            u += "=" * (-len(u) % 4)
            return base64.urlsafe_b64decode(u).decode("utf-8", errors="ignore")
    except Exception:
        pass
    return href


def _parse_bing_web_html(html: str, max_results: int) -> list[dict]:
    tree = LexborHTMLParser(html)
    results = []
    for node in tree.css("li.b_algo")[:max_results]:
        a = node.css_first("h2 a")
        if not a:
            continue
        href = a.attributes.get("href") or ""
        snip = node.css_first(".b_caption p") or node.css_first(".b_lineclamp2") or node.css_first("p")
        results.append(
            {
                "title": _clean(a.text(separator=" ", strip=True)),
                "url": _decode_bing_redirect(href),
                "snippet": _clean(snip.text(separator=" ", strip=True)) if snip else "",
            }
        )
    return results


def _parse_bing_news_html(html: str, max_results: int) -> list[dict]:
    tree = LexborHTMLParser(html)
    results = []
    for node in tree.css(".news-card")[:max_results]:
        url = node.attributes.get("url") or node.attributes.get("data-url") or ""
        if not url:
            continue
        results.append(
            {
                "title": _clean(node.attributes.get("data-title") or ""),
                "url": url,
                "source": node.attributes.get("data-author") or "",
            }
        )
    return results


async def _fetch_html_http(url: str) -> str:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url, headers=random_headers())
        resp.raise_for_status()
        return resp.text


async def _fetch_html_browser(url: str) -> str:
    headers = random_headers()
    user_agent = headers.pop("User-Agent")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(user_agent=user_agent, extra_http_headers=headers)
            await page.goto(url, wait_until="networkidle", timeout=BROWSER_TIMEOUT_MS)
            return await page.content()
        finally:
            await browser.close()


async def bing_web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search Bing for `query`. Tries a plain HTTP request first (fast, no
    browser needed -- Bing's results are server-rendered); falls back to
    rendering with headless Chromium only if that returns nothing parseable.
    Raises on hard network failure; returns [] if nothing parses either way.
    """
    url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
    results = _parse_bing_web_html(await _fetch_html_http(url), max_results)
    if results:
        return results
    return _parse_bing_web_html(await _fetch_html_browser(url), max_results)


async def bing_news_search(query: str, max_results: int = 5) -> list[dict]:
    """Search Bing News for `query`. Same two-tier (HTTP then browser) strategy as bing_web_search."""
    url = f"https://www.bing.com/news/search?q={urllib.parse.quote(query)}"
    results = _parse_bing_news_html(await _fetch_html_http(url), max_results)
    if results:
        return results
    return _parse_bing_news_html(await _fetch_html_browser(url), max_results)


# --- Kayak ---
#
# Unlike Bing, Kayak's results are 100% client-side rendered -- confirmed a
# plain HTTP GET returns zero result markup, so there's no fast HTTP-first
# tier here, only headless Chromium. Results also stream in progressively
# over several seconds rather than being present at page load, so these poll
# for the result selector to appear instead of a fixed sleep. CSS classes
# below are algorithmically-generated hashes (Kayak's build system), not
# semantic names like Bing's `.b_algo` -- meaningfully more likely to break
# on any Kayak frontend deploy than the Bing scraper. Confirmed live when
# built; if results come back empty, this is the first place to check.


async def _kayak_page_with_results(url: str, selector: str, timeout_ms: int = 20000, settle_ms: int = 2000):
    """Returns (playwright_driver, browser, page) -- caller is responsible for
    `await browser.close()` then `await playwright_driver.stop()`.
    """
    # No extra_http_headers here (unlike _fetch_html_browser above) -- confirmed
    # live that Kayak's flights vertical returns zero results when Accept/
    # Accept-Language/Accept-Encoding/etc are set on the page context, even
    # though the main HTML document still loads fine (200, correct title).
    # Those headers apply to every request Playwright makes including Kayak's
    # background result-streaming calls, and something in that set breaks
    # those specifically. A plain User-Agent alone works for both verticals.
    playwright_driver = await async_playwright().start()
    browser = await playwright_driver.chromium.launch()
    page = await browser.new_page(user_agent=random_user_agent())
    await page.goto(url, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT_MS)

    elapsed = 0
    poll_ms = 1500
    while elapsed < timeout_ms:
        if await page.locator(selector).count() > 0:
            await page.wait_for_timeout(settle_ms)  # let a few more results stream in
            break
        await page.wait_for_timeout(poll_ms)
        elapsed += poll_ms

    return playwright_driver, browser, page


async def kayak_flight_search(from_airport: str, to_airport: str, departure_date: str, max_results: int = 5) -> list[dict]:
    """Search Kayak for one-way flights (no round-trip support in this tool).
    Raises on hard failure; returns [] if no results stream in within the
    poll timeout (~20s worst case, usually faster).
    """
    url = f"https://www.kayak.com/flights/{from_airport}-{to_airport}/{departure_date}"
    pw, browser, page = await _kayak_page_with_results(url, ".nrc6-wrapper")
    try:
        raw = await page.eval_on_selector_all(
            ".nrc6-wrapper",
            """(nodes, max) => nodes.slice(0, max).map(n => {
                const price = n.querySelector('.e2GB-price-text');
                const provider = n.querySelector('.M_JD-provider-name');
                const logo = n.querySelector('.c5iUd-leg-carrier img');
                const leg = n.querySelector('.c3J0r-container');
                const times = leg ? leg.querySelector('.VY2U .vmXl') : null;
                const stops = leg ? leg.querySelector('.JWEO .vmXl') : null;
                const duration = leg ? leg.querySelector('.xdW8 .vmXl') : null;
                return {
                    price: price ? price.textContent.trim() : '',
                    airline: provider ? provider.textContent.trim() : (logo ? logo.getAttribute('alt') : ''),
                    times: times ? times.textContent.trim() : '',
                    stops: stops ? stops.textContent.trim() : '',
                    duration: duration ? duration.textContent.trim() : '',
                };
            })""",
            max_results,
        )
    finally:
        await browser.close()
        await pw.stop()

    return [r for r in raw if r["price"]]


async def kayak_hotel_search(destination: str, check_in: str, check_out: str, max_results: int = 5) -> list[dict]:
    """Search Kayak for hotels. Raises on hard failure; returns [] if no
    results stream in within the poll timeout (~20s worst case, usually
    faster).
    """
    dest_path = urllib.parse.quote(destination.replace(",", "").strip().replace(" ", "-"))
    url = f"https://www.kayak.com/hotels/{dest_path}/{check_in}/{check_out}"
    pw, browser, page = await _kayak_page_with_results(url, ".S0Ps-resultInner")
    try:
        raw = await page.eval_on_selector_all(
            ".S0Ps-resultInner",
            """(nodes, max) => nodes.slice(0, max).map(n => {
                const name = n.querySelector('.c9Hnq-big-name');
                const loc = n.querySelector('.upS4-big-name');
                const score = n.querySelector('.c9kNN');
                const label = n.querySelector('.AFFP-des');
                const price = n.querySelector('.c1XBO-primary-price');
                return {
                    name: name ? name.textContent.trim() : '',
                    location: loc ? loc.textContent.trim() : '',
                    score: score ? score.textContent.trim() : '',
                    rating_label: label ? label.textContent.trim() : '',
                    price: price ? price.textContent.trim() : '',
                };
            })""",
            max_results,
        )
    finally:
        await browser.close()
        await pw.stop()

    return [r for r in raw if r["name"]]
