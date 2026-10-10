"""Reusable functions for location searches and weather forecasts."""

# Import tools for retry delays and HTTP requests.
import time
import requests

# Read contact settings from the local environment.
import os

# Import pandas to organise daily forecasts into a table.
import pandas as pd

# Import tools for saving and reading forecast snapshots.
import json
from pathlib import Path

# Import standard-library tools for HTTP requests and their errors.
import urllib.request
from urllib.error import HTTPError, URLError


# Give weather-related failures a recognisable exception type.
class WeatherError(Exception):
    """Raised when a weather request or its returned data cannot be used."""


# Request JSON data with retries and optional response details.
def request_json(
    url: str,
    params: dict,
    contact_email: str,
    timeout: float = 15.0,
    response_info: dict | None = None
) -> dict:
    """Fetch JSON and optionally record details of the successful response."""

    # Check settings before contacting the API.
    if not contact_email.strip():
        raise WeatherError("Configure your contact email before requesting data.")

    if not 0 < timeout <= 60:
        raise WeatherError("Timeout must be greater than zero and at most 60 seconds.")

    headers = {
        "User-Agent": f"WeatherAssignment/1.0 ({contact_email.strip()})"
    }

    # Store the most recent failure if all request attempts fail.
    last_error: Exception | None = None

    for attempt in range(3):
        try:
            # Measure this attempt through downloading the response.
            start_time = time.perf_counter()

            with requests.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout
            ) as response:
                elapsed_seconds = time.perf_counter() - start_time
                response.raise_for_status()
                data = response.json()

                # Record response details when the caller requests them.
                if response_info is not None:
                    response_info.update({
                        "status_code": response.status_code,
                        "content_type": response.headers.get("Content-Type"),
                        "response_seconds": elapsed_seconds
                    })

            # Our weather APIs should return a JSON object.
            if not isinstance(data, dict):
                raise WeatherError("The API did not return a JSON object.")

            return data

        except requests.exceptions.JSONDecodeError as error:
            raise WeatherError("The API returned invalid JSON.") from error

        except requests.exceptions.HTTPError as error:
            # Retry server errors; stop immediately for other HTTP errors.
            status = (
                error.response.status_code
                if error.response is not None
                else None
            )
            if status is None or not 500 <= status < 600:
                raise WeatherError(f"Request rejected: HTTP {status}.") from error
            last_error = error

        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout
        ) as error:
            # Temporary network problems may succeed on another attempt.
            last_error = error

        except requests.exceptions.RequestException as error:
            raise WeatherError("The request could not be completed.") from error

        # Wait one second, then two seconds, between attempts.
        if attempt < 2:
            time.sleep(2 ** attempt)

    raise WeatherError(
        "Request failed after three attempts. Check your connection "
        "or try again later."
    ) from last_error

# Find candidate locations for the user's chosen place name.
def geocode(name: str) -> list[dict]:
    """Return candidate locations matching a non-empty place name."""

    # Reject an empty location before sending a request.
    if not isinstance(name, str) or not name.strip():
        raise WeatherError("Enter a non-empty location name.")

    # Search for up to five matching locations.
    data = request_json(
        url="https://geocoding-api.open-meteo.com/v1/search",
        params={"name": name.strip(), "count": 5, "language": "en"},
        contact_email=os.getenv("WEATHER_CONTACT_EMAIL", "")
    )

    # Open-Meteo may omit the results key when no locations match.
    candidates = data.get("results", [])

    # Check the structure and fields needed for location selection.
    if not isinstance(candidates, list):
        raise WeatherError("The API returned an invalid location list.")

    for place in candidates:
        if not isinstance(place, dict):
            raise WeatherError("The API returned an invalid location entry.")

        if not {"name", "latitude", "longitude"}.issubset(place):
            raise WeatherError("A location is missing its name or coordinates.")

    return candidates

# Retrieve daily weather forecasts for the selected coordinates.
def get_forecast(lat: float, lon: float, days: int) -> dict:
    """Return daily forecast JSON for valid coordinates and 1–16 days."""

    # Reject invalid coordinates before contacting the API.
    if type(lat) not in (int, float) or not -90 <= lat <= 90:
        raise WeatherError("Latitude must be a number between -90 and 90.")

    if type(lon) not in (int, float) or not -180 <= lon <= 180:
        raise WeatherError("Longitude must be a number between -180 and 180.")

    if type(days) is not int or not 1 <= days <= 16:
        raise WeatherError("Forecast days must be a whole number from 1 to 16.")

    # Specify the daily measurements, units and local time zone.
    params = {
        "latitude": lat,
        "longitude": lon,
        "forecast_days": days,
        "daily": ",".join([
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "wind_speed_10m_max",
            "weather_code"
        ]),
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "timezone": "auto"
    }

    # Use our shared function for timeouts and limited retries.
    return request_json(
        url="https://api.open-meteo.com/v1/forecast",
        params=params,
        contact_email=os.getenv("WEATHER_CONTACT_EMAIL", "")
    )

# Map Open-Meteo weather codes to readable descriptions.
# Source: https://open-meteo.com/en/docs
WEATHER_DESCRIPTIONS = {
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
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    97: "Heavy thunderstorm",
    99: "Thunderstorm with heavy hail"
}


# Translate a weather code without guessing unknown conditions.
def describe_weather(code: int | None) -> str:
    """Return a description, marking missing or unknown codes explicitly."""
    if code is None:
        return "Not available"

    return WEATHER_DESCRIPTIONS.get(code, f"Unknown weather code: {code}")

# Convert daily forecast JSON into a table with clearly labelled units.
def forecast_to_table(data: dict) -> pd.DataFrame:
    """Build a daily forecast table after checking the response structure."""

    # Require a dictionary containing daily forecast data.
    if not isinstance(data, dict) or not isinstance(data.get("daily"), dict):
        raise WeatherError("The response is missing daily forecast data.")

    daily = data["daily"]

    # Match API field names to readable table headings.
    columns = {
        "time": "Date",
        "temperature_2m_min": "Minimum temperature (°C)",
        "temperature_2m_max": "Maximum temperature (°C)",
        "precipitation_sum": "Precipitation (mm)",
        "wind_speed_10m_max": "Maximum wind speed (km/h)",
        "weather_code": "Weather code"
    }

    # Check that each required field contains a list.
    for field in columns:
        if not isinstance(daily.get(field), list):
            raise WeatherError(f"Missing or invalid daily field: {field}.")

    # Every measurement must have one entry for each forecast date.
    day_count = len(daily["time"])
    if day_count == 0:
        raise WeatherError("The forecast contains no dates.")

    if any(len(daily[field]) != day_count for field in columns):
        raise WeatherError("Daily forecast lists have different lengths.")

    # Create the table without changing the original response.
    table = pd.DataFrame({
        heading: daily[field]
        for field, heading in columns.items()
    })

    # Translate weather codes into readable descriptions.
    table["Description"] = [
        describe_weather(code) for code in daily["weather_code"]
    ]

    return table

# Retrieve a MET Norway snapshot once and reuse it for this location.
def get_met_forecast(
    lat: float,
    lon: float,
    sample_folder: Path
) -> dict:
    """Return a saved MET Norway snapshot, downloading it if absent."""

    # Check coordinates before reading or requesting forecast data.
    if type(lat) not in (int, float) or not -90 <= lat <= 90:
        raise WeatherError("Latitude must be a number between -90 and 90.")

    if type(lon) not in (int, float) or not -180 <= lon <= 180:
        raise WeatherError("Longitude must be a number between -180 and 180.")

    # Limit coordinate precision and keep separate samples per location.
    lat_text = f"{lat:.4f}"
    lon_text = f"{lon:.4f}"
    sample_path = sample_folder / f"met_forecast_{lat_text}_{lon_text}.json"

    try:
        # Reuse the existing snapshot without contacting the API.
        if sample_path.exists():
            with sample_path.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, dict):
                raise WeatherError("The saved MET Norway sample is invalid.")

            return data

        # Use the shared request function for identification and retries.
        data = request_json(
            url="https://api.met.no/weatherapi/locationforecast/2.0/compact",
            params={"lat": lat_text, "lon": lon_text},
            contact_email=os.getenv("WEATHER_CONTACT_EMAIL", "")
        )

        # Save the response for repeatable analysis and offline checks.
        sample_folder.mkdir(parents=True, exist_ok=True)
        with sample_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)

        return data

    except (OSError, json.JSONDecodeError) as error:
        raise WeatherError(
            "Could not read or save the MET Norway sample file."
        ) from error

# Convert MET Norway time steps into a table using local times.
def met_to_table(data: dict, local_timezone: str) -> pd.DataFrame:
    """Extract temperature and wind forecasts, converting wind to km/h."""

    # Check the expected response structure and measurement units.
    try:
        properties = data["properties"]
        units = properties["meta"]["units"]
        entries = properties["timeseries"]

        if units["air_temperature"] != "celsius":
            raise WeatherError("Expected MET Norway temperatures in Celsius.")

        if units["wind_speed"] != "m/s":
            raise WeatherError("Expected MET Norway wind speeds in m/s.")

        if not isinstance(entries, list) or not entries:
            raise WeatherError("MET Norway returned no valid forecast list.")

        # Extract the measurements for each forecast time.
        rows = []
        for entry in entries:
            details = entry["data"]["instant"]["details"]
            wind_speed = details["wind_speed"]

            rows.append({
                "Time": entry["time"],
                "Temperature (°C)": details["air_temperature"],
                "Wind speed (km/h)": (
                    None if wind_speed is None else wind_speed * 3.6
                )
            })

    except (KeyError, TypeError) as error:
        raise WeatherError(
            "The MET Norway response has missing or invalid fields."
        ) from error

    # Convert UTC timestamps to the selected location's time zone.
    table = pd.DataFrame(rows)

    try:
        table["Time"] = pd.to_datetime(
            table["Time"], utc=True, errors="raise"
        ).dt.tz_convert(local_timezone)

    except (ValueError, KeyError, TypeError) as error:
        raise WeatherError(
            "Could not interpret the forecast times or local time zone."
        ) from error

    return table

# Fetch JSON using urllib with a timeout and limited retries.
def urllib_request_json(request: urllib.request.Request) -> dict:
    """Read JSON using urllib, allowing at most three attempts."""
    last_error: Exception | None = None

    for attempt in range(3):
        try:
            # urllib automatically raises HTTPError for HTTP failures.
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.load(response)

            # Require the JSON object expected from our weather APIs.
            if not isinstance(data, dict):
                raise WeatherError("The API did not return a JSON object.")

            return data

        except HTTPError as error:
            # Retry server errors but stop for other HTTP errors.
            status = error.code
            error.close()

            if not 500 <= status < 600:
                raise WeatherError(
                    f"Request rejected: HTTP {status}."
                ) from error

            last_error = error

        except (URLError, TimeoutError) as error:
            # Retry temporary connection failures and timeouts.
            last_error = error

        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise WeatherError("The API returned invalid JSON.") from error

        # Wait one second, then two seconds, before retrying.
        if attempt < 2:
            time.sleep(2 ** attempt)

    raise WeatherError(
        "The urllib request failed after three attempts."
    ) from last_error


