"""Time-boxed live AIS snapshot — designed for Streamlit Community Cloud.

Streamlit Cloud runs only the app process (no always-on worker) on an ephemeral
filesystem, so we cannot run the persistent `ingest.py` loop there. Instead, on
load we open a short-lived WebSocket to aisstream.io, collect position reports for
the Gulf of Panama bounding box for a few seconds, and return them. The dashboard
caches this with a TTL and appends to SQLite so history accumulates while the
container stays warm.

Reuses the parsing/subscription helpers from ingest.py (single source of truth).
"""

from __future__ import annotations

import asyncio
import json
import os

from . import config
from .ingest import _parse_position, _subscription


def get_api_key() -> str | None:
    """Resolve the aisstream.io key: Streamlit secrets -> env -> .env -> None."""
    # st.secrets (only present when running under Streamlit with secrets set).
    try:
        import streamlit as st

        if "AISSTREAM_API_KEY" in st.secrets:
            key = str(st.secrets["AISSTREAM_API_KEY"]).strip()
            if key:
                return key
    except Exception:
        pass
    key = os.environ.get("AISSTREAM_API_KEY")
    if not key:
        try:
            from dotenv import load_dotenv

            load_dotenv()
            key = os.environ.get("AISSTREAM_API_KEY")
        except ImportError:
            pass
    return key.strip() if key else None


async def _pull(api_key: str, total_seconds: float, max_msgs: int) -> list[dict]:
    import websockets

    sub = _subscription(api_key)
    positions: list[dict] = []
    loop = asyncio.get_event_loop()
    deadline = loop.time() + total_seconds
    try:
        async with websockets.connect(config.AISSTREAM_URL, ping_interval=20) as ws:
            await ws.send(json.dumps(sub))
            while len(positions) < max_msgs:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break  # hard wall-clock cap reached
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("MessageType") != "PositionReport":
                    continue
                parsed = _parse_position(msg)
                if not parsed:
                    continue
                mmsi, name, lat, lon, sog, cog, ts = parsed
                positions.append(
                    {"mmsi": mmsi, "name": name, "lat": lat, "lon": lon,
                     "sog": sog, "cog": cog, "ts": ts}
                )
    except Exception:
        # Transport hiccup — return whatever we gathered; caller falls back if empty.
        return positions
    return positions


def fetch_live_snapshot(total_seconds: float = 12.0, max_msgs: int = 300) -> list[dict] | None:
    """Collect a short window of live AIS positions for the gulf.

    Bounded by a hard wall-clock cap (default 12s) so the first page load stays
    snappy on Streamlit Cloud / Codespaces. Returns a list of position dicts, or
    None if no API key is configured. An empty list means a key exists but no
    messages arrived in the window.
    """
    api_key = get_api_key()
    if not api_key:
        return None
    return asyncio.run(_pull(api_key, total_seconds=total_seconds, max_msgs=max_msgs))
