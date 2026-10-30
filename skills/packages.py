from urllib.parse import quote


def search_packages(
    origin_airport: str,
    destination: str,
    check_in: str,
    check_out: str,
    adults: int = 2,
) -> str:
    """Build flight+hotel package search deep links.

    Only Expedia and Priceline offer bundled flight+hotel packages among
    major travel sites -- Google Travel and Skyscanner don't have a packages
    product, so they're not included here.

    origin_airport: IATA code, e.g. "SFO".
    destination: city/place name, e.g. "Cancun, Mexico".
    check_in/check_out: YYYY-MM-DD.
    """
    dest_q = quote(destination)

    links = {
        # Documented format from Expedia Group's own Developer Hub
        # (package-deeplinks page) -- confirmed, not a guess.
        "Expedia": (
            f"https://www.expedia.com/go/package/search/FlightHotel/{check_in}/{check_out}"
            f"?FromAirport={origin_airport}&Destination={dest_q}&NumAdult={adults}&NumRoom=1"
        ),
        # No official or confirmed parameterized format exists for Priceline
        # packages -- PerimeterX blocks automated verification of any guess,
        # so this is a plain landing page, not a prefilled deep link.
        "Priceline (search manually)": "https://www.priceline.com/vacationpackages",
    }

    lines = [
        f"Flight+hotel package search links: {origin_airport} -> {destination}, "
        f"{check_in} -> {check_out} ({adults} adults):"
    ]
    lines += [f"- {name}: {url}" for name, url in links.items()]
    return "\n".join(lines)


def register(mcp):
    mcp.tool()(search_packages)
