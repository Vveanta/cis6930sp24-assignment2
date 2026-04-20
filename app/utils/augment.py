import csv
import datetime
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from .emstat import check_emsstat
from .geocoding import GeocodingQuotaError, geocode_address
from .rank import assign_ranks, calculate_frequencies
from .side import calculate_street_position
from .weather import fetch_weathercode_using_meteo

ProgressCb = Optional[Callable[[str, int, Optional[str]], None]]


class _ProgressEmitter:
    """Throttle Redis/UI updates so the bar moves smoothly without flooding Redis."""

    def __init__(self, cb: ProgressCb, min_interval_s: float = 0.45):
        self._cb = cb
        self._min = min_interval_s
        self._last = 0.0
        self._last_pct = -1
        self._last_detail: Optional[str] = None

    def emit(self, stage: str, percent: int, detail: Optional[str], force: bool = False) -> None:
        if not self._cb:
            return
        pct = max(0, min(100, int(percent)))
        now = time.monotonic()
        if force or (now - self._last >= self._min) or (pct - self._last_pct >= 2) or (detail and detail != self._last_detail):
            self._cb(stage, pct, detail)
            self._last = now
            self._last_pct = pct
            self._last_detail = detail
        else:
            self._last_detail = detail


def create_geocode_table(geocode_db_path="resources/normanpd.db"):
    conn = sqlite3.connect(geocode_db_path)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS geocodes (
            location TEXT PRIMARY KEY,
            latitude REAL,
            longitude REAL
        );
    """
    )
    conn.commit()
    conn.close()


def _enable_wal(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    finally:
        conn.close()


def _weather_and_side_for_row(incident: dict, weather_cache: dict | None) -> tuple[str, str]:
    lat, lng = incident.get("Latitude"), incident.get("Longitude")
    if lat is None or lng is None:
        return "Unknown", "Unknown"
    incident_time = datetime.datetime.strptime(incident["Incident_time"], "%m/%d/%Y %H:%M")
    weather = fetch_weathercode_using_meteo(
        lat,
        lng,
        incident_time.strftime("%Y-%m-%d"),
        incident_time.hour,
        cache=weather_cache,
    )
    side = calculate_street_position(lat, lng)
    return str(weather), side


def augment_data(db_path: str, progress_cb: ProgressCb = None) -> str:
    create_geocode_table(db_path)
    _enable_wal(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM incidents")
    incidents = cursor.fetchall()
    conn.close()

    incidents_dicts = [
        {
            "Incident_time": i[0],
            "Incident Number": i[1],
            "Location": i[2],
            "Nature": i[3],
            "Incident ORI": i[4],
        }
        for i in incidents
    ]

    prog = _ProgressEmitter(progress_cb)
    prog.emit("Preparing rankings", 5, None, force=True)

    location_frequencies = calculate_frequencies(incidents_dicts, "Location")
    nature_frequencies = calculate_frequencies(incidents_dicts, "Nature")
    location_ranks = assign_ranks(location_frequencies)
    nature_ranks = assign_ranks(nature_frequencies)

    n = len(incidents_dicts)
    augmented_incidents: list[dict] = []

    prog.emit("Geocoding addresses", 8, f"0 / {n}" if n else "No rows", force=True)

    for index, incident in enumerate(incidents_dicts):
        incident_time = datetime.datetime.strptime(incident["Incident_time"], "%m/%d/%Y %H:%M")
        dow = incident_time.isoweekday()
        adow = (dow % 7) + 1
        incident["Day Of The Week"] = adow
        incident["Time Of Day"] = incident_time.hour

        try:
            latitude, longitude = geocode_address(incident["Location"], db_path)
        except GeocodingQuotaError:
            raise

        incident["Latitude"] = latitude
        incident["Longitude"] = longitude
        incident["Location Rank"] = location_ranks[incident["Location"]]
        incident["Nature Rank"] = nature_ranks[incident["Nature"]]
        augmented_incidents.append(incident)

        if n > 0:
            pct_geo = 8 + int(52 * (index + 1) / n)
            prog.emit(
                "Geocoding addresses",
                pct_geo,
                f"{index + 1} / {n} locations",
                force=(index == 0 or index == n - 1),
            )

    # Weather + side of town (I/O bound — parallelize safely; geocodes already in DB/LRU)
    prog.emit("Weather & side of town", max(60, 8), f"0 / {n}" if n else None, force=True)

    if n == 0:
        pass
    else:
        # Open-Meteo limits concurrent requests; keep pool small (2–4 workers).
        weather_cache: dict = {}
        max_workers = max(1, min(4, n))

        def run_one(idx: int) -> tuple[int, str, str]:
            w, s = _weather_and_side_for_row(augmented_incidents[idx], weather_cache)
            return idx, w, s

        done = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(run_one, i) for i in range(n)]
            for fut in as_completed(futures):
                idx, weather, side = fut.result()
                augmented_incidents[idx]["Weather"] = weather
                augmented_incidents[idx]["Side of Town"] = side
                done += 1
                pct_wx = 60 + int(28 * done / n)
                prog.emit(
                    "Weather & side of town",
                    pct_wx,
                    f"{done} / {n} enriched",
                    force=(done == 1 or done == n),
                )

    prog.emit("Ranking & EMSSTAT", 90, None, force=True)
    for index, incident in enumerate(augmented_incidents):
        incident["EMSSTAT"] = check_emsstat(incidents_dicts, index)

    prog.emit("Writing augmented CSV", 94, None, force=True)

    resources_dir = os.path.join("app", "resources")
    if not os.path.exists(resources_dir):
        os.makedirs(resources_dir)
    csv_file_path = os.path.join(resources_dir, "augmented_data.csv")
    with open(csv_file_path, "w", newline="") as file:
        writer = csv.writer(file, delimiter=",")
        writer.writerow(
            [
                "Incident Time",
                "Latitude",
                "Longitude",
                "Day of the Week",
                "Time of Day",
                "Weather",
                "Location Rank",
                "Location",
                "Side of Town",
                "Incident Rank",
                "Nature",
                "EMSSTAT",
            ]
        )
        for incident in augmented_incidents:
            lat_v = incident.get("Latitude")
            lng_v = incident.get("Longitude")
            writer.writerow(
                [
                    incident["Incident_time"],
                    lat_v if lat_v is not None else "",
                    lng_v if lng_v is not None else "",
                    incident["Day Of The Week"],
                    incident["Time Of Day"],
                    incident["Weather"],
                    incident["Location Rank"],
                    incident["Location"],
                    incident["Side of Town"],
                    incident["Nature Rank"],
                    incident["Nature"],
                    incident["EMSSTAT"],
                ]
            )

    prog.emit("Done", 100, None, force=True)

    return csv_file_path
