from skills.flights import search_flights
from skills.weather import get_weather
from skills.web_search import web_search


async def plan_trip(
    origin_airport: str,
    destination_airport: str,
    destination_city: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
) -> str:
    """Compose a trip summary: cheapest flights, destination weather, and top attractions.

    origin_airport/destination_airport: IATA codes, used for the flight search.
    destination_city: place name used for the weather and attractions lookup, e.g. "Rome, Italy".
    departure_date/return_date: YYYY-MM-DD. Omit return_date for a one-way trip.
    """
    header = f"=== Trip plan: {origin_airport} -> {destination_city} ({departure_date}"
    header += f" to {return_date})" if return_date else ")"
    header += " ==="
    sections = [header]

    sections.append("\n--- Flights ---")
    try:
        sections.append(
            search_flights(
                origin_airport,
                destination_airport,
                departure_date,
                return_date,
                adults=adults,
                max_results=3,
            )
        )
    except Exception as e:
        sections.append(f"error: {e}")

    sections.append("\n--- Weather at destination ---")
    try:
        sections.append(await get_weather(destination_city))
    except Exception as e:
        sections.append(f"error: {e}")

    sections.append("\n--- Things to do ---")
    try:
        sections.append(await web_search(f"top attractions and things to do in {destination_city}", max_results=5))
    except Exception as e:
        sections.append(f"error: {e}")

    return "\n".join(sections)


def register(mcp):
    mcp.tool()(plan_trip)
