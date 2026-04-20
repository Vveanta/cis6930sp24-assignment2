import random
import time
from typing import Any, Optional

import openmeteo_requests  # type: ignore
import pandas as pd
import requests_cache  # type: ignore
from openmeteo_requests import OpenMeteoRequestsError  # type: ignore
from retry_requests import retry  # type: ignore

# Retry Open-Meteo when rate-limited ("Too many concurrent requests", etc.)
_WEATHER_MAX_ATTEMPTS = 6
_BACKOFF_BASE_S = 0.45
_BACKOFF_CAP_S = 12.0


def _weather_cache_key(latitude: float, longitude: float, date: str, hour: int) -> tuple[Any, ...]:
    return (round(float(latitude), 5), round(float(longitude), 5), str(date), int(hour))


def _fetch_weathercode_once(latitude, longitude, date, hour) -> int:
    """Single Open-Meteo archive request (no retry)."""
    cache_session = requests_cache.CachedSession(".cache", expire_after=-1)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": date,
        "end_date": date,
        "hourly": "weather_code",
    }
    responses = openmeteo.weather_api(url, params=params)

    response = responses[0]
    hourly = response.Hourly()
    hourly_weather_code = hourly.Variables(0).ValuesAsNumpy()

    hourly_data = {
        "date": pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left",
        )
    }
    hourly_data["weather_code"] = hourly_weather_code

    hourly_dataframe = pd.DataFrame(data=hourly_data)
    return int(hourly_dataframe["weather_code"][hour])


def fetch_weathercode_using_meteo(
    latitude,
    longitude,
    date,
    hour,
    cache: Optional[dict] = None,
) -> int:
    """
    Historical weather code for (lat, lon, date, hour).

    - Optional ``cache``: dict keyed by (rounded lat, rounded lon, date str, hour) for one augment run.
    - Retries with exponential backoff on OpenMeteoRequestsError (rate limits, transient errors).
    """
    key = _weather_cache_key(latitude, longitude, date, hour)
    if cache is not None and key in cache:
        return cache[key]

    last_err: Optional[Exception] = None
    for attempt in range(_WEATHER_MAX_ATTEMPTS):
        try:
            code = _fetch_weathercode_once(latitude, longitude, date, hour)
            if cache is not None:
                cache[key] = code
            return code
        except OpenMeteoRequestsError as e:
            last_err = e
            if attempt >= _WEATHER_MAX_ATTEMPTS - 1:
                raise
            delay = min(
                _BACKOFF_CAP_S,
                _BACKOFF_BASE_S * (2**attempt) + random.random() * 0.25,
            )
            time.sleep(delay)

    raise last_err  # pragma: no cover
