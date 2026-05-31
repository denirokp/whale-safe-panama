# 🐋 Whale Safe Panama

> Open transparency layer for ship-strike risk in the **Gulf of Panama**.
> Which vessels exceed the **10-knot** seasonal whale-protection speed limit — and which respect it?

Software-only. No hardware. The leverage of a solo builder is **data + transparency + pressure**, not buoys.
Value mechanism is indirect: **transparency → pressure → compliance → fewer whale strikes**.

## Why Panama

Less than 7% of the world's most dangerous ship-strike zones have any protection. Panama is an
unusually clean first case: the route exists and is mostly followed (86–90%), but **only ~10–19% of
ships keep to the 10-knot limit** (Guzman et al. 2020). The behaviour gap is in *speed* — exactly what
a transparency dashboard can pressure. AIS data is free.

The IMO seasonal speed recommendation: **≤ 10 knots SOG, 1 Aug – 30 Nov, north of latitude 8°00′N**,
both lanes of the Gulf of Panama Traffic Separation Scheme (effective 2014).

## Quick start (no API key needed)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) Generate a realistic demo snapshot (simulated AIS, in-season timestamps)
python -m whale_safe.simulate --reset

# 2) Launch the dashboard
streamlit run dashboard/app.py
```

## Live data (free aisstream.io key)

The dashboard pulls a **live AIS snapshot** itself when a key is present — no separate
ingester needed. Get a free key at [aisstream.io](https://aisstream.io) (sign in with GitHub):

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # paste your key
streamlit run dashboard/app.py                                # shows 🟢 LIVE
```

For long-running background collection into `whale_safe.db` (e.g. on a server), the
standalone ingester is still available:

```bash
export AISSTREAM_API_KEY=...
python -m whale_safe.ingest
```

> Today's date may be **outside** the Aug–Nov season — the dashboard handles this honestly:
> off-season, over-limit positions are labelled *over limit* (for monitoring), not *violation*.

## Publish (Streamlit Community Cloud — free)

1. Push this repo to **public GitHub** (`*.db` and `secrets.toml` are git-ignored).
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app** → pick the repo →
   branch `main` → main file `dashboard/app.py`.
3. **Settings → Secrets** → paste `AISSTREAM_API_KEY = "..."`.
4. **Deploy** → you get a public URL. Without the key it shows the labelled **DEMO**.

> Note: Streamlit Cloud has an ephemeral filesystem and no always-on worker, so the live
> feed is a periodic in-app snapshot (cached ~3 min), accumulating history only while the
> app stays warm. For persistent history, run `whale_safe.ingest` on a small server into a
> shared DB (see *out of scope* in the plan).

## Layout

| Path | Role |
|---|---|
| `whale_safe/config.py` | Zone polygon, season, speed limit, AIS source — with sources |
| `whale_safe/geo.py` | Geofence + season logic (`over_limit` vs `violation`) |
| `whale_safe/store.py` | SQLite store + derived risk flags |
| `whale_safe/ingest.py` | Standalone aisstream.io WebSocket client (background collection) |
| `whale_safe/live.py` | In-app live AIS snapshot (for Streamlit Cloud) |
| `whale_safe/simulate.py` | Synthetic AIS so the pipeline runs today |
| `whale_safe/analytics.py` | Aggregations: leaderboard, best performers, speed histogram, by-flag |
| `dashboard/app.py` | Public Streamlit dashboard + map |
| `.streamlit/config.toml` | Ocean theme (committed for deploy) |

## Honesty principles (baked into the UI)

- **Approximate geofence** — a false zone is a false accusation. Exact IMO TSS vertices kept for reference.
- **`over limit` ≠ `violation`** — physical fact vs breach of the official seasonal rule.
- **AIS can be spoofed/stale** — single pings are weak; sustained over-limit transit is strong.
- **Success metric = a real conservation actor uses this**, not GitHub stars. *Validate demand with an NGO
  (STRI, MarViva) before scaling.*

## Status

`v0.2`: precise IMO TSS geofence (all 12 official vertices, north of 8°N) + in-app live
AIS snapshot + public friendly dashboard (top speeders, whale-friendly captains, stats,
map) — deploy-ready for Streamlit Community Cloud.
Next: deploy publicly; validate demand with STRI / MarViva before scaling.

---

Sources: IMO MSC.93 / res. A.858(20); Guzman et al. 2012, 2020 (*Marine Policy*);
[Smithsonian Tropical Research Institute](https://stri.si.edu/story/compliance); [aisstream.io](https://aisstream.io/documentation).
