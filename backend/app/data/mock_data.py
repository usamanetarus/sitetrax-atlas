"""Mock SiteTrax.io asset data matching the real JSON schema."""

import random
import datetime
from urllib.parse import quote

# Status codes from SiteTrax.io docs:
# A0 = clean, A1 = interpolated check digit, I1-I7 = various detection issues
STATUS_CODES = ["A0", "A0", "A0", "A1", "I1", "I2", "I3"]

CONTAINER_IDS = [
    "TRBU5341840", "MSCU7823411", "CMAU9123456", "OOLU4567890",
    "TTNU1234567", "CSLU8901234", "HLCU5678901", "ONEU2345678",
]

LOCATIONS = ["Norfolk Yard", "Charleston Terminal", "Savannah Gate 3", "Wilmington Depot"]

CONTAINER_COMPANIES = ["TRITON", "MSC", "CMA-CGM", "OOL", "TRITON", "CSL", "HLC", "ONE"]

CONTAINER_COUNTRIES = ["US", "CN", "DE", "SG", "US", "PA", "DE", "JP"]


def _mock_image_url(container_id: str, location: str, asset_id: int) -> str:
    """Deterministic inline image for local/mock runs."""
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">
      <defs>
        <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="#1c1917" />
          <stop offset="100%" stop-color="#292524" />
        </linearGradient>
      </defs>
      <rect width="960" height="540" rx="28" fill="url(#g)" />
      <rect x="56" y="56" width="848" height="428" rx="22" fill="#111111" stroke="#44403c" stroke-width="2" />
      <text x="90" y="142" fill="#f5f5f4" font-family="Inter, Arial, sans-serif" font-size="44" font-weight="700">{container_id}</text>
      <text x="90" y="200" fill="#d6d3d1" font-family="Inter, Arial, sans-serif" font-size="28">{location}</text>
      <text x="90" y="262" fill="#a8a29e" font-family="Inter, Arial, sans-serif" font-size="22">Mock asset image</text>
      <text x="90" y="310" fill="#78716c" font-family="Inter, Arial, sans-serif" font-size="18">Asset ID {asset_id}</text>
    </svg>
    """.strip()
    return f"data:image/svg+xml;charset=utf-8,{quote(svg)}"


def generate_asset_records(count: int = 20) -> list[dict]:
    """Generate mock asset records matching SiteTrax.io JSON schema."""
    records = []
    base_time = datetime.datetime.now(datetime.timezone.utc)

    for i in range(count):
        offset = datetime.timedelta(hours=random.randint(-72, 0), minutes=random.randint(0, 59))
        ts = base_time + offset

        idx = i % len(CONTAINER_IDS)
        asset_id = random.randint(100000, 999999)
        location = LOCATIONS[idx % len(LOCATIONS)]
        records.append({
            "id": asset_id,
            "video_name": f"gate_cam_{random.randint(1,5)}_{ts.strftime('%Y%m%d_%H%M%S')}.mp4",
            "type": "container",
            "text": CONTAINER_IDS[idx],
            "datetime": ts.isoformat(),
            "datetime_original": ts.isoformat(),
            "datetime_digitized": (ts + datetime.timedelta(seconds=random.randint(1, 30))).isoformat(),
            "gps_lat": round(30.40 + random.uniform(-0.05, 0.05), 6),
            "gps_lon": round(-81.55 + random.uniform(-0.05, 0.05), 6),
            "container_company": CONTAINER_COMPANIES[idx],
            "container_country": CONTAINER_COUNTRIES[idx],
            "status": random.choice(STATUS_CODES),
            "status_code": random.choice(STATUS_CODES),
            "camera": f"gate_cam_{random.randint(1,5)}",
            "location": location,
            "stacking": random.choice(["top", "bottom", "single"]),
            "sorting": random.choice(["inbound", "outbound", "storage"]),
            "asset_image": _mock_image_url(CONTAINER_IDS[idx], location, asset_id),
            "thumbnail_url": _mock_image_url(CONTAINER_IDS[idx], location, asset_id),
        })

    return records


# Pre-generated dataset for demo consistency
ASSETS = generate_asset_records(30)


def query_assets(
    container_id: str | None = None,
    location: str | None = None,
    camera: str | None = None,
    status_code: str | None = None,
    hours_back: int | None = 24,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Query mock assets with optional filters."""
    cutoff = None if hours_back is None else datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_back)
    start_dt = datetime.datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
    end_dt = datetime.datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None

    results = []
    for asset in ASSETS:
        dt = datetime.datetime.fromisoformat(asset["datetime"])
        if date_from and dt < start_dt:
            continue
        if date_to and dt > end_dt:
            continue
        if cutoff is not None and hours_back and hours_back > 0 and dt < cutoff:
            continue
        if container_id and container_id.upper() not in asset["text"].upper():
            continue
        if location and location.lower() not in asset.get("location", "").lower():
            continue
        if camera and camera.lower() not in asset.get("camera", "").lower():
            continue
        if status_code and status_code.upper() != asset.get("status_code", "").upper():
            continue
        results.append(asset)

    return results


def get_latest_scan(container_id: str) -> dict | None:
    """Get the most recent scan for a specific container ID."""
    matching = [
        a for a in ASSETS
        if container_id.upper() in a["text"].upper()
    ]
    if not matching:
        return None
    return max(matching, key=lambda a: a["datetime"])


def get_asset_timeline(container_id: str) -> list[dict]:
    """All scans of a container ID (full detection history), newest first."""
    matching = [a for a in ASSETS if container_id.upper() in a["text"].upper()]
    return sorted(matching, key=lambda a: a["datetime"], reverse=True)


def find_asset_by_id(asset_id: int) -> dict | None:
    """Find a specific asset record by internal ID."""
    for asset in ASSETS:
        if asset["id"] == asset_id:
            return asset
    return None
