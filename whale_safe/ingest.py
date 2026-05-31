"""Live AIS ingestion from aisstream.io into the local SQLite store.

Connect to wss://stream.aisstream.io/v0/stream, subscribe to a bounding box
around the Gulf of Panama, and persist PositionReport messages with derived
risk flags.

Requires a free API key from https://aisstream.io (sign in with GitHub).
Set it in the environment as AISSTREAM_API_KEY (or in a .env file).

Run:
    python -m whale_safe.ingest
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
from datetime import datetime, timezone

try:
    import websockets
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "The 'websockets' package is required. Install deps: pip install -r requirements.txt"
    ) from e

from . import config, store


def _load_api_key() -> str:
    # Lazy .env support without hard dependency on python-dotenv.
    key = os.environ.get("AISSTREAM_API_KEY")
    if not key:
        try:
            from dotenv import load_dotenv

            load_dotenv()
            key = os.environ.get("AISSTREAM_API_KEY")
        except ImportError:
            pass
    if not key:
        raise SystemExit(
            "AISSTREAM_API_KEY not set.\n"
            "Get a free key at https://aisstream.io and either:\n"
            "  export AISSTREAM_API_KEY=...   or put it in a .env file.\n"
            "No key yet? Run the simulator instead: python -m whale_safe.simulate"
        )
    return key


def _subscription(api_key: str) -> dict:
    s, w, n, e = config.SUBSCRIPTION_BBOX
    # BoundingBoxes: list of boxes, each box = [[lat_sw, lon_sw], [lat_ne, lon_ne]].
    return {
        "APIKey": api_key,
        "BoundingBoxes": [[[s, w], [n, e]]],
        "FilterMessageTypes": ["PositionReport"],
    }


def _parse_position(msg: dict):
    """Extract (mmsi, name, lat, lon, sog, cog, ts) from an aisstream message."""
    report = msg.get("Message", {}).get("PositionReport", {})
    meta = msg.get("MetaData", {})
    mmsi = meta.get("MMSI") or report.get("UserID")
    if mmsi is None:
        return None
    lat = report.get("Latitude")
    lon = report.get("Longitude")
    if lat is None or lon is None:
        return None
    sog = report.get("Sog")
    cog = report.get("Cog")
    # aisstream uses 1023.0 / similar sentinels for "not available".
    if sog is not None and sog >= 102.3:
        sog = None
    if cog is not None and cog >= 360.0:
        cog = None
    name = (meta.get("ShipName") or "").strip() or None
    ts_raw = meta.get("time_utc")
    ts = _parse_ts(ts_raw)
    return str(mmsi), name, lat, lon, sog, cog, ts


def _parse_ts(ts_raw) -> datetime:
    if not ts_raw:
        return datetime.now(timezone.utc)
    # aisstream time_utc looks like "2024-01-01 12:00:00.000000000 +0000 UTC".
    cleaned = str(ts_raw).split(".")[0].replace("UTC", "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return datetime.now(timezone.utc)


async def run(db_path: str = config.DB_PATH) -> None:
    api_key = _load_api_key()
    store.init_db(db_path)
    sub = _subscription(api_key)

    stop = asyncio.Event()

    def _request_stop(*_):
        stop.set()

    try:
        signal.signal(signal.SIGINT, _request_stop)
        signal.signal(signal.SIGTERM, _request_stop)
    except (ValueError, OSError):
        pass  # not in main thread

    count = 0
    zone_count = 0
    print(f"Connecting to {config.AISSTREAM_URL} ...")
    print(f"Bounding box (S,W,N,E): {config.SUBSCRIPTION_BBOX}")

    while not stop.is_set():
        try:
            async with websockets.connect(config.AISSTREAM_URL, ping_interval=20) as ws:
                await ws.send(json.dumps(sub))
                print("Subscribed. Streaming PositionReports... (Ctrl-C to stop)")
                with store.connect(db_path) as conn:
                    async for raw in ws:
                        if stop.is_set():
                            break
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if msg.get("MessageType") != "PositionReport":
                            # aisstream sends an error object if the sub is bad.
                            if "error" in str(msg).lower():
                                print("Server message:", msg)
                            continue
                        parsed = _parse_position(msg)
                        if not parsed:
                            continue
                        mmsi, name, lat, lon, sog, cog, ts = parsed
                        store.insert_position(
                            conn, mmsi=mmsi, name=name, lat=lat, lon=lon,
                            sog=sog, cog=cog, ts=ts,
                        )
                        count += 1
                        from .geo import in_zone as _iz
                        if _iz(lat, lon):
                            zone_count += 1
                        if count % 50 == 0:
                            conn.commit()
                            print(f"  stored {count} positions ({zone_count} inside zone)")
        except Exception as exc:  # noqa: BLE001 - reconnect on any transport error
            if stop.is_set():
                break
            print(f"Connection error: {exc!r} — reconnecting in 5s")
            await asyncio.sleep(5)

    print(f"Stopped. Total stored: {count} ({zone_count} inside zone).")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
