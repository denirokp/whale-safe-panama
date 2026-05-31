"""Read-side aggregations for the dashboard."""

from __future__ import annotations

import pandas as pd

from . import config

# --- Flag (country) lookup by MMSI Maritime Identification Digits (MID) --------
# First 3 digits of an MMSI identify the flag state. Subset of the most common
# merchant flags seen in the Gulf of Panama. Returns (country, emoji).
_MID_FLAGS = {
    "PANAMA": ("🇵🇦", range(351, 358)),          # 351-357 + 370-373 below
    "PANAMA2": ("🇵🇦", range(370, 374)),
    "LIBERIA": ("🇱🇷", range(636, 638)),
    "MARSHALL IS.": ("🇲🇭", range(538, 539)),
    "SINGAPORE": ("🇸🇬", range(563, 567)),
    "HONG KONG": ("🇭🇰", range(477, 478)),
    "GREECE": ("🇬🇷", range(237, 242)),
    "MALTA": ("🇲🇹", range(215, 216)),
    "MALTA2": ("🇲🇹", range(248, 257)),
    "CYPRUS": ("🇨🇾", range(209, 213)),
    "USA": ("🇺🇸", range(366, 370)),
    "CHINA": ("🇨🇳", range(412, 415)),
    "JAPAN": ("🇯🇵", range(431, 433)),
    "SOUTH KOREA": ("🇰🇷", range(440, 442)),
    "BAHAMAS": ("🇧🇸", range(308, 312)),
    "DENMARK": ("🇩🇰", range(219, 221)),
    "GERMANY": ("🇩🇪", range(211, 212)),
    "NORWAY": ("🇳🇴", range(257, 260)),
    "CHILE": ("🇨🇱", range(725, 726)),
    "ECUADOR": ("🇪🇨", range(735, 736)),
    "COLOMBIA": ("🇨🇴", range(730, 731)),
}


def mmsi_to_flag(mmsi: str) -> tuple[str, str]:
    """Return (country, emoji) for an MMSI; ('Unknown', '🏳️') if unmatched."""
    try:
        mid = int(str(mmsi)[:3])
    except (ValueError, TypeError):
        return "Unknown", "🏳️"
    for name, (emoji, rng) in _MID_FLAGS.items():
        if mid in rng:
            return name.rstrip("2").title(), emoji
    return "Unknown", "🏳️"


def _q(conn, sql: str, params=()) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def overview(conn) -> dict:
    """Headline numbers for the top of the dashboard."""
    row = _q(
        conn,
        """
        SELECT
          COUNT(DISTINCT mmsi)                                   AS vessels,
          COUNT(*)                                               AS positions,
          SUM(in_zone)                                           AS zone_positions,
          SUM(CASE WHEN in_zone=1 THEN over_limit ELSE 0 END)    AS over_limit_pings,
          COUNT(DISTINCT CASE WHEN in_zone=1 THEN mmsi END)      AS vessels_in_zone,
          COUNT(DISTINCT CASE WHEN in_zone=1 AND over_limit=1
                              THEN mmsi END)                     AS vessels_over_limit
        FROM positions
        """,
    ).iloc[0]
    vz = int(row["vessels_in_zone"] or 0)
    vo = int(row["vessels_over_limit"] or 0)
    compliant_pct = round(100 * (vz - vo) / vz, 1) if vz else None
    return {
        "vessels": int(row["vessels"] or 0),
        "positions": int(row["positions"] or 0),
        "zone_positions": int(row["zone_positions"] or 0),
        "over_limit_pings": int(row["over_limit_pings"] or 0),
        "vessels_in_zone": vz,
        "vessels_over_limit": vo,
        "compliant_pct": compliant_pct,
        "speed_limit": config.SPEED_LIMIT_KNOTS,
    }


def leaderboard(conn) -> pd.DataFrame:
    """The 'board of transparency': vessels ranked by in-zone speeding.

    over_limit_pings = times the vessel was clocked over the limit inside the zone.
    violation_pings  = those that also fall in the official season (the formal breach).
    """
    return _q(
        conn,
        """
        SELECT
          mmsi,
          COALESCE(MAX(name), '(unknown)')                       AS name,
          SUM(in_zone)                                           AS zone_pings,
          ROUND(MAX(CASE WHEN in_zone=1 THEN sog END), 1)        AS max_sog_in_zone,
          ROUND(AVG(CASE WHEN in_zone=1 THEN sog END), 1)        AS avg_sog_in_zone,
          SUM(CASE WHEN in_zone=1 THEN over_limit ELSE 0 END)    AS over_limit_pings,
          SUM(CASE WHEN in_zone=1 AND over_limit=1 AND in_season=1
                   THEN 1 ELSE 0 END)                            AS violation_pings
        FROM positions
        WHERE in_zone = 1
        GROUP BY mmsi
        HAVING zone_pings > 0
        ORDER BY over_limit_pings DESC, max_sog_in_zone DESC
        """,
    )


def positions_for_map(conn) -> pd.DataFrame:
    """Recent in-zone positions for the map layer."""
    return _q(
        conn,
        """
        SELECT mmsi, name, ts, lat, lon, sog, in_zone, over_limit, in_season
        FROM positions
        WHERE lat IS NOT NULL AND lon IS NOT NULL
        ORDER BY ts DESC
        LIMIT 5000
        """,
    )


def best_performers(conn) -> pd.DataFrame:
    """Whale-friendly vessels: seen in the zone and NEVER exceeded the limit."""
    return _q(
        conn,
        """
        SELECT
          mmsi,
          COALESCE(MAX(name), '(unknown)')                AS name,
          SUM(in_zone)                                    AS zone_pings,
          ROUND(MAX(CASE WHEN in_zone=1 THEN sog END), 1) AS max_sog_in_zone
        FROM positions
        WHERE in_zone = 1
        GROUP BY mmsi
        HAVING SUM(CASE WHEN in_zone=1 THEN over_limit ELSE 0 END) = 0
           AND MAX(CASE WHEN in_zone=1 THEN sog END) IS NOT NULL
        ORDER BY zone_pings DESC, max_sog_in_zone ASC
        """,
    )


def speed_histogram(conn, bin_width: float = 2.0) -> pd.DataFrame:
    """Distribution of in-zone speeds, binned, for a histogram chart."""
    df = _q(
        conn,
        "SELECT sog FROM positions WHERE in_zone=1 AND sog IS NOT NULL AND sog >= ?",
        (config.MIN_TRANSIT_SOG_KNOTS,),
    )
    if df.empty:
        return pd.DataFrame(columns=["speed_bin", "count"])
    max_sog = max(20.0, float(df["sog"].max()) + bin_width)
    bins = [i * bin_width for i in range(int(max_sog // bin_width) + 2)]
    labels = [f"{int(b)}–{int(b + bin_width)}" for b in bins[:-1]]
    df["speed_bin"] = pd.cut(df["sog"], bins=bins, labels=labels, right=False)
    out = df.groupby("speed_bin", observed=False).size().reset_index(name="count")
    out["bin_start"] = [float(str(lbl).split("–")[0]) for lbl in out["speed_bin"]]
    out["over_limit"] = out["bin_start"] >= config.SPEED_LIMIT_KNOTS
    return out


def by_flag(conn) -> pd.DataFrame:
    """Per-flag breakdown: vessels in zone and how many exceeded the limit."""
    rows = _q(
        conn,
        """
        SELECT
          mmsi,
          MAX(CASE WHEN in_zone=1 THEN over_limit ELSE 0 END) AS ever_over
        FROM positions
        WHERE in_zone = 1
        GROUP BY mmsi
        """,
    )
    if rows.empty:
        return pd.DataFrame(columns=["flag", "vessels", "over_limit", "compliant_pct"])
    rows["flag"] = rows["mmsi"].map(lambda m: " ".join(mmsi_to_flag(m)[::-1]))
    agg = (
        rows.groupby("flag")
        .agg(vessels=("mmsi", "count"), over_limit=("ever_over", "sum"))
        .reset_index()
    )
    agg["compliant_pct"] = ((agg["vessels"] - agg["over_limit"]) / agg["vessels"] * 100).round(0)
    return agg.sort_values(["over_limit", "vessels"], ascending=False)
