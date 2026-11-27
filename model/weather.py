"""Hourly weather for St. Gallen from Open-Meteo, as a feature for the model.

Scooter use depends on the weather (rain, cold), so the training table gets
the temperature and precipitation of every hour. This module gives:

- get_history(): hourly weather from the start of our data collection (2.11.)
  up to today, to join with the collected snapshots for training,
- get_forecast(): hourly weather for tomorrow, as input for the prediction.

Both come from the same Open-Meteo forecast endpoint. It also returns past
days (up to about three months back), so history and forecast are built the
same way. Open-Meteo is free and needs no API key.

The API is asked for UTC times, which are then converted to Swiss local time
(Europe/Zurich). Converting from UTC avoids the duplicated or missing hour when
the clocks change, and it matches analysis/load_data.py, which also works in
Europe/Zurich.

Precipitation in Open-Meteo is the sum of the preceding hour: the value at
08:00 is the rain that fell between 07:00 and 08:00.

AI citation: this file was generated with Claude Code (model Claude Opus 5.5,
Anthropic) on 2026-11-27 and reviewed by Moritz.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

API_URL = "https://api.open-meteo.com/v1/forecast"
LOCAL_TIME = ZoneInfo("Europe/Zurich")

# Center of St. Gallen. One point is enough: the city is small, so the weather
# is the same for every 200 m cell.
ST_GALLEN = (47.4245, 9.3767)

# First day of our data collection.
COLLECTION_START = date(2026, 11, 2)

# Open-Meteo variable names and the column names we use in our tables.
VARIABLES = {
    "temperature_2m": "temperature_c",
    "precipitation": "precipitation_mm",
}


def fetch_weather(start, end, location=ST_GALLEN, timeout=30):
    """Download hourly weather from Open-Meteo for the days start to end (both included).

    start and end are datetime.date objects in Swiss local time. Returns a
    DataFrame with the columns time, temperature_c and precipitation_mm, one
    row per hour, with time in Europe/Zurich.
    Raises requests.HTTPError if the API answers with an error.
    """
    lat, lon = location
    # One extra day on both sides in UTC, so that every local hour of the
    # requested days is included; the extra hours are cut off below.
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(VARIABLES),
        "timezone": "GMT",
        "start_date": (start - timedelta(days=1)).isoformat(),
        "end_date": (end + timedelta(days=1)).isoformat(),
    }
    response = requests.get(API_URL, params=params, timeout=timeout)
    response.raise_for_status()
    weather = parse_hourly(response.json())
    local_day = weather["time"].dt.date
    return weather[(local_day >= start) & (local_day <= end)].reset_index(drop=True)


def parse_hourly(payload):
    """Turn the JSON answer of Open-Meteo into a DataFrame in Swiss local time.

    The answer has a block "hourly" with a list of UTC times and one list of
    values per variable, all of the same length.
    """
    hourly = payload["hourly"]
    weather = pd.DataFrame({
        "time": pd.to_datetime(hourly["time"], utc=True).tz_convert(LOCAL_TIME),
        **{column: hourly[name] for name, column in VARIABLES.items()},
    })
    # Missing values come as null (NaN). Precipitation is then treated as
    # 0 mm; temperature stays NaN so that the model side can decide.
    weather["precipitation_mm"] = weather["precipitation_mm"].fillna(0.0)
    return weather


def get_history(start=COLLECTION_START, end=None):
    """Hourly weather from the start of the data collection up to today (local time)."""
    if end is None:
        end = datetime.now(LOCAL_TIME).date()
    return fetch_weather(start, end)


def get_forecast(day=None):
    """Hourly weather forecast for one day, by default tomorrow (local time)."""
    if day is None:
        day = datetime.now(LOCAL_TIME).date() + timedelta(days=1)
    return fetch_weather(day, day)


if __name__ == "__main__":
    # Quick check by hand: python3 model/weather.py
    history = get_history()
    print(f"History: {len(history)} hours from {history['time'].min()} to {history['time'].max()}")
    print(history.tail(3).to_string(index=False))
    forecast = get_forecast()
    print(f"\nForecast for tomorrow: {len(forecast)} hours")
    print(forecast.to_string(index=False))
