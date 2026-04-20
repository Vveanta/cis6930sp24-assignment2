import os
import sqlite3
import threading
from collections import OrderedDict
from typing import Optional, Tuple

import googlemaps
from googlemaps.exceptions import ApiError

# # for local
# # Read API key from config file
# config = configparser.ConfigParser()
# config.read('config.ini')
# api_key = config['google_maps']['GOOGLE_API_KEY']

# for deployment server
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("No GOOGLE_API_KEY set for Flask application")
gmaps = googlemaps.Client(key=api_key)

_GEO_LRU_MAX = 8192
_geo_lru: "OrderedDict[str, Tuple[Optional[float], Optional[float]]]" = OrderedDict()
_geo_lock = threading.Lock()


class GeocodingQuotaError(Exception):
    """Raised when Google Geocoding returns quota / billing / access errors."""


def _lru_key(address: str, db_path: str) -> str:
    return f"{db_path}\x1f{address.strip().casefold()}"


def _lru_get(key: str) -> Optional[Tuple[Optional[float], Optional[float]]]:
    with _geo_lock:
        if key not in _geo_lru:
            return None
        _geo_lru.move_to_end(key)
        return _geo_lru[key]


def _lru_set(key: str, value: Tuple[Optional[float], Optional[float]]) -> None:
    with _geo_lock:
        _geo_lru[key] = value
        _geo_lru.move_to_end(key)
        while len(_geo_lru) > _GEO_LRU_MAX:
            _geo_lru.popitem(last=False)


def geocode_address(address, db_path="resources/normanpd.db"):
    lk = _lru_key(address, db_path)
    cached = _lru_get(lk)
    if cached is not None:
        return cached

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT latitude, longitude FROM geocodes WHERE location = ?", (address,))
    result = c.fetchone()
    conn.close()

    if result:
        out = (result[0], result[1])
        _lru_set(lk, out)
        return out

    address_string = f"{address}, Norman, Oklahoma, USA"
    try:
        api_result = gmaps.geocode(address_string)
    except ApiError as e:
        status = getattr(e, "status", None)
        if status in (
            "OVER_QUERY_LIMIT",
            "OVER_DAILY_LIMIT",
            "REQUEST_DENIED",
            "RESOURCE_EXHAUSTED",
        ):
            raise GeocodingQuotaError(str(e)) from e
        raise

    if api_result:
        latitude = api_result[0]["geometry"]["location"]["lat"]
        longitude = api_result[0]["geometry"]["location"]["lng"]
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO geocodes (location, latitude, longitude) VALUES (?, ?, ?)",
            (address, latitude, longitude),
        )
        conn.commit()
        conn.close()
        out = (latitude, longitude)
        _lru_set(lk, out)
        return out

    print(f"Geocoding API returned no results for address: {address_string}")
    out = (None, None)
    _lru_set(lk, out)
    return out
