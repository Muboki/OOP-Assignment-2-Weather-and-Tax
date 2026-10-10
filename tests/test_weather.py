# Import tools for loading saved data and checking expected errors.
import json
from pathlib import Path

import pytest

# Import the weather functions we want to test.
from src.weather import WeatherError, describe_weather, forecast_to_table


# Locate the saved samples relative to this test file.
PROJECT_FOLDER = Path(__file__).resolve().parents[1]


# Load a fresh copy of the saved forecast for each test that needs it.
@pytest.fixture
def forecast_sample() -> dict:
    """Read the forecast sample without making an API request."""
    sample_path = PROJECT_FOLDER / "data" / "forecast_sample.json"

    with sample_path.open("r", encoding="utf-8") as file:
        return json.load(file)


# Check that parsing preserves the dates and temperature measurements.
def test_forecast_table_preserves_values(forecast_sample: dict) -> None:
    """Each table row should match the corresponding saved forecast day."""
    table = forecast_to_table(forecast_sample)
    daily = forecast_sample["daily"]

    assert len(table) == len(daily["time"])
    assert table["Date"].tolist() == daily["time"]
    assert table["Minimum temperature (°C)"].tolist() == (
        daily["temperature_2m_min"]
    )
    assert table["Maximum temperature (°C)"].tolist() == (
        daily["temperature_2m_max"]
    )


# Check that known, missing and unknown weather codes are distinguished.
def test_weather_descriptions() -> None:
    """Weather codes should produce clear and appropriate descriptions."""
    assert describe_weather(0) == "Clear sky"
    assert describe_weather(3) == "Overcast"
    assert describe_weather(63) == "Moderate rain"
    assert describe_weather(None) == "Not available"
    assert describe_weather(999) == "Unknown weather code: 999"

# Check that an absent daily section produces a clear error.
def test_missing_daily_section(forecast_sample: dict) -> None:
    """Reject a response without daily forecast data."""
    del forecast_sample["daily"]

    with pytest.raises(WeatherError, match="missing daily forecast data"):
        forecast_to_table(forecast_sample)


# Check that a missing measurement field is detected.
def test_missing_forecast_field(forecast_sample: dict) -> None:
    """Reject a forecast without its precipitation list."""
    del forecast_sample["daily"]["precipitation_sum"]

    with pytest.raises(WeatherError, match="precipitation_sum"):
        forecast_to_table(forecast_sample)


# Check that measurements cannot become misaligned with dates.
def test_mismatched_forecast_lengths(forecast_sample: dict) -> None:
    """Reject a temperature list with fewer entries than the dates."""
    forecast_sample["daily"]["temperature_2m_max"].pop()

    with pytest.raises(WeatherError, match="different lengths"):
        forecast_to_table(forecast_sample)


# Check that an empty forecast is rejected.
def test_empty_forecast(forecast_sample: dict) -> None:
    """Reject a response whose daily lists contain no observations."""
    for field in forecast_sample["daily"]:
        forecast_sample["daily"][field] = []

    with pytest.raises(WeatherError, match="no dates"):
        forecast_to_table(forecast_sample)