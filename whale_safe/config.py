"""Configuration: the Panama whale-protection zone, season, and speed limit.

Sources (verified 2026-05-31):
- IMO adopted a Traffic Separation Scheme (TSS) in the Gulf of Panama, effective
  00:00 UTC 1 December 2014 (MSC.93, resolution A.858(20)).
- Seasonal speed restriction: <= 10 knots SOG, 1 August - 30 November each year,
  northwards of latitude 8 deg 00'.0 N, applying to both lanes of the TSS.
- Scientific basis: Guzman et al. 2012/2020 — strikes below 10 kn rarely injure
  whales; cargo/tanker ships in the gulf typically run 15-17 kn.
- Compliance (Guzman et al. 2020, Marine Policy): route adherence 86-90%, but only
  10-19% of ships kept <= 10 kn — exactly the gap this dashboard targets.

HONESTY NOTE: SPEED_ZONE_POLYGON below now follows the EXACT official IMO TSS
lane boundaries (Part I — Gulf of Panama), clipped to north of latitude 8 deg 00' N
where the seasonal speed restriction applies. All 12 scheme vertices are kept in
TSS_PART1_VERTICES for full traceability. The official rule targets the TSS *lanes*;
real whale-strike risk extends somewhat beyond them (the flanking inshore traffic
zones and adjacent gulf waters) — a possible future widening, but we deliberately
keep the geofence to the defensible, officially-defined lanes. A transparency tool
must not over-claim: the dashboard still surfaces AIS/spoofing caveats in the UI.
"""

from __future__ import annotations

# --- Speed rule ------------------------------------------------------------
SPEED_LIMIT_KNOTS = 10.0  # IMO seasonal recommendation, <= 10 kn SOG

# Seasonal window (inclusive), month/day. 1 Aug - 30 Nov.
SEASON_START = (8, 1)
SEASON_END = (11, 30)

# Below this SOG a vessel is treated as moored/drifting, not "transiting".
# Avoids flagging anchored ships as compliant or violators meaninglessly.
MIN_TRANSIT_SOG_KNOTS = 1.0

# --- Geofence --------------------------------------------------------------
# Precise polygon (lat, lon) of the seasonal speed area: the OUTER ENVELOPE of the
# IMO Gulf-of-Panama TSS (western edge of the southbound lane -> eastern edge of the
# northbound lane), clipped to north of 8 deg 00' N where the 10-kn rule applies.
# Width at 8 deg N is ~7 nm — the real shipping corridor, not the whole gulf.
SPEED_ZONE_POLYGON = [
    (8.0000, -79.4700),   # SW — 8 deg N clip on the southbound lane west edge
    (8.5833, -79.4700),   # (8) southbound lane west boundary
    (8.7333, -79.4667),   # (7) north end, southbound lane west boundary
    (8.7667, -79.4103),   # (10) north end, northbound lane east boundary
    (8.5833, -79.3500),   # (11) northbound lane east boundary
    (8.0000, -79.3500),   # SE — 8 deg N clip on the northbound lane east edge
]

# Wider bounding box for the AIS subscription (we ingest a margin around the
# zone so we can see vessels approaching and compute behaviour, then geofence).
# Format here is (south, west, north, east) in decimal degrees.
SUBSCRIPTION_BBOX = (7.0, -80.5, 9.2, -78.0)

# All 12 official IMO vertices of the TSS, Part I — Gulf of Panama (reference /
# traceability). Source: IMO MSC.93, NtM 3719(P)/14; confirmed by Panama Canal
# Authority advisory. Converted from deg/decimal-minutes to decimal degrees.
TSS_PART1_VERTICES = {
    # Central separation zone
    1: (8.7450, -79.4500),   # 8 deg 44.70' N  79 deg 27.00' W
    2: (8.5833, -79.4333),   # 8 deg 35.00' N  79 deg 26.00' W
    3: (7.7500, -79.4333),   # 7 deg 45.00' N  79 deg 26.00' W
    4: (7.7500, -79.3833),   # 7 deg 45.00' N  79 deg 23.00' W
    5: (8.5833, -79.3833),   # 8 deg 35.00' N  79 deg 23.00' W
    6: (8.7570, -79.4240),   # 8 deg 45.42' N  79 deg 25.44' W
    # Southbound lane — western boundary
    7: (8.7333, -79.4667),   # 8 deg 44.00' N  79 deg 28.00' W
    8: (8.5833, -79.4700),   # 8 deg 35.00' N  79 deg 28.20' W
    9: (7.7500, -79.4700),   # 7 deg 45.00' N  79 deg 28.20' W
    # Northbound lane — eastern boundary
    10: (8.7667, -79.4103),  # 8 deg 46.00' N  79 deg 24.62' W
    11: (8.5833, -79.3500),  # 8 deg 35.00' N  79 deg 21.00' W
    12: (7.7500, -79.3500),  # 7 deg 45.00' N  79 deg 21.00' W
}

# --- Storage ---------------------------------------------------------------
DB_PATH = "whale_safe.db"

# --- AIS source ------------------------------------------------------------
AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"
