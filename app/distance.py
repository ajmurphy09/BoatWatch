from __future__ import annotations

import math


EARTH_RADIUS_MILES = 3958.7613


def haversine_miles(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Return great-circle distance between two latitude/longitude points
    in statute miles.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(dlambda / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_MILES * c


def bearing_degrees(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Return initial bearing from point 1 to point 2 in degrees,
    where 0° = north, 90° = east, 180° = south, 270° = west.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)

    x = math.sin(dlambda) * math.cos(phi2)

    y = (
        math.cos(phi1) * math.sin(phi2)
        - math.sin(phi1)
        * math.cos(phi2)
        * math.cos(dlambda)
    )

    bearing = math.degrees(math.atan2(x, y))

    return (bearing + 360) % 360


def compass_direction(bearing: float) -> str:
    """
    Convert a degree bearing into one of 16 compass directions.
    """
    directions = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    ]

    index = round(bearing / 22.5) % 16
    return directions[index]


if __name__ == "__main__":
    house_lat = 45.0
    house_lon = -87.5

    vessel_lat = 45.05
    vessel_lon = -87.4

    distance = haversine_miles(
        house_lat,
        house_lon,
        vessel_lat,
        vessel_lon,
    )

    bearing = bearing_degrees(
        house_lat,
        house_lon,
        vessel_lat,
        vessel_lon,
    )

    print(f"Distance: {distance:.2f} miles")
    print(f"Bearing: {bearing:.1f}°")
    print(f"Direction: {compass_direction(bearing)}")
