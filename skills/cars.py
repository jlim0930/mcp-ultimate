from urllib.parse import quote


def search_car_rentals(location: str, pickup_date: str, dropoff_date: str) -> str:
    """Build car rental search deep links for a location and date range.

    No free real-time car rental pricing API exists, so this returns
    ready-to-click search URLs (dates prefilled where the site's format is
    confirmed) rather than scraped prices.

    location: city/place name, e.g. "Los Angeles, CA".
    pickup_date/dropoff_date: YYYY-MM-DD.
    """
    # Kayak's URLs need a comma-free, hyphen-joined slug -- "Los-Angeles,-CA"
    # (comma preserved) silently resolves to the WRONG city (Carlsbad, not
    # LA) instead of erroring; "Los-Angeles-CA" resolves correctly. Confirmed
    # live by checking the final post-redirect URL and page title, not just
    # the HTTP status (the broken form still returns 200, just for Carlsbad).
    loc_path = quote(location.replace(",", "").strip().replace(" ", "-"))
    loc_q = quote(location)
    y, m, d = pickup_date.split("-")

    links = {
        "Kayak": f"https://www.kayak.com/cars/{loc_path}/{pickup_date}/{dropoff_date}",
        # Expedia requires a numeric `dpln` region id for a fully-prefilled
        # result; without it this usually lands on a disambiguation step.
        "Expedia": f"https://www.expedia.com/carsearch?locn={loc_q}&date1={m}/{d}/{y}&date2={dropoff_date}",
        # Priceline/Skyscanner: no confirmed parameterized format for either
        # (Priceline blocks automated verification outright; Skyscanner's
        # car-hire city-slug scheme returned 404 on every guess tried) --
        # plain landing pages, not prefilled deep links.
        "Priceline (search manually)": "https://www.priceline.com/drive",
        "Skyscanner (search manually)": "https://www.skyscanner.com/car-hire",
        "Google (general search)": (
            f"https://www.google.com/search?q=car+rental+in+{loc_q}+from+{pickup_date}+to+{dropoff_date}"
        ),
    }

    lines = [f"Car rental search links for {location}, {pickup_date} -> {dropoff_date}:"]
    lines += [f"- {name}: {url}" for name, url in links.items()]
    lines.append(
        "\n(Kayak's URL scheme is confirmed working; Expedia/Priceline/Skyscanner "
        "are either best-effort or plain landing pages -- see the comments in "
        "cars.py for why. The Google link is a reliable fallback regardless.)"
    )
    return "\n".join(lines)


def register(mcp):
    mcp.tool()(search_car_rentals)
