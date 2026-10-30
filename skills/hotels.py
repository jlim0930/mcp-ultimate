import time
from urllib.parse import quote

# fast-hotels hardcodes an outdated primp browser-impersonation string
# ("chrome_126") that current primp releases reject with "Invalid
# impersonate". Patch the Client fast_hotels.core actually calls (not primp
# itself -- primp.Client is a compiled PyO3 extension type whose __init__
# can be reassigned without error but is never actually invoked by
# construction, so patching it silently does nothing). See requirements.txt
# for the full explanation.
import fast_hotels.core as _fast_hotels_core
from primp import Client as _RealPrimpClient


def _patched_primp_client(*args, impersonate=None, **kwargs):
    if impersonate in ("chrome_126", "chrome_100"):
        impersonate = "chrome_146"
    return _RealPrimpClient(*args, impersonate=impersonate, **kwargs)


_fast_hotels_core.Client = _patched_primp_client

from fast_hotels import get_hotels  # noqa: E402
from fast_hotels.hotels_impl import Guests, HotelData  # noqa: E402

from skills.search_engines import kayak_hotel_search  # noqa: E402


def _deep_links(destination: str, check_in: str, check_out: str, adults: int, rooms: int) -> dict:
    dest_q = quote(destination)
    # Kayak's hotel URLs need a comma-free, hyphen-joined slug -- "Austin,-TX"
    # (comma preserved) silently redirects to Kayak's generic /stays landing
    # page instead of real results; "Austin-TX" resolves correctly. Confirmed
    # live by checking the final post-redirect URL and page title, not just
    # the HTTP status (a comma'd URL still returns 200, just on the wrong page).
    dest_path = quote(destination.replace(",", "").strip().replace(" ", "-"))
    return {
        "Booking.com": (
            f"https://www.booking.com/searchresults.html?ss={dest_q}"
            f"&checkin={check_in}&checkout={check_out}"
            f"&group_adults={adults}&no_rooms={rooms}"
        ),
        "Kayak": f"https://www.kayak.com/hotels/{dest_path}/{check_in}/{check_out}",
        "Expedia": (
            f"https://www.expedia.com/Hotel-Search?destination={dest_q}"
            f"&startDate={check_in}&endDate={check_out}"
            f"&adults={adults}&rooms={rooms}"
        ),
        # Priceline/Skyscanner block automated access (PerimeterX px-captcha /
        # unresolvable SPA routing respectively) -- no confirmed parameterized
        # URL scheme for either, so these are plain landing pages, not
        # prefilled deep links.
        "Priceline (search manually)": "https://www.priceline.com/hotels",
        "Skyscanner (search manually)": "https://www.skyscanner.com/hotels",
    }


def _looks_degraded(result) -> bool:
    """fast_hotels occasionally gets a Google Hotels response variant it parses
    into near-empty records (rating=None, price<=1.0, no amenities/url) instead
    of raising -- observed ~1 in 3 calls live, not rare. Detect that case so
    we can retry rather than present it as if it were real data.
    """
    if not result.hotels:
        return False
    bad = sum(1 for h in result.hotels if h.rating is None or h.price <= 1.0)
    return bad > len(result.hotels) / 2


def search_hotels(destination: str, check_in: str, check_out: str, adults: int = 2, rooms: int = 1) -> str:
    """Search for hotels and return real prices/ratings plus comparison links.

    Tries real Google Hotels data first (name, price, rating, amenities,
    direct booking URL) via the fast-hotels package -- same undocumented
    internal-API approach fast-flights uses for Google Flights. Always also
    lists deep links to Booking.com/Kayak/Expedia (prefilled) and
    Priceline/Skyscanner (plain landing pages -- both block automated access,
    so there's no reliable prefilled URL for either) to compare further or
    book elsewhere.

    destination: city/place name, e.g. "Austin, TX".
    check_in/check_out: YYYY-MM-DD.
    """
    lines = []

    try:
        hd = HotelData(checkin_date=check_in, checkout_date=check_out, location=destination)
        result = None
        for attempt in range(3):
            result = get_hotels(hotel_data=[hd], guests=Guests(adults=adults), limit=5)
            if not _looks_degraded(result):
                break
            if attempt < 2:
                time.sleep(1.5)

        if result.hotels and not _looks_degraded(result):
            lines.append(f"Google Hotels results for {destination}, {check_in} -> {check_out}:")
            for i, h in enumerate(result.hotels, 1):
                amenities = ", ".join(h.amenities[:5]) if h.amenities else ""
                lines.append(f"{i}. {h.name} -- ${h.price}/night, rating {h.rating}\n   {amenities}\n   {h.url}")
        elif result.hotels:
            lines.append(
                f"Google Hotels: results for {destination} came back incomplete after 3 attempts "
                "(this happens -- Google occasionally serves a response fast-hotels can't fully parse). "
                "Using comparison links below instead."
            )
        else:
            lines.append(f"Google Hotels: no results for {destination}.")
    except Exception as e:
        lines.append(f"Google Hotels: unavailable ({e})")

    lines.append(f"\nMore options for {destination}, {check_in} -> {check_out} ({adults} adults, {rooms} room(s)):")
    for name, url in _deep_links(destination, check_in, check_out, adults, rooms).items():
        lines.append(f"- {name}: {url}")

    return "\n".join(lines)


async def search_hotels_kayak(destination: str, check_in: str, check_out: str, max_results: int = 5) -> str:
    """Cross-check real hotel prices/ratings from Kayak (separate from
    Google Hotels' data in search_hotels).

    Slower than search_hotels (~5-20s vs under a few seconds) -- Kayak's
    results are entirely client-side rendered and stream in progressively,
    so this needs a real headless-browser page load, not a quick HTTP
    request. Only call this when an actual price cross-check is worth the
    wait; for a fast default, use search_hotels.

    destination: city/place name, e.g. "Austin, TX".
    check_in/check_out: YYYY-MM-DD.
    """
    try:
        results = await kayak_hotel_search(destination, check_in, check_out, max_results)
    except Exception as e:
        return f"error searching Kayak: {e}"

    if not results:
        return f"No Kayak results for {destination} (or the page didn't load results in time -- try again)."

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. {r['name']} ({r['location']}) -- {r['price']}/night, {r['score']} {r['rating_label']}"
        )
    return "\n".join(lines)


def register(mcp):
    mcp.tool()(search_hotels)
    mcp.tool()(search_hotels_kayak)
