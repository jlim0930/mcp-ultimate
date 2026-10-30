import os
import random

# Pool of current, real desktop browser User-Agent strings (Chrome/Firefox/
# Safari/Edge across Windows and macOS). random_user_agent() picks a fresh
# one per call so consecutive outbound requests don't all share one
# identical fingerprint. Set BROWSER_USER_AGENT to pin a single exact value
# instead (skips the pool entirely).
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:158.0) Gecko/20100101 Firefox/158.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:158.0) Gecko/20100101 Firefox/158.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36 Edg/156.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Mobile/15E148 Safari/604.1",
]

# A handful of plausible Accept/Accept-Language/etc bundles. Not matched to a
# specific UA/OS -- these headers don't reveal OS the way UA does, and a
# sparse request with only a User-Agent header is itself a bot tell, so the
# goal here is just "looks like a normal browser sent this", not fingerprint
# precision.
HEADER_SETS = [
    {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
    },
    {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Upgrade-Insecure-Requests": "1",
    },
    {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    },
]

_USER_AGENT_PIN = os.environ.get("BROWSER_USER_AGENT", "").strip()


def random_user_agent() -> str:
    """User-Agent for outbound requests: the BROWSER_USER_AGENT pin if set, else a random pick from USER_AGENTS."""
    return _USER_AGENT_PIN or random.choice(USER_AGENTS)


def random_headers() -> dict:
    """A full header bundle (User-Agent + matching Accept/Accept-Language/etc), picked together."""
    headers = dict(random.choice(HEADER_SETS))
    headers["User-Agent"] = random_user_agent()
    return headers


HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "10"))
LOCAL_LLM_TIMEOUT = float(os.environ.get("LOCAL_LLM_TIMEOUT", "60"))
BROWSER_TIMEOUT_MS = int(os.environ.get("BROWSER_TIMEOUT_MS", "20000"))
BROWSER_VIEWPORT_WIDTH = int(os.environ.get("BROWSER_VIEWPORT_WIDTH", "1920"))
BROWSER_VIEWPORT_HEIGHT = int(os.environ.get("BROWSER_VIEWPORT_HEIGHT", "1080"))
SANDBOX_MAX_OUTPUT = int(os.environ.get("SANDBOX_MAX_OUTPUT", "20000"))
WEATHER_FORECAST_DAYS = int(os.environ.get("WEATHER_FORECAST_DAYS", "3"))
GIT_TIMEOUT = int(os.environ.get("GIT_TIMEOUT", "120"))
PYTHON_TIMEOUT = int(os.environ.get("PYTHON_TIMEOUT", "30"))

# web_search/search_news try Bing (scraped directly, HTTP first then headless
# browser) before falling back to SearXNG by default. Set to "false" to
# reverse that order -- SearXNG first (faster, self-hosted, under your
# control), Bing only as the fallback.
SEARCH_PREFER_BROWSER = os.environ.get("SEARCH_PREFER_BROWSER", "true").strip().lower() not in (
    "false",
    "0",
    "no",
    "off",
)
