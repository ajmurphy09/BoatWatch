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


def first_present(vessel: dict, *keys):
    for key in keys:
        value = vessel.get(key)
        if value not in (None, "", "Unknown", "UNKNOWN"):
            return value
    return None


def as_float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def vessel_length_ft(vessel: dict):
    # Prefer an explicit overall length if CESARops supplies one.
    direct = as_float(first_present(
        vessel, "length_ft", "lengthFeet", "length_feet"
    ))
    if direct is not None and direct > 0:
        return round(direct)

    meters = as_float(first_present(
        vessel, "length", "length_m", "lengthMeters", "ship_length"
    ))
    if meters is not None and meters > 0:
        return round(meters * 3.28084)

    # AIS static dimensions may be bow/stern distances in meters.
    bow = as_float(first_present(vessel, "dim_bow", "to_bow", "dimensionToBow"))
    stern = as_float(first_present(vessel, "dim_stern", "to_stern", "dimensionToStern"))
    if bow is not None and stern is not None and bow + stern > 0:
        return round((bow + stern) * 3.28084)

    return None


def raw_type_text(vessel: dict) -> str | None:
    value = first_present(
        vessel,
        "ship_type_text", "shipTypeText", "type_name", "typeName",
        "vessel_type", "vesselType", "type", "ship_type", "shipType",
    )
    return str(value).strip() if value is not None else None


def friendly_vessel_type(vessel: dict) -> tuple[str, list[str]]:
    raw = (raw_type_text(vessel) or "").strip()
    upper = raw.upper()
    name = str(vessel.get("name") or "").upper()
    haystack = f"{upper} {name}"

    badges = []

    rules = (
        (("COAST GUARD", "USCG"), "Coast Guard", "COAST GUARD"),
        (("LAW ENFORCEMENT", "POLICE", "SHERIFF"), "Law enforcement vessel", "LAW ENFORCEMENT"),
        (("SEARCH AND RESCUE", "RESCUE", "SAR"), "Search / rescue vessel", "RESCUE"),
        (("PILOT",), "Pilot vessel", "PILOT"),
        (("DREDG",), "Dredging vessel", "DREDGE"),
        (("RESEARCH", "SURVEY"), "Research / survey vessel", "RESEARCH"),
        (("TUG", "TOW"), "Tug / towing vessel", "TUG"),
        (("FISH",), "Fishing vessel", "FISHING"),
        (("PASSENGER", "FERRY"), "Passenger vessel", "PASSENGER"),
        (("PLEASURE", "YACHT"), "Pleasure craft", "PLEASURE CRAFT"),
        (("SAIL",), "Sailing vessel", "SAILING"),
        (("CARGO", "FREIGHT", "BULK", "CARRIER"), "Cargo / bulk vessel", "CARGO"),
        (("TANKER",), "Tanker", "TANKER"),
    )

    for needles, label, badge in rules:
        if any(n in haystack for n in needles):
            badges.append(badge)
            return label, badges

    # Numeric AIS ship type when exposed by the source.
    try:
        code = int(float(raw))
    except (TypeError, ValueError):
        code = None

    if code is not None:
        if 30 <= code <= 39:
            return "Special-purpose / fishing vessel", ["SPECIAL PURPOSE"]
        if 40 <= code <= 49:
            return "High-speed craft", ["HIGH SPEED"]
        if 60 <= code <= 69:
            return "Passenger vessel", ["PASSENGER"]
        if 70 <= code <= 79:
            return "Cargo vessel", ["CARGO"]
        if 80 <= code <= 89:
            return "Tanker", ["TANKER"]

    return (raw if raw else "Vessel"), badges


def visibility_assessment(distance_miles: float, length_ft: int | None) -> tuple[str, str]:
    # Deliberately conservative: this is a viewing aid, not a guarantee.
    if distance_miles <= 5:
        return "LIKELY VISIBLE", "Near the watch area"
    if distance_miles <= 10:
        if length_ft is None or length_ft >= 40:
            return "LIKELY VISIBLE", "Close enough to be a strong visual candidate"
        return "MAY BE VISIBLE", "Close, but a smaller vessel may be harder to spot"
    if distance_miles <= 15:
        if length_ft is not None and length_ft >= 300:
            return "LIKELY VISIBLE", "Large vessel within the visible zone"
        return "MAY BE VISIBLE", "Within the visible zone; haze and vessel size matter"
    return "UNLIKELY VISIBLE", "Outside the configured 15-mile visible zone"


def movement_explanation(status: str, speed: float, distance: float,
                         cpa_distance: float, cpa_minutes: int) -> str:
    if status == "STATIONARY":
        return "Stationary / holding position; it may be anchored, moored, or waiting."
    if status == "APPROACHING":
        if cpa_minutes > 0:
            return (
                f"Approaching the watch area; closest projected pass is "
                f"{cpa_distance:.1f} mi in about {cpa_minutes} min."
            )
        return "Approaching the watch area."
    if status == "DEPARTING":
        return "Moving away from the watch area."
    if status == "PASSING":
        return "Passing across the watch area at roughly the same distance."
    return f"Moving at {speed:.1f} kt, {distance:.1f} mi from the watch area."

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

        length_ft = vessel_length_ft(vessel)
        friendly_type, badges = friendly_vessel_type(vessel)
        visibility_label, visibility_reason = visibility_assessment(
            current_distance, length_ft
        )

        # Only browser-needed fields are published. Site coordinates and raw
        # vessel coordinates stay inside the GitHub Action.
        all_local_targets.append({
            "mmsi": mmsi,
            "imo": first_present(vessel, "imo", "IMO"),
            "callsign": first_present(vessel, "callsign", "callSign", "call_sign"),
            "name": name,
            "vessel_type": friendly_type,
            "vessel_type_raw": raw_type_text(vessel),
            "badges": badges,
            "length_ft": length_ft,
            "distance_miles": round(current_distance, 2),
            "bearing_degrees": round(bearing, 1),
            "direction": compass_direction(bearing),
            "speed_knots": round(speed, 1),
            "course_degrees": round(course, 1),
            "movement_status": movement_status,
            "movement_explanation": movement_explanation(
                movement_status, speed, current_distance,
                cpa_distance, cpa_minutes
            ),
            "visibility_label": visibility_label,
            "visibility_reason": visibility_reason,
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
