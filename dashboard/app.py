"""Whale Safe Panama — public transparency dashboard (Streamlit).

Are ships slowing down for whales in the Gulf of Panama? This public board shows
who respects the 10-knot whale-protection speed limit and who speeds through.
Value mechanism: transparency -> pressure -> compliance -> fewer whale strikes.

Run locally:   streamlit run dashboard/app.py
Live data:     set AISSTREAM_API_KEY (env / .streamlit/secrets.toml / Cloud secrets)
No key:        falls back to a clearly-labelled SIMULATED demo.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

# Allow running from repo root without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from whale_safe import analytics, config, gfw, live, simulate, store  # noqa: E402
from whale_safe.geo import in_season  # noqa: E402

st.set_page_config(page_title="Whale Safe Panama", page_icon="🐋", layout="wide")

# --------------------------------------------------------------------------- #
# Styling — ocean theme
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
      .block-container { padding-top: 2rem; max-width: 1200px; }
      .hero { background: linear-gradient(135deg,#06243a 0%,#0b3a55 60%,#13728a 100%);
              border-radius: 18px; padding: 28px 32px; color: #eaf6fb; margin-bottom: 14px; }
      .hero h1 { font-size: 2.5rem; margin: 0 0 6px 0; }
      .hero p  { font-size: 1.12rem; line-height: 1.5; margin: 0; color:#cfe9f3; max-width: 820px; }
      .badge { display:inline-block; padding:4px 12px; border-radius:999px; font-weight:600;
               font-size:0.85rem; margin-top:14px; }
      .badge-live { background:#0c7a3f; color:#d7ffe7; }
      .badge-demo { background:#9a6a00; color:#fff3d6; }
      .cards { display:flex; gap:14px; flex-wrap:wrap; margin: 6px 0 4px 0; }
      .card { flex:1 1 180px; border-radius:14px; padding:18px 20px; background:#f3f8fb;
              border:1px solid #e0ebf2; }
      .card .v { font-size:2.4rem; font-weight:700; line-height:1; }
      .card .l { font-size:0.92rem; color:#52707f; margin-top:6px; }
      .card.red .v { color:#d62828; }
      .card.green .v { color:#147a45; }
      .card.blue .v { color:#0b6e8a; }
      .stakes { color:#445; font-size:0.98rem; line-height:1.55; }
      .legend { font-size:0.9rem; color:#52707f; }
      .foot { color:#7a8c95; font-size:0.85rem; line-height:1.6; margin-top:8px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Data loading: live snapshot (cached) or simulated demo fallback
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=180, show_spinner="Fetching live ship positions…")
def refresh_live() -> int:
    """Pull a fresh live AIS window and persist it. Returns #positions stored."""
    snap = live.fetch_live_snapshot()
    if not snap:
        return 0
    store.init_db()
    with store.connect() as conn:
        for p in snap:
            store.insert_position(
                conn, mmsi=p["mmsi"], name=p["name"], lat=p["lat"], lon=p["lon"],
                sog=p["sog"], cog=p["cog"], ts=p["ts"],
            )
    return len(snap)


@st.cache_data(ttl=3600, show_spinner=False)
def ensure_demo() -> None:
    store.init_db()
    with store.connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM positions WHERE in_zone=1").fetchone()[0]
    if n == 0:
        simulate.generate(vessels=60, reset=True)


def load() -> str:
    """Prepare data, return mode: 'live' or 'demo'."""
    store.init_db()
    has_key = live.get_api_key() is not None
    mode = "demo"
    if has_key:
        refresh_live()
    with store.connect() as conn:
        zone_n = conn.execute("SELECT COUNT(*) FROM positions WHERE in_zone=1").fetchone()[0]
    if has_key and zone_n > 0:
        mode = "live"
    else:
        ensure_demo()
        mode = "demo"
    return mode


def flag_label(mmsi: str) -> str:
    country, emoji = analytics.mmsi_to_flag(mmsi)
    return f"{emoji} {country}"


@st.cache_data(ttl=21600, show_spinner="Loading real season data (Global Fishing Watch)…")
def load_gfw() -> dict | None:
    """Real corridor compliance from GFW satellite AIS (historical; cached 6h)."""
    try:
        return gfw.season_report()
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Hero — painted FIRST so the page shows instantly while data loads below.
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <div class="hero">
      <h1>🐋 Whale Safe Panama</h1>
      <p>Endangered humpback whales cross one of the world's busiest shipping lanes here.
      Ships are asked to slow to <b>10 knots</b> in the Gulf of Panama so a collision
      doesn't kill a whale. <b>This dashboard shows who actually slows down — and who doesn't.</b></p>
    </div>
    """,
    unsafe_allow_html=True,
)
badge_slot = st.empty()

# Now load data (may pull a brief live AIS snapshot — bounded to ~12s).
with st.spinner("Loading ship data…"):
    mode = load()
    with store.connect() as conn:
        ov = analytics.overview(conn)
        board = analytics.leaderboard(conn)
        best = analytics.best_performers(conn)
        pts = analytics.positions_for_map(conn)
        hist = analytics.speed_histogram(conn)
        flags = analytics.by_flag(conn)

season_now = in_season(date.today())

badge_slot.markdown(
    '<span class="badge badge-live">🟢 LIVE — real AIS ship data</span>'
    if mode == "live"
    else '<span class="badge badge-demo">🟡 DEMO — simulated data (no live feed connected)</span>',
    unsafe_allow_html=True,
)

if not season_now:
    st.info(
        "🗓️ **Off-season right now.** The official speed rule runs **1 Aug – 30 Nov**. "
        "Outside it, ships over 10 kn are shown as **over the limit** (for monitoring), "
        "not as formal *violations* — those only count during the season."
    )

st.markdown(
    '<p class="stakes">🚢 Ship strikes are a leading cause of death for large whales. '
    'Worldwide, fewer than <b>7%</b> of the most dangerous zones have any protection. '
    'In the Gulf of Panama, ships keep to the route — but studies found only '
    '<b>~10–19%</b> actually respect the speed limit.</p>',
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# REAL DATA — Global Fishing Watch (satellite AIS), last humpback season
# --------------------------------------------------------------------------- #
gfw_data = load_gfw()
if gfw_data and gfw_data.get("total_hours"):
    y0 = gfw_data["date_range"][0][:4]
    over_pct = gfw_data["over_pct"]
    comp_pct = gfw_data["compliant_pct"]
    st.markdown(
        f'<div class="hero" style="background:linear-gradient(135deg,#0a2e2a 0%,#0d4f43 60%,#16857a 100%);">'
        f'<h1 style="font-size:1.5rem;">🛰️ Real data — humpback season {y0}</h1>'
        f'<p>From <b>satellite AIS</b> (Global Fishing Watch), not a simulation. Of all the time '
        f'cargo, tanker &amp; carrier ships spent in the whale corridor during the {y0} season '
        f'(1 Aug – 30 Nov), <b>{over_pct:.0f}% was spent speeding over 10 knots</b>.</p>'
        f'<span class="badge badge-live">🛰️ REAL — satellite AIS · season {y0}</span></div>',
        unsafe_allow_html=True,
    )
    rc1, rc2, rc3 = st.columns(3)
    rc1.metric("Time over the limit", f"{over_pct:.0f}%", help="Share of commercial-vessel presence-hours above 10 kn.")
    rc2.metric("Time whale-safe", f"{comp_pct:.0f}%")
    rc3.metric("Vessel-hours measured", f"{gfw_data['total_hours']:,.0f}")

    rg1, rg2 = st.columns(2)
    with rg1:
        st.markdown("**Real speed distribution (vessel-hours)**")
        dist = gfw_data["distribution"]
        ddf = pd.DataFrame(
            {"speed": list(dist.keys()), "hours": list(dist.values())}
        )
        ddf["over_limit"] = ddf["speed"].isin(gfw.OVER_LIMIT_BUCKETS)
        chart = (
            alt.Chart(ddf).mark_bar().encode(
                x=alt.X("speed:N", sort=gfw.SPEED_BUCKETS, title="Speed (knots)"),
                y=alt.Y("hours:Q", title="Vessel-hours"),
                color=alt.Color("over_limit:N",
                                scale=alt.Scale(domain=[False, True], range=["#18a558", "#d62828"]),
                                legend=None),
                tooltip=["speed", "hours"],
            ).properties(height=280)
        )
        st.altair_chart(chart, use_container_width=True)
    with rg2:
        st.markdown("**Which flags speed the most? (real)**")
        fdf = pd.DataFrame(gfw_data["by_flag"][:10])
        if len(fdf):
            fdf["Flag"] = fdf["flag"].map(analytics.iso3_to_flag)
            fdf = fdf.rename(columns={"over_hours": "Hours over limit", "over_pct": "% of its time over"})
            st.dataframe(
                fdf[["Flag", "Hours over limit", "% of its time over"]],
                hide_index=True, use_container_width=True, height=280,
                column_config={
                    "% of its time over": st.column_config.ProgressColumn(
                        "% of its time over", min_value=0, max_value=100, format="%.0f%%"),
                },
            )
    st.caption(
        "📐 Honest caveat: this counts **presence-hours**, so slow/anchored ships near the canal "
        "approach pull compliance up — it reads more optimistically than per-transit studies "
        "(Guzman et al.: only ~10–19% of ships kept ≤10 kn the whole way). Source: Global Fishing "
        "Watch AIS vessel presence (satellite), commercial vessels, corridor polygon north of 8°N."
    )
    st.divider()
    st.subheader("🧪 Illustrative live/demo view")
    st.caption(
        "The boards below show the *mechanism* with named vessels. Live AIS (aisstream.io) has no "
        "offshore coverage of this corridor, so this view is a **labelled simulation** unless a live "
        "feed reaches the area. The real numbers are the satellite figures above."
    )

# --------------------------------------------------------------------------- #
# Headline cards
# --------------------------------------------------------------------------- #
comp = ov["compliant_pct"]
comp_disp = f"{comp:.0f}%" if comp is not None else "—"
st.markdown(
    f"""
    <div class="cards">
      <div class="card blue"><div class="v">{ov['vessels_in_zone']}</div>
        <div class="l">Ships in the whale lanes</div></div>
      <div class="card red"><div class="v">{ov['vessels_over_limit']}</div>
        <div class="l">Speeding over 10 knots 🔴</div></div>
      <div class="card green"><div class="v">{ov['vessels_in_zone'] - ov['vessels_over_limit']}</div>
        <div class="l">Going whale-safe (≤10 kn) 🟢</div></div>
      <div class="card green"><div class="v">{comp_disp}</div>
        <div class="l">Respect the speed limit</div></div>
    </div>
    """,
    unsafe_allow_html=True,
)
if comp is not None:
    st.progress(min(int(comp), 100), text=f"Compliance: {comp_disp} of ships in the lanes kept to ≤10 knots")

st.divider()

# --------------------------------------------------------------------------- #
# Boards: top speeders + whale-friendly
# --------------------------------------------------------------------------- #
col_bad, col_good = st.columns(2)

with col_bad:
    st.subheader("🔴 Top speeders")
    st.caption("Ships clocked fastest over the 10-knot whale limit, inside the lanes.")
    if len(board):
        b = board.head(12).copy()
        b["Flag"] = b["mmsi"].map(flag_label)
        b = b.rename(columns={
            "name": "Vessel", "max_sog_in_zone": "Top speed (kn)",
            "over_limit_pings": "Times over limit",
        })
        st.dataframe(
            b[["Flag", "Vessel", "Top speed (kn)", "Times over limit"]],
            hide_index=True, use_container_width=True, height=460,
            column_config={
                "Top speed (kn)": st.column_config.ProgressColumn(
                    "Top speed (kn)", min_value=0, max_value=20, format="%.1f kn"),
                "Times over limit": st.column_config.NumberColumn("Times over limit"),
            },
        )
    else:
        st.write("No speeding vessels recorded yet.")

with col_good:
    st.subheader("🟢 Whale-friendly captains")
    st.caption("Ships that stayed at or below 10 knots the whole way through.")
    if len(best):
        g = best.head(12).copy()
        g["Flag"] = g["mmsi"].map(flag_label)
        g = g.rename(columns={
            "name": "Vessel", "max_sog_in_zone": "Top speed (kn)", "zone_pings": "Pings in lane",
        })
        st.dataframe(
            g[["Flag", "Vessel", "Top speed (kn)", "Pings in lane"]],
            hide_index=True, use_container_width=True, height=460,
            column_config={
                "Top speed (kn)": st.column_config.ProgressColumn(
                    "Top speed (kn)", min_value=0, max_value=20, format="%.1f kn"),
            },
        )
    else:
        st.write("No fully-compliant vessels recorded yet.")

st.divider()

# --------------------------------------------------------------------------- #
# Map
# --------------------------------------------------------------------------- #
st.subheader("🗺️ Where are the ships?")


def _zone_layer():
    ring = [[lon, lat] for (lat, lon) in config.SPEED_ZONE_POLYGON]
    ring.append(ring[0])
    return pdk.Layer(
        "PolygonLayer", data=[{"polygon": ring}], get_polygon="polygon",
        get_fill_color=[20, 120, 200, 35], get_line_color=[20, 120, 200, 180],
        line_width_min_pixels=2, pickable=False,
    )


def _vessel_layer(df: pd.DataFrame):
    def color(r):
        if not r["in_zone"]:
            return [150, 150, 150, 110]
        if r["over_limit"]:
            return [214, 40, 40, 220]
        return [20, 150, 80, 220]

    df = df.copy()
    df["color"] = df.apply(color, axis=1)
    df["sog_disp"] = df["sog"].round(1)
    return pdk.Layer(
        "ScatterplotLayer", data=df, get_position="[lon, lat]",
        get_fill_color="color", get_radius=250, radius_min_pixels=3,
        radius_max_pixels=11, pickable=True,
    )


if len(pts):
    lats = [lat for (lat, _l) in config.SPEED_ZONE_POLYGON]
    lons = [lon for (_la, lon) in config.SPEED_ZONE_POLYGON]
    deck = pdk.Deck(
        map_style=None,
        initial_view_state=pdk.ViewState(
            latitude=sum(lats) / len(lats), longitude=sum(lons) / len(lons),
            zoom=9, pitch=0,
        ),
        layers=[_zone_layer(), _vessel_layer(pts)],
        tooltip={"html": "<b>{name}</b><br/>{sog_disp} kn",
                 "style": {"backgroundColor": "#0b2a3a", "color": "white"}},
    )
    st.pydeck_chart(deck, use_container_width=True)
    st.markdown(
        '<p class="legend">🔴 over 10 kn in the lanes · 🟢 whale-safe in the lanes · '
        '⚪ outside the protected lanes. Blue outline = the official IMO speed zone '
        '(both traffic lanes, north of 8°N).</p>',
        unsafe_allow_html=True,
    )

st.divider()

# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #
st.subheader("📊 The numbers")
sc1, sc2 = st.columns(2)

with sc1:
    st.markdown("**How fast are ships going?**")
    if len(hist) and hist["count"].sum() > 0:
        chart = (
            alt.Chart(hist)
            .mark_bar()
            .encode(
                x=alt.X("speed_bin:N", sort=list(hist["speed_bin"]), title="Speed (knots)"),
                y=alt.Y("count:Q", title="Ship positions"),
                color=alt.Color(
                    "over_limit:N",
                    scale=alt.Scale(domain=[False, True], range=["#18a558", "#d62828"]),
                    legend=None,
                ),
                tooltip=["speed_bin", "count"],
            )
            .properties(height=300)
        )
        st.altair_chart(chart, use_container_width=True)
        st.caption("Green = whale-safe (≤10 kn) · Red = over the limit. The cluster above 10 kn is the problem.")
    else:
        st.write("Not enough data yet.")

with sc2:
    st.markdown("**Which flags speed the most?**")
    if len(flags):
        f = flags.head(10).rename(columns={
            "flag": "Flag", "vessels": "Ships in zone",
            "over_limit": "Speeding", "compliant_pct": "Compliance",
        })
        st.dataframe(
            f[["Flag", "Ships in zone", "Speeding", "Compliance"]],
            hide_index=True, use_container_width=True, height=300,
            column_config={
                "Compliance": st.column_config.ProgressColumn(
                    "Compliance", min_value=0, max_value=100, format="%.0f%%"),
            },
        )
        st.caption("Flag = the country a ship is registered under (from its MMSI). Not the owner's nationality.")
    else:
        st.write("Not enough data yet.")

# --------------------------------------------------------------------------- #
# Methodology & footer
# --------------------------------------------------------------------------- #
with st.expander("ℹ️ How this works & honest caveats"):
    st.markdown(
        """
**The rule.** The IMO recommends ships keep to **≤ 10 knots** in the Gulf of Panama
**traffic lanes**, **north of 8°N**, from **1 Aug – 30 Nov** (humpback season). Below
10 kn, a strike rarely kills a whale; cargo ships normally run 15–17 kn.

**The zone.** The blue outline follows the **exact official IMO traffic-lane boundaries**
(all 12 scheme vertices, clipped at 8°N) — not a rough box. The official rule targets the
lanes; real whale risk extends a bit beyond them, so this is a conservative, defensible view.

**The speed.** Ships broadcast their speed (SOG) over AIS — we read it directly, we don't
guess. But AIS can be stale or spoofed: a single ping is weak evidence; sustained
over-limit transit is strong.

**`Over limit` ≠ `violation`.** Over-limit is the physical fact (shown year-round, for
monitoring). A formal *violation* is over-limit **and** during the 1 Aug–30 Nov season.

**Why a dashboard?** Compliance is largely voluntary, so transparency is the lever:
transparency → pressure → compliance → fewer strikes. Success = a real conservation
actor using this, not GitHub stars.

*Data here may be **simulated** when no live AIS feed is connected (see the badge at the top).*

Sources: IMO MSC.93 / res. A.858(20); Guzman et al. 2012, 2020 (*Marine Policy*);
Smithsonian Tropical Research Institute (STRI); ship data via aisstream.io.
        """
    )

st.markdown(
    '<p class="foot">Open project · data: <a href="https://aisstream.io">aisstream.io</a> · '
    'rule: IMO / STRI · Built to protect whales from ships. '
    'Not an official navigation source.</p>',
    unsafe_allow_html=True,
)
