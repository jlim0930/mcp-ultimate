from fast_flights import FlightQuery, Passengers, create_filter, get_flights

from skills.search_engines import kayak_flight_search


def _compare_links(from_airport: str, to_airport: str, departure_date: str, return_date: str) -> dict:
    # Expedia: documented query-param format (see search_hotels/search_car_rentals
    # for the general pattern). Skyscanner: confirmed working path format
    # (tested live). Priceline: no confirmed parameterized format -- PerimeterX
    # blocks automated verification of any guess, so this is a plain landing
    # page, not a prefilled deep link.
    y, m, d = departure_date.split("-")
    sky_date = f"{y[2:]}{m}{d}"
    trip = "roundtrip" if return_date else "oneway"
    expedia = (
        f"https://www.expedia.com/Flights-Search?flight-type=on&mode=search&trip={trip}"
        f"&leg1=from:{from_airport},to:{to_airport},departure:{m}/{d}/{y}TANYT"
    )
    if return_date:
        ry, rm, rd = return_date.split("-")
        expedia += f"&leg2=from:{to_airport},to:{from_airport},departure:{rm}/{rd}/{ry}TANYT"
    expedia += "&passengers=adults:1&options=cabinclass:economy"

    links = {
        "Expedia": expedia,
        "Skyscanner": f"https://www.skyscanner.com/transport/flights/{from_airport.lower()}/{to_airport.lower()}/{sky_date}/",
        "Priceline (search manually)": "https://www.priceline.com/fly",
    }
    return links


def _fmt_dt(dt) -> str:
    y, m, d = dt.date
    hh, mm = dt.time
    return f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}"


def _render(results, max_n: int) -> str:
    if not results:
        return "No flights found."
    ranked = sorted(results, key=lambda f: f.price)[:max_n]
    lines = []
    for i, f in enumerate(ranked, 1):
        stops = len(f.flights) - 1
        legs = [
            f"{leg.from_airport.code} {_fmt_dt(leg.departure)} -> {leg.to_airport.code} {_fmt_dt(leg.arrival)} "
            f"({leg.plane_type}, {leg.duration}min)"
            for leg in f.flights
        ]
        lines.append(f"{i}. ${f.price} | {', '.join(f.airlines)} | {stops} stop(s)\n   " + "\n   ".join(legs))
    return "\n\n".join(lines)


def search_flights(
    from_airport: str,
    to_airport: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
    seat: str = "economy",
    max_results: int = 5,
) -> str:
    """Search Google Flights for the cheapest options on a route, ranked by price.

    from_airport/to_airport: IATA airport codes, e.g. SFO, JFK.
    departure_date/return_date: YYYY-MM-DD. Omit return_date for a one-way search.
    seat: economy, premium-economy, business, or first.

    NOTE: scrapes Google Flights' internal endpoints (no official API exists
    for this data without a paid partner agreement). Data quality and
    availability can change if Google alters their site. Round-trip results
    are two independent one-way searches (outbound + return), each ranked
    by price -- Google's bundled round-trip fare requires an extra
    outbound-selection step this scraper doesn't perform, so there's no
    combined round-trip discount here, just the two cheapest legs.

    Also appends comparison links to Expedia/Skyscanner (prefilled) and
    Priceline (plain landing page, no confirmed deep-link format) -- Expedia
    and Priceline both block automated price scraping outright (PerimeterX),
    so these three never return real prices the way this tool's own Google
    Flights data does, just a place to check and compare manually.
    """
    compare = "\n".join(f"- {name}: {url}" for name, url in _compare_links(
        from_airport, to_airport, departure_date, return_date
    ).items())

    def _search_one_way(dep_date: str, dep_airport: str, arr_airport: str):
        query = create_filter(
            flights=[FlightQuery(date=dep_date, from_airport=dep_airport, to_airport=arr_airport)],
            trip="one-way",
            seat=seat,
            passengers=Passengers(adults=adults),
        )
        return get_flights(query)

    try:
        outbound = _search_one_way(departure_date, from_airport, to_airport)
    except Exception as e:
        return f"error searching outbound flights: {e}"

    if not return_date:
        if not outbound:
            return f"No flights found for {from_airport} -> {to_airport} on {departure_date}"
        return f"{_render(outbound, max_results)}\n\nAlso compare:\n{compare}"

    try:
        inbound = _search_one_way(return_date, to_airport, from_airport)
    except Exception as e:
        return f"Outbound found, but error searching return flights: {e}"

    return (
        f"Outbound ({from_airport} -> {to_airport}, {departure_date}):\n"
        f"{_render(outbound, max_results)}\n\n"
        f"Return ({to_airport} -> {from_airport}, {return_date}):\n"
        f"{_render(inbound, max_results)}\n\n"
        f"Also compare:\n{compare}"
    )


async def search_flights_kayak(from_airport: str, to_airport: str, departure_date: str, max_results: int = 5) -> str:
    """Cross-check real one-way flight prices from Kayak (separate from
    Google Flights' data in search_flights).

    Slower than search_flights (~5-20s vs under a second) -- Kayak's results
    are entirely client-side rendered and stream in progressively, so this
    needs a real headless-browser page load, not a quick HTTP request. Only
    call this when an actual price cross-check is worth the wait; for a fast
    default, use search_flights. No round-trip support (call twice with
    airports swapped for a return leg if needed).
    """
    try:
        results = await kayak_flight_search(from_airport, to_airport, departure_date, max_results)
    except Exception as e:
        return f"error searching Kayak: {e}"

    if not results:
        return f"No Kayak results for {from_airport} -> {to_airport} on {departure_date} (or the page didn't load results in time -- try again)."

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['price']} | {r['airline']} | {r['stops']} ({r['duration']})\n   {r['times']}")
    return "\n\n".join(lines)


def register(mcp):
    mcp.tool()(search_flights)
    mcp.tool()(search_flights_kayak)
