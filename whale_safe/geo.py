"""Geofencing and season logic — no external dependencies.

Two distinct notions, kept separate on purpose (see config.py honesty note):
- over_limit: physical fact — vessel is inside the zone AND faster than the limit.
  True year-round. Useful for off-season data reconnaissance.
- violation:  breach of the *official* IMO rule = over_limit AND inside the season.

The dashboard reports both, clearly labelled, so a May reading (off-season) is not
mislabelled as a "violation".
"""

from __future__ import annotations

from datetime import date, datetime

from . import config


def point_in_polygon(lat: float, lon: float, polygon=None) -> bool:
    """Ray-casting point-in-polygon test. polygon is a list of (lat, lon)."""
    if polygon is None:
        polygon = config.SPEED_ZONE_POLYGON
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        # Treat lat as y, lon as x.
        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / (yj - yi) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def in_zone(lat: float, lon: float) -> bool:
    """Is the position inside the Panama seasonal speed area?"""
    return point_in_polygon(lat, lon)


def in_season(when: date | datetime | None = None) -> bool:
    """Is `when` within the 1 Aug - 30 Nov seasonal window?"""
    if when is None:
        raise ValueError("in_season requires an explicit date (no implicit 'now')")
    if isinstance(when, datetime):
        when = when.date()
    md = (when.month, when.day)
    return config.SEASON_START <= md <= config.SEASON_END


def over_limit(sog_knots: float | None) -> bool:
    """Is the vessel transiting faster than the speed limit?

    None SOG (unknown) -> False (do not accuse on missing data).
    SOG below MIN_TRANSIT_SOG -> False (moored/drifting, not transiting).
    """
    if sog_knots is None:
        return False
    if sog_knots < config.MIN_TRANSIT_SOG_KNOTS:
        return False
    return sog_knots > config.SPEED_LIMIT_KNOTS


def classify(lat: float, lon: float, sog_knots: float | None, when: date | datetime):
    """Return (in_zone, over_limit, in_season, is_violation) for one position."""
    z = in_zone(lat, lon)
    ol = z and over_limit(sog_knots)
    seas = in_season(when)
    violation = ol and seas
    return z, ol, seas, violation
