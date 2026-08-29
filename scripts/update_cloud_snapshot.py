from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.cesar_live import (
    MAX_DISTANCE_MILES,
    MOVING_MAX_AGE_MINUTES,
    STATIONARY_MAX_AGE_MINUTES,
    VISIBLE_RADIUS_MILES,
    age_minutes,
    bearing_degrees,
    calculate_cpa,
    classify_movement,
    compass_direction,
    display_name,
    fetch_vessels,
    freshness_limit,
    haversine_miles,
    is_fixed_infrastructure,
    is_navigation_aid,
    is_stale_warning,
)

OUT = Path(__file__).resolve().parents[1] / "data" / "vessels.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def required_float(name: str) -> float:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing {name}. Add it as a GitHub Actions repository secret."
        )
    return float(value)


def build_snapshot() -> dict:
    site_lat = required_float("SITE_LATITUDE")
    site_lon = required_float("SITE_LONGITUDE")
    site_name = os.getenv("SITE_NAME", "M-35 Family Watch Area")

    # Same bounding box used by the working local application.
    min_lat = site_lat - 0.6
    max_lat = site_lat + 0.6
    min_lon = site_lon - 0.8
    max_lon = site_lon + 0.8

    vessels = fetch_vessels(min_lat, min_lon, max_lat, max_lon)

    all_local_targets = []
    skipped_too_far = 0
    skipped_navigation_aid = 0
    skipped_stale = 0
    skipped_bad_position = 0
    skipped_fixed = 0

    for vessel in vessels:
        lat = vessel.get("lat")
        lon = vessel.get("lon")

        if lat is None or lon is None:
            skipped_bad_position += 1
            continue

        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            skipped_bad_position += 1
            continue

        distance = haversine_miles(site_lat, site_lon, lat, lon)

        if distance > MAX_DISTANCE_MILES:
            skipped_too_far += 1
            continue

        mmsi = vessel.get("mmsi")

        if is_navigation_aid(mmsi):
            skipped_navigation_aid += 1
            continue

        try:
            speed = float(vessel.get("sog") or 0.0)
        except (TypeError, ValueError):
            speed = 0.0

        age = age_minutes(vessel.get("ts"))

        if age is None or age > freshness_limit(speed):
            skipped_stale += 1
            continue

        try:
            course = float(vessel.get("cog") or 0.0)
        except (TypeError, ValueError):
            course = 0.0

        name = display_name(vessel)

        if is_fixed_infrastructure(name, mmsi, speed):
            skipped_fixed += 1
            continue

        movement_status, current_distance = classify_movement(
            lat, lon, speed, course, site_lat, site_lon
        )

        cpa_distance, cpa_minutes = calculate_cpa(
            lat, lon, speed, course, site_lat, site_lon
        )

        bearing = bearing_degrees(site_lat, site_lon, lat, lon)

        # Only browser-needed fields are published. Site coordinates and raw
        # vessel coordinates stay inside the GitHub Action.
        all_local_targets.append({
            "mmsi": mmsi,
            "name": name,
            "distance_miles": round(current_distance, 2),
            "bearing_degrees": round(bearing, 1),
            "direction": compass_direction(bearing),
            "speed_knots": round(speed, 1),
            "course_degrees": round(course, 1),
            "movement_status": movement_status,
            "cpa_distance_miles": round(cpa_distance, 2),
            "cpa_minutes": cpa_minutes,
            "destination": vessel.get("destination"),
            "ais_timestamp": vessel.get("ts"),
            "age_minutes": round(age, 1),
            "stale_warning": is_stale_warning(age),
            "source": vessel.get("source"),
        })

    visible_now = [
        v for v in all_local_targets
        if v["distance_miles"] <= VISIBLE_RADIUS_MILES
    ]

    coming_up = [
        v for v in all_local_targets
        if (
            v["distance_miles"] > VISIBLE_RADIUS_MILES
            and v["movement_status"] == "APPROACHING"
            and v["cpa_distance_miles"] <= VISIBLE_RADIUS_MILES
        )
    ]

    visible_mmsi = {v["mmsi"] for v in visible_now}
    coming_mmsi = {v["mmsi"] for v in coming_up}

    background = [
        v for v in all_local_targets
        if v["mmsi"] not in visible_mmsi
        and v["mmsi"] not in coming_mmsi
    ]

    visible_now.sort(key=lambda v: v["distance_miles"])
    coming_up.sort(key=lambda v: (v["cpa_minutes"], v["cpa_distance_miles"]))
    background.sort(key=lambda v: v["distance_miles"])

    now = utc_now_iso()

    return {
        "status": "ok",
        "last_attempt": now,
        "last_success": now,
        "error": None,
        "site": {
            "id": "m35_family",
            "name": site_name,
        },
        "settings": {
            "visible_radius_miles": VISIBLE_RADIUS_MILES,
            "max_collection_radius_miles": MAX_DISTANCE_MILES,
            "moving_max_age_minutes": MOVING_MAX_AGE_MINUTES,
            "stationary_max_age_minutes": STATIONARY_MAX_AGE_MINUTES,
            "cloud_snapshot_interval_minutes": 5,
        },
        "visible_now": visible_now,
        "coming_up": coming_up,
        "background": background,
        "stats": {
            "total_feed_vessels": len(vessels),
            "usable_local_targets": len(all_local_targets),
            "visible_now": len(visible_now),
            "coming_up": len(coming_up),
            "background": len(background),
            "skipped_too_far": skipped_too_far,
            "skipped_navigation_aid": skipped_navigation_aid,
            "skipped_fixed": skipped_fixed,
            "skipped_stale": skipped_stale,
            "skipped_bad_position": skipped_bad_position,
        },
    }


def main() -> None:
    snapshot = build_snapshot()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(
        "CESARops snapshot written:",
        f"visible={len(snapshot['visible_now'])}",
        f"coming={len(snapshot['coming_up'])}",
        f"background={len(snapshot['background'])}",
    )


if __name__ == "__main__":
    main()
