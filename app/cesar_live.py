from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from app.distance import (
    bearing_degrees,
    compass_direction,
    haversine_miles,
)


BASE_URL = "https://cesarops.com/api/ais/vessels"

MAX_DISTANCE_MILES = 50.0
VISIBLE_RADIUS_MILES = 15.0

MOVING_MAX_AGE_MINUTES = 30.0
STATIONARY_MAX_AGE_MINUTES = 90.0
STALE_WARNING_MINUTES = 15.0

STATIONARY_SPEED_KNOTS = 1.0

PROJECTION_MINUTES = 15.0
PASSING_THRESHOLD_MILES = 0.35

CPA_LOOKAHEAD_MINUTES = 180
CPA_STEP_MINUTES = 1


def fetch_vessels(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
) -> list[dict]:
    bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"

    url = BASE_URL + "?" + urllib.parse.urlencode({
        "bbox": bbox,
    })

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 GreenBayShipWatch/1.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.load(response)

    return data.get("vessels", [])


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        return None


def age_minutes(timestamp: str | None) -> float | None:
    parsed = parse_timestamp(timestamp)

    if parsed is None:
        return None

    now = datetime.now(timezone.utc)
    age = now - parsed

    return age.total_seconds() / 60.0


def is_navigation_aid(mmsi: object) -> bool:
    if mmsi is None:
        return False

    return str(mmsi).startswith("99")


def is_fixed_infrastructure(
    name: str,
    mmsi: object,
    speed_knots: float,
) -> bool:
    cleaned_name = name.strip().upper()

    if cleaned_name.startswith("D09"):
        return True

    infrastructure_terms = (
        "BUOY",
        "BEACON",
        "AIS STATION",
        "BASE STATION",
    )

    mmsi_text = str(mmsi) if mmsi is not None else ""

    if (
        speed_knots == 0.0
        and len(mmsi_text) < 9
        and any(term in cleaned_name for term in infrastructure_terms)
    ):
        return True

    return False


def project_position(
    latitude: float,
    longitude: float,
    speed_knots: float,
    course_degrees: float,
    minutes: float,
) -> tuple[float, float]:
    earth_radius_nm = 3440.065

    distance_nm = speed_knots * (minutes / 60.0)
    angular_distance = distance_nm / earth_radius_nm

    bearing = math.radians(course_degrees)
    lat1 = math.radians(latitude)
    lon1 = math.radians(longitude)

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1)
        * math.sin(angular_distance)
        * math.cos(bearing)
    )

    lon2 = lon1 + math.atan2(
        math.sin(bearing)
        * math.sin(angular_distance)
        * math.cos(lat1),
        math.cos(angular_distance)
        - math.sin(lat1) * math.sin(lat2),
    )

    return math.degrees(lat2), math.degrees(lon2)


def calculate_cpa(
    vessel_lat: float,
    vessel_lon: float,
    speed_knots: float,
    course_degrees: float,
    site_lat: float,
    site_lon: float,
) -> tuple[float, int]:
    current_distance = haversine_miles(
        site_lat,
        site_lon,
        vessel_lat,
        vessel_lon,
    )

    if speed_knots < STATIONARY_SPEED_KNOTS:
        return current_distance, 0

    best_distance = current_distance
    best_minute = 0

    for minute in range(
        CPA_STEP_MINUTES,
        CPA_LOOKAHEAD_MINUTES + 1,
        CPA_STEP_MINUTES,
    ):
        projected_lat, projected_lon = project_position(
            vessel_lat,
            vessel_lon,
            speed_knots,
            course_degrees,
            minute,
        )

        distance = haversine_miles(
            site_lat,
            site_lon,
            projected_lat,
            projected_lon,
        )

        if distance < best_distance:
            best_distance = distance
            best_minute = minute

    return best_distance, best_minute


def classify_movement(
    vessel_lat: float,
    vessel_lon: float,
    speed_knots: float,
    course_degrees: float,
    site_lat: float,
    site_lon: float,
) -> tuple[str, float]:
    current_distance = haversine_miles(
        site_lat,
        site_lon,
        vessel_lat,
        vessel_lon,
    )

    if speed_knots < STATIONARY_SPEED_KNOTS:
        return "STATIONARY", current_distance

    projected_lat, projected_lon = project_position(
        vessel_lat,
        vessel_lon,
        speed_knots,
        course_degrees,
        PROJECTION_MINUTES,
    )

    projected_distance = haversine_miles(
        site_lat,
        site_lon,
        projected_lat,
        projected_lon,
    )

    distance_change = projected_distance - current_distance

    if abs(distance_change) <= PASSING_THRESHOLD_MILES:
        return "PASSING", current_distance

    if distance_change < 0:
        return "APPROACHING", current_distance

    return "DEPARTING", current_distance


def display_name(vessel: dict) -> str:
    name = (vessel.get("name") or "").strip()
    mmsi = vessel.get("mmsi")

    if not name or name.lower() == "unknown":
        return f"Unknown vessel {mmsi}"

    return name


def freshness_limit(speed_knots: float) -> float:
    if speed_knots < STATIONARY_SPEED_KNOTS:
        return STATIONARY_MAX_AGE_MINUTES

    return MOVING_MAX_AGE_MINUTES


def is_stale_warning(age: float) -> bool:
    return age >= STALE_WARNING_MINUTES


def background_reason(vessel: dict) -> str:
    if vessel["distance_miles"] <= VISIBLE_RADIUS_MILES:
        return "Would be visible now"

    if vessel["movement_status"] == "APPROACHING":
        if vessel["cpa_distance_miles"] > VISIBLE_RADIUS_MILES:
            return (
                f"Approaching, but closest pass is "
                f"{vessel['cpa_distance_miles']:.2f} mi"
            )

        return "Approaching visible zone"

    if vessel["movement_status"] == "DEPARTING":
        return "Outside visible zone and departing"

    if vessel["movement_status"] == "STATIONARY":
        return "Stationary but outside visible zone"

    return "Outside visible zone"


def print_vessel(vessel: dict, coming_up: bool = False) -> None:
    print(
        f"{vessel['display_name']:<28} "
        f"{vessel['distance_miles']:6.2f} mi | "
        f"{vessel['direction']:>3} | "
        f"{vessel['speed_knots']:5.1f} kt | "
        f"{vessel['movement_status']}"
    )

    print(
        f"  Course: {vessel['course_degrees']:.1f}° | "
        f"MMSI: {vessel.get('mmsi')} | "
        f"{vessel['age_minutes']:.1f} min old"
    )

    if vessel["stale_warning"]:
        print("  WARNING: position may be stale")

    if vessel["movement_status"] != "STATIONARY":
        print(
            f"  Closest approach: "
            f"{vessel['cpa_distance_miles']:.2f} mi "
            f"in ~{vessel['cpa_minutes']} min"
        )

    destination = vessel.get("destination")

    if destination and destination != "Unknown":
        print(f"  Destination: {destination}")

    if coming_up:
        print(
            f"  Expected to enter the "
            f"{VISIBLE_RADIUS_MILES:.0f}-mile visible zone"
        )

    print()


def main() -> None:
    site = get_site()

    site_lat = float(site["latitude"])
    site_lon = float(site["longitude"])

    min_lat = site_lat - 0.6
    max_lat = site_lat + 0.6
    min_lon = site_lon - 0.8
    max_lon = site_lon + 0.8

    vessels = fetch_vessels(
        min_lat,
        min_lon,
        max_lat,
        max_lon,
    )

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

        distance = haversine_miles(
            site_lat,
            site_lon,
            lat,
            lon,
        )

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

        if age is None:
            skipped_stale += 1
            continue

        max_age = freshness_limit(speed)

        if age > max_age:
            skipped_stale += 1
            continue

        try:
            course = float(vessel.get("cog") or 0.0)
        except (TypeError, ValueError):
            course = 0.0

        name = display_name(vessel)

        if is_fixed_infrastructure(
            name,
            mmsi,
            speed,
        ):
            skipped_fixed += 1
            continue

        movement_status, current_distance = classify_movement(
            lat,
            lon,
            speed,
            course,
            site_lat,
            site_lon,
        )

        cpa_distance, cpa_minutes = calculate_cpa(
            lat,
            lon,
            speed,
            course,
            site_lat,
            site_lon,
        )

        bearing = bearing_degrees(
            site_lat,
            site_lon,
            lat,
            lon,
        )

        all_local_targets.append({
            **vessel,
            "display_name": name,
            "distance_miles": current_distance,
            "bearing": bearing,
            "direction": compass_direction(bearing),
            "age_minutes": age,
            "speed_knots": speed,
            "course_degrees": course,
            "movement_status": movement_status,
            "cpa_distance_miles": cpa_distance,
            "cpa_minutes": cpa_minutes,
            "stale_warning": is_stale_warning(age),
        })

    visible_now = [
        vessel
        for vessel in all_local_targets
        if vessel["distance_miles"] <= VISIBLE_RADIUS_MILES
    ]

    coming_up = [
        vessel
        for vessel in all_local_targets
        if (
            vessel["distance_miles"] > VISIBLE_RADIUS_MILES
            and vessel["movement_status"] == "APPROACHING"
            and vessel["cpa_distance_miles"] <= VISIBLE_RADIUS_MILES
        )
    ]

    visible_ids = {
        vessel.get("mmsi")
        for vessel in visible_now
    }

    coming_ids = {
        vessel.get("mmsi")
        for vessel in coming_up
    }

    background = [
        vessel
        for vessel in all_local_targets
        if (
            vessel.get("mmsi") not in visible_ids
            and vessel.get("mmsi") not in coming_ids
        )
    ]

    visible_now.sort(
        key=lambda vessel: vessel["distance_miles"]
    )

    coming_up.sort(
        key=lambda vessel: (
            vessel["cpa_minutes"],
            vessel["cpa_distance_miles"],
        )
    )

    background.sort(
        key=lambda vessel: vessel["distance_miles"]
    )

    print(f"Site: {site['name']}")
    print(f"Coordinates: {site_lat}, {site_lon}")
    print()

    print(f"Total feed vessels: {len(vessels)}")
    print(
        f"Usable AIS targets within {MAX_DISTANCE_MILES:.0f} miles: "
        f"{len(all_local_targets)}"
    )
    print()

    print("FILTER SUMMARY")
    print(f"  Too far away:         {skipped_too_far}")
    print(f"  Navigation aids:      {skipped_navigation_aid}")
    print(f"  Fixed infrastructure: {skipped_fixed}")
    print(f"  Stale positions:      {skipped_stale}")
    print(f"  Bad position data:    {skipped_bad_position}")
    print()

    print("=" * 70)
    print("VISIBLE NOW")
    print(f"Within {VISIBLE_RADIUS_MILES:.0f} miles of the houses")
    print("=" * 70)
    print()

    if not visible_now:
        print("No vessels currently in the visible zone.")
        print()
    else:
        for vessel in visible_now:
            print_vessel(vessel)

    print("=" * 70)
    print("COMING UP")
    print(
        f"Approaching vessels expected to enter "
        f"within {VISIBLE_RADIUS_MILES:.0f} miles"
    )
    print("=" * 70)
    print()

    if not coming_up:
        print("No incoming vessels currently expected in the visible zone.")
        print()
    else:
        for vessel in coming_up:
            print_vessel(vessel, coming_up=True)

    print("=" * 70)
    print("BACKGROUND / DEBUG")
    print("Valid local AIS targets not shown on the main board")
    print("=" * 70)
    print()

    if not background:
        print("No background targets.")
        print()
    else:
        for vessel in background:
            print(
                f"{vessel['display_name']:<28} "
                f"{vessel['distance_miles']:6.2f} mi | "
                f"{vessel['direction']:>3} | "
                f"{vessel['speed_knots']:5.1f} kt | "
                f"{vessel['movement_status']}"
            )

            print(
                f"  Reason: {background_reason(vessel)}"
            )

            print(
                f"  CPA: {vessel['cpa_distance_miles']:.2f} mi "
                f"in ~{vessel['cpa_minutes']} min | "
                f"{vessel['age_minutes']:.1f} min old"
            )

            if vessel["stale_warning"]:
                print("  WARNING: position may be stale")

            print()


if __name__ == "__main__":
    main()
