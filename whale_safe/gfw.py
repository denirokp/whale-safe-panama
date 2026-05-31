"""Global Fishing Watch (GFW) — real satellite-AIS compliance stats for the corridor.

aisstream.io has no offshore coverage of the Gulf-of-Panama TSS corridor (terrestrial
receivers don't reach it). GFW combines satellite AIS, so it DOES cover the corridor and
includes cargo / tanker / carrier vessels — exactly the ships that strike whales.

GFW's public v3 API has NO raw per-vessel track endpoint, but its **4Wings report**
(dataset `public-global-presence`) returns vessel-presence aggregated over a polygon and
date range, filterable by vessel type AND speed bucket. That gives the headline the whole
project is about: the REAL share of cargo/tanker traffic in the corridor that exceeded the
10-knot whale limit during a season — from satellite data, not an estimate.

What this gives:  real compliance %, real speed distribution, by vessel type.
What it can't:    named individual vessels / a "top speeders" leaderboard, real-time.

Free token (non-commercial): https://globalfishingwatch.org/our-apis/
Set it as GFW_API_TOKEN (Streamlit secrets / env / .env).

NOTE: response shape and filter syntax below follow the documented API; they are tuned
against a real token in gfw.probe(). Until verified, treat parsing as best-effort.
"""

from __future__ import annotations

import os

import requests

from . import config

API_URL = "https://gateway.api.globalfishingwatch.org/v3/4wings/report"
PRESENCE_DATASET = "public-global-presence:latest"

# Speed buckets as defined by the 4Wings presence dataset (knots).
SPEED_BUCKETS = ["<2", "2-4", "4-6", "6-10", "10-15", "15-25", ">25"]
# Buckets that count as OVER the 10-knot limit.
OVER_LIMIT_BUCKETS = ["10-15", "15-25", ">25"]
# Vessel types relevant to whale strikes (large commercial traffic).
SHIP_TYPES = ["cargo", "bunker_or_tanker", "carrier", "passenger"]

# Last completed humpback season before today (2026-05-31): 1 Aug - 30 Nov 2025.
DEFAULT_SEASON = ("2025-08-01", "2025-11-30")


def get_token() -> str | None:
    """Resolve the GFW token: Streamlit secrets -> env -> .env -> None."""
    try:
        import streamlit as st

        if "GFW_API_TOKEN" in st.secrets:
            tok = str(st.secrets["GFW_API_TOKEN"]).strip()
            if tok:
                return tok
    except Exception:
        pass
    tok = os.environ.get("GFW_API_TOKEN")
    if not tok:
        try:
            from dotenv import load_dotenv

            load_dotenv()
            tok = os.environ.get("GFW_API_TOKEN")
        except ImportError:
            pass
    return tok.strip() if tok else None


def _polygon_geojson() -> dict:
    """Our exact TSS corridor polygon as a GeoJSON Polygon ([lon, lat] rings)."""
    ring = [[lon, lat] for (lat, lon) in config.SPEED_ZONE_POLYGON]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def _report_value(token: str, *, date_range: str, filters: list[str], timeout: int = 60) -> float:
    """Run one 4Wings presence report over the corridor; return total presence value.

    Presence is aggregated vessel-hours (the API's report value) for the given filters.
    """
    params = {
        "datasets[0]": PRESENCE_DATASET,
        "date-range": date_range,
        "temporal-resolution": "ENTIRE",
        "format": "JSON",
    }
    for i, f in enumerate(filters):
        params[f"filters[{i}]"] = f
    body = {"geojson": _polygon_geojson()}
    resp = requests.post(
        API_URL, params=params, json=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return _sum_report(resp.json())


def _sum_report(payload) -> float:
    """Sum numeric 'value' fields from a 4Wings report response (shape-tolerant)."""
    total = 0.0

    def walk(node):
        nonlocal total
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "value" and isinstance(v, (int, float)):
                    total += float(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return total


def _type_filter() -> str:
    quoted = ", ".join(f"'{t}'" for t in SHIP_TYPES)
    return f"vessel_type in ({quoted})"


def season_compliance(
    token: str | None = None,
    date_range: tuple[str, str] = DEFAULT_SEASON,
) -> dict | None:
    """Real corridor compliance for a season, from GFW satellite-AIS presence.

    Returns a dict with the full speed distribution, total presence, over-limit
    presence and the compliance percentage — or None if no token.
    """
    token = token or get_token()
    if not token:
        return None
    dr = f"{date_range[0]},{date_range[1]}"
    type_f = _type_filter()
    distribution: dict[str, float] = {}
    for bucket in SPEED_BUCKETS:
        distribution[bucket] = _report_value(
            token, date_range=dr, filters=[type_f, f"speed = '{bucket}'"]
        )
    total = sum(distribution.values())
    over = sum(distribution[b] for b in OVER_LIMIT_BUCKETS)
    compliant_pct = round(100 * (total - over) / total, 1) if total > 0 else None
    return {
        "date_range": date_range,
        "distribution": distribution,
        "total_presence": total,
        "over_limit_presence": over,
        "compliant_pct": compliant_pct,
        "ship_types": SHIP_TYPES,
        "source": "Global Fishing Watch — AIS vessel presence (satellite)",
    }


def probe(date_range: tuple[str, str] = DEFAULT_SEASON) -> None:
    """CLI smoke test against a real token — prints the raw shape + computed compliance."""
    token = get_token()
    if not token:
        raise SystemExit("GFW_API_TOKEN not set. Get a free token: https://globalfishingwatch.org/our-apis/")
    dr = f"{date_range[0]},{date_range[1]}"
    print(f"Probing GFW 4Wings presence over the corridor, {dr} ...")
    # Raw single request to inspect response shape.
    params = {
        "datasets[0]": PRESENCE_DATASET, "date-range": dr,
        "temporal-resolution": "ENTIRE", "format": "JSON",
        "filters[0]": _type_filter(),
    }
    r = requests.post(
        API_URL, params=params, json={"geojson": _polygon_geojson()},
        headers={"Authorization": f"Bearer {token}"}, timeout=60,
    )
    print("HTTP", r.status_code)
    print("Body (first 800 chars):", str(r.text)[:800])
    if r.ok:
        result = season_compliance(token, date_range)
        print("\nComputed:", result)


if __name__ == "__main__":
    probe()
