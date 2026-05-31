"""Global Fishing Watch (GFW) — real satellite-AIS compliance for the corridor.

aisstream.io has no offshore coverage of the Gulf-of-Panama TSS corridor. GFW combines
satellite AIS and covers it, including cargo/tanker/carrier vessels — the ships that
strike whales. GFW's public v3 API has no raw per-vessel track endpoint, but the 4Wings
report (dataset `public-global-presence`) aggregates vessel-presence over a polygon and
date range, filterable by vessel type AND speed bucket. That yields the project's
headline on REAL data: the share of commercial-vessel time in the corridor spent over
the 10-knot whale limit during a season.

Verified against the live API (2026-05-31). Key request facts learned the hard way:
- Must use POST with the polygon in the body as `geojson`.
- Filters ONLY apply when `group-by` is set (else the report returns an unfiltered
  per-vessel list). We use `group-by=FLAG` so filters apply AND we get a per-flag split.
- `in (...)` filter values need DOUBLE quotes: vessel_type in ("cargo"), speed in ("10-15").
- The aggregated value is in the `hours` field (vessel-presence hours), not `value`.
- `spatial-resolution` (HIGH/LOW) is required.

Metric note (surfaced in the UI): this is presence-HOURS weighted. Slow/anchored vessels
near the canal approach linger and inflate the compliant bucket, so this reads more
optimistically than per-transit compliance studies (Guzman et al.: only ~10-19% of ships
kept <=10 kn). Both are honest; they measure different things.

Free token (non-commercial): https://globalfishingwatch.org/our-apis/  (env GFW_API_TOKEN)
"""

from __future__ import annotations

import os

import requests

from . import config

API_URL = "https://gateway.api.globalfishingwatch.org/v3/4wings/report"
PRESENCE_DATASET = "public-global-presence:latest"

SPEED_BUCKETS = ["<2", "2-4", "4-6", "6-10", "10-15", "15-25", ">25"]
OVER_LIMIT_BUCKETS = ["10-15", "15-25", ">25"]
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
    """Our exact TSS corridor polygon as GeoJSON ([lon, lat] ring)."""
    ring = [[lon, lat] for (lat, lon) in config.SPEED_ZONE_POLYGON]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def _type_filter() -> str:
    return 'vessel_type in (' + ", ".join(f'"{t}"' for t in SHIP_TYPES) + ')'


def _report_rows(token: str, date_range: str, speed_bucket: str, timeout: int = 90) -> list[dict]:
    """One 4Wings presence report for a speed bucket, grouped by flag.

    Returns a list of {flag, hours, vesselIDs, ...} rows (commercial vessels only).
    """
    params = {
        "datasets[0]": PRESENCE_DATASET,
        "date-range": date_range,
        "temporal-resolution": "ENTIRE",
        "spatial-resolution": "LOW",
        "group-by": "FLAG",
        "format": "JSON",
        "filters[0]": f'speed in ("{speed_bucket}")',
        "filters[1]": _type_filter(),
    }
    resp = requests.post(
        API_URL, params=params, json={"geojson": _polygon_geojson()},
        headers={"Authorization": f"Bearer {token}"}, timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    entries = data.get("entries") or []
    if not entries or not entries[0]:
        return []
    key = next(iter(entries[0].keys()))
    return entries[0][key] or []


def season_report(
    token: str | None = None,
    date_range: tuple[str, str] = DEFAULT_SEASON,
) -> dict | None:
    """Real corridor compliance for commercial vessels over a season (GFW satellite AIS).

    Returns a dict with the speed distribution (hours per bucket), totals, compliance %,
    and a per-flag breakdown (hours over vs total -> over %). None if no token.
    """
    token = token or get_token()
    if not token:
        return None
    dr = f"{date_range[0]},{date_range[1]}"

    distribution: dict[str, float] = {}
    flag_total: dict[str, float] = {}
    flag_over: dict[str, float] = {}
    for bucket in SPEED_BUCKETS:
        rows = _report_rows(token, dr, bucket)
        bucket_hours = 0.0
        for row in rows:
            hrs = float(row.get("hours") or 0)
            flag = row.get("flag") or "UNK"
            bucket_hours += hrs
            flag_total[flag] = flag_total.get(flag, 0.0) + hrs
            if bucket in OVER_LIMIT_BUCKETS:
                flag_over[flag] = flag_over.get(flag, 0.0) + hrs
        distribution[bucket] = bucket_hours

    total = sum(distribution.values())
    over = sum(distribution[b] for b in OVER_LIMIT_BUCKETS)
    compliant_pct = round(100 * (total - over) / total, 1) if total > 0 else None

    flags = []
    for flag, tot in flag_total.items():
        ov = flag_over.get(flag, 0.0)
        flags.append({
            "flag": flag,
            "hours": round(tot, 1),
            "over_hours": round(ov, 1),
            "over_pct": round(100 * ov / tot, 0) if tot > 0 else 0,
        })
    flags.sort(key=lambda f: f["over_hours"], reverse=True)

    return {
        "date_range": date_range,
        "distribution": distribution,
        "total_hours": round(total, 1),
        "over_hours": round(over, 1),
        "compliant_pct": compliant_pct,
        "over_pct": round(100 * over / total, 1) if total else None,
        "by_flag": flags,
        "ship_types": SHIP_TYPES,
        "source": "Global Fishing Watch — AIS vessel presence (satellite)",
    }


def probe(date_range: tuple[str, str] = DEFAULT_SEASON) -> None:
    """CLI smoke test against a real token."""
    token = get_token()
    if not token:
        raise SystemExit("GFW_API_TOKEN not set: https://globalfishingwatch.org/our-apis/")
    print(f"GFW corridor presence, season {date_range[0]}..{date_range[1]} (commercial vessels):")
    res = season_report(token, date_range)
    for b, h in res["distribution"].items():
        print(f"  {b:>6}: {h:>8.0f} h")
    print(f"\n  compliant <=10 kn : {res['compliant_pct']}%")
    print(f"  over 10 kn        : {res['over_pct']}%  ({res['over_hours']:.0f} of {res['total_hours']:.0f} h)")
    print("  top flags by over-limit hours:")
    for f in res["by_flag"][:6]:
        print(f"    {f['flag']:4} {f['over_hours']:>6.0f}h over / {f['hours']:>6.0f}h  ({f['over_pct']:.0f}% over)")


if __name__ == "__main__":
    probe()
