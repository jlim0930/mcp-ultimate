from playwright.async_api import async_playwright

from skills.config import BROWSER_TIMEOUT_MS, BROWSER_VIEWPORT_HEIGHT, BROWSER_VIEWPORT_WIDTH, random_headers


async def browse(url: str, max_chars: int = 8000, scroll_to_bottom: bool = False) -> str:
    """Render a page with a headless browser (JS included) and return its visible text.

    Use this for JavaScript-heavy pages that fetch_url can't read properly.
    Heavier/slower than fetch_url -- prefer fetch_url first.

    scroll_to_bottom: for lazy-loaded/infinite-scroll pages that only render
    content as you scroll (not needed for ordinary pages, adds ~2s).
    """
    headers = random_headers()
    user_agent = headers.pop("User-Agent")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(
                user_agent=user_agent,
                extra_http_headers=headers,
                viewport={"width": BROWSER_VIEWPORT_WIDTH, "height": BROWSER_VIEWPORT_HEIGHT},
            )
            await page.goto(url, wait_until="networkidle", timeout=BROWSER_TIMEOUT_MS)
            if scroll_to_bottom:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
            text = await page.inner_text("body")
        finally:
            await browser.close()

    text = " ".join(text.split())
    if len(text) > max_chars:
        text = text[:max_chars] + f"... [truncated, {len(text)} chars total]"
    return text or "(no readable text found)"


def register(mcp):
    mcp.tool()(browse)
