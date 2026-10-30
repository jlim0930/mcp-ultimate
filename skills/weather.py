import httpx

from skills.config import HTTP_TIMEOUT, WEATHER_FORECAST_DAYS

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
ZIP_URL = "https://api.zippopotam.us/us/{zip}"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


async def _resolve_location(client: httpx.AsyncClient, location: str):
    location = location.strip()

    if location.isdigit() and len(location) == 5:
        resp = await client.get(ZIP_URL.format(zip=location))
        if resp.status_code == 200:
            data = resp.json()
            place = data["places"][0]
            label = f"{place['place name']}, {place['state abbreviation']} {location}"
            return float(place["latitude"]), float(place["longitude"]), label
        if resp.status_code != 404:
            resp.raise_for_status()

    resp = await client.get(GEOCODE_URL, params={"name": location, "count": 1})
    resp.raise_for_status()
    results = resp.json().get("results")
    if not results:
        raise ValueError(f"Could not find location: {location}")

    r = results[0]
    label = r["name"]
    if r.get("admin1"):
        label += f", {r['admin1']}"
    if r.get("country"):
        label += f", {r['country']}"
    return r["latitude"], r["longitude"], label


async def get_weather(location: str) -> str:
    """Get current conditions and a multi-day forecast for a city name or US zip code."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        lat, lon, label = await _resolve_location(client, location)
        resp = await client.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": "auto",
                "forecast_days": WEATHER_FORECAST_DAYS,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    cur = data["current"]
    desc = WEATHER_CODES.get(cur.get("weather_code"), "Unknown")
    lines = [
        f"Weather for {label}:",
        f"Now: {desc}, {cur['temperature_2m']}°F (feels like {cur['apparent_temperature']}°F), "
        f"humidity {cur['relative_humidity_2m']}%, wind {cur['wind_speed_10m']} mph",
        "",
    ]

    daily = data.get("daily", {})
    for i, d in enumerate(daily.get("time", [])):
        code_desc = WEATHER_CODES.get(daily["weather_code"][i], "Unknown")
        high = daily["temperature_2m_max"][i]
        low = daily["temperature_2m_min"][i]
        lines.append(f"{d}: {code_desc}, high {high}°F / low {low}°F")

    return "\n".join(lines)


def register(mcp):
    mcp.tool()(get_weather)
