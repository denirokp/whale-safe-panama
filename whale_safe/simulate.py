"""Synthetic AIS generator — run the whole pipeline TODAY without an API key.

Generates plausible vessel tracks transiting the Gulf of Panama, a realistic mix
of compliant (<= 10 kn) and speeding ships, matching the real-world finding that
only ~10-19% of vessels keep to the limit (Guzman et al. 2020).

Timestamps are stamped inside a past in-season window (September) so `in_season`
is genuinely True and the dashboard demonstrates the full violation logic. The
data is clearly labelled SIMULATED in the dashboard — never presented as real.

Run:
    python -m whale_safe.simulate            # default 40 vessels
    python -m whale_safe.simulate --vessels 80 --reset
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta, timezone

from . import config, store

# A reference in-season day (1 Aug - 30 Nov). Year is arbitrary/historical;
# only month/day drive the season flag.
_SEASON_DAY = datetime(2025, 9, 15, 6, 0, 0, tzinfo=timezone.utc)

# Flag states and a small ship-name pool for readable demo output.
_FLAGS = ["PA", "LR", "MH", "SG", "GR", "HK", "MT", "CY"]
_NAME_PREFIX = ["STAR", "OCEAN", "PACIFIC", "MAERSK", "EVER", "CMA", "NORD",
                "CAPE", "GULF", "ATLANTIC", "BLUE", "ANDES"]
_NAME_SUFFIX = ["TRADER", "VOYAGER", "PIONEER", "SPIRIT", "EXPRESS", "BRIDGE",
                "HORIZON", "MARINER", "GLORY", "VENTURE", "LEADER", "SUMMIT"]


def _rand_name() -> str:
    return f"{random.choice(_NAME_PREFIX)} {random.choice(_NAME_SUFFIX)}"


def _rand_mmsi() -> str:
    # MMSI: 9 digits, first 3 = MID (country). 351/352/357 ~ Panama flag.
    mid = random.choice([351, 352, 357, 477, 538, 636, 563, 240])
    return f"{mid}{random.randint(100000, 999999)}"


def _track_through_zone(speeding: bool):
    """Generate a track transiting the real TSS corridor (toward/from the canal).

    Ships ride one of the two lanes (north- or southbound) so positions fall
    inside the precise ~7-nm corridor, not the whole gulf. Returns a list of
    (lat, lon, sog, cog) samples.
    """
    # Pick a lane. Northbound rides the eastern lane (~-79.36..-79.40); southbound
    # rides the western lane (~-79.44..-79.46). Lon held within the corridor with
    # small jitter; latitude spans across the 8 deg N seasonal line.
    northbound = random.random() < 0.5
    if northbound:
        lon_center = random.uniform(-79.40, -79.36)
        start_lat, end_lat = random.uniform(7.95, 8.10), random.uniform(8.55, 8.74)
    else:
        lon_center = random.uniform(-79.46, -79.44)
        start_lat, end_lat = random.uniform(8.55, 8.74), random.uniform(7.95, 8.10)
    jitter = random.uniform(-0.006, 0.006)

    if speeding:
        base_sog = random.uniform(11.5, 17.5)  # cargo/tanker cruise, over limit
    else:
        base_sog = random.uniform(6.0, 9.8)    # compliant

    steps = random.randint(6, 12)
    samples = []
    for i in range(steps):
        f = i / (steps - 1)
        lat = start_lat + (end_lat - start_lat) * f
        lon = lon_center + jitter * (f - 0.5) * 2
        sog = max(0.5, base_sog + random.uniform(-0.8, 0.8))
        cog = 0.0 if northbound else 180.0
        samples.append((lat, lon, sog, cog))
    return samples


def generate(vessels: int = 40, reset: bool = False, db_path: str = config.DB_PATH) -> None:
    store.init_db(db_path)
    if reset:
        store.reset(db_path)

    # Real-world: only ~10-19% compliant. Use ~15% compliant here.
    compliant_share = 0.15
    inserted = 0
    zone_hits = 0
    with store.connect(db_path) as conn:
        for v in range(vessels):
            mmsi = _rand_mmsi()
            name = _rand_name()
            speeding = random.random() > compliant_share
            samples = _track_through_zone(speeding)
            # Stagger each vessel's track start time across the day.
            t0 = _SEASON_DAY + timedelta(minutes=random.randint(0, 18 * 60))
            for i, (lat, lon, sog, cog) in enumerate(samples):
                ts = t0 + timedelta(minutes=10 * i)
                store.insert_position(
                    conn, mmsi=mmsi, name=name, lat=lat, lon=lon,
                    sog=sog, cog=cog, ts=ts,
                )
                inserted += 1
                from .geo import in_zone
                if in_zone(lat, lon):
                    zone_hits += 1
    print(
        f"Simulated {vessels} vessels -> {inserted} positions "
        f"({zone_hits} inside the zone), in-season day {_SEASON_DAY.date()}."
    )
    print("Launch the dashboard:  streamlit run dashboard/app.py")


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic AIS data for the Gulf of Panama.")
    ap.add_argument("--vessels", type=int, default=40)
    ap.add_argument("--reset", action="store_true", help="wipe existing data first")
    args = ap.parse_args()
    generate(vessels=args.vessels, reset=args.reset)


if __name__ == "__main__":
    main()
