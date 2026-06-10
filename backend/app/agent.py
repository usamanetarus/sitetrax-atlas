"""Builder Agent — the core ADK agent that parses logistics intent into monitoring rules.

Uses ADK 2.x API with the session service configured by `app.main`.
"""

import json
import os
import datetime
import re
import logging
import csv
import io
from collections import Counter
from zoneinfo import ZoneInfo

import sys
from pathlib import Path

from google.adk import Agent
from google.adk.tools import FunctionTool
from google.adk.tools import load_memory
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

from app.monitoring.templates import TEMPLATES, TEMPLATE_DESCRIPTIONS_FOR_PROMPT, TemplateName
from app.monitoring import store
from app.data import query_assets, get_latest_scan, get_asset_timeline
from app.data.sitetrax_client import (
    get_facility_last_scan, get_facility_recent, list_projects,
    get_container_video, get_container_videos, get_container_image, get_container_images, search_videos, facility_metrics, project_metrics,
    get_asset_timeline, get_asset_detail, export_assets, get_project_detail, get_project_integrations, get_video_detail,
    get_video_metrics, query_sitetrax, get_timeline_with_videos, facility_overview,
    get_sitetrax_schema, sitetrax_query,
    get_auth_self, get_feedback_choices, get_project_last_video, sitetrax_image_url_to_base64,
    resolve_buckets, SiteTraxAuthError, SiteTraxNotFoundError, SiteTraxAPIError, UnknownFacilityError,
    resolve_date_range, resolve_date,
)
from app.knowledge import search_reference

logger = logging.getLogger("sitetrax")




def _iso_z(dt: datetime.datetime) -> str:
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Date-preset resolution (today, this_month, june, last_30d, …) lives in
# app.data.sitetrax_client — the single source of truth shared with the MCP
# servers, so every entry point resolves keywords identically. These private
# aliases keep the decorator below readable.
_resolve_date_range = resolve_date_range
_resolve_date = resolve_date


def _resolve_tool_dates(fn):
    """Decorator that expands date presets in date_from/date_to kwargs.

    A closed-period keyword in date_from (e.g. "yesterday", "last_month", "june")
    fills BOTH bounds, unless the caller already supplied an explicit date_to.
    """
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if kwargs.get("date_from"):
            start, end = _resolve_date_range(kwargs["date_from"])
            kwargs["date_from"] = start
            if end and not kwargs.get("date_to"):
                kwargs["date_to"] = end
        if kwargs.get("date_to"):
            start, end = _resolve_date_range(kwargs["date_to"])
            kwargs["date_to"] = end or start  # date_to uses the period's closing bound
        return fn(*args, **kwargs)

    return wrapper


def _tool_guard(fn):
    """Decorator that catches data-layer exceptions and returns user-friendly messages.

    Catches:
      - SiteTraxAuthError   → authentication guidance
      - SiteTraxNotFoundError → "not found" message
      - UnknownFacilityError  → facility suggestion with known names
      - SiteTraxAPIError    → generic API error
      - Other exceptions    → unexpected error fallback
    """
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SiteTraxAuthError:
            return _sitetrax_auth_message()
        except SiteTraxNotFoundError as exc:
            return f"No data found for that request. {exc}"
        except UnknownFacilityError as exc:
            known = exc.known_names or []
            suggestions = ", ".join(known[:8]) if known else "none available"
            return (
                f"I don't recognize facility '{exc.facility}'. "
                f"Available: {suggestions}. "
                "Please use the exact project name or a shorter unique prefix."
            )
        except SiteTraxAPIError as exc:
            logger.exception("SiteTrax API error in %s", fn.__name__)
            return "SiteTrax is temporarily unavailable - try again shortly."
        except Exception as exc:
            logger.exception("Unexpected error in %s", fn.__name__)
            return f"An unexpected error occurred while processing your request: {exc}"

    return wrapper


_ASSET_COLUMNS = [
    {"key": "text", "label": "Container"},
    {"key": "container_id", "label": "Container"},
    {"key": "facility", "label": "Facility"},
    {"key": "location", "label": "Location"},
    {"key": "status_code", "label": "Status"},
    {"key": "heading", "label": "Heading"},
    {"key": "created_at", "label": "Detected at"},
    {"key": "datetime", "label": "Detected at"},
    {"key": "asset_id", "label": "Asset ID"},
    {"key": "id", "label": "ID"},
]


def _columns_for_rows(rows, preferred=None):
    """Build compact GenericVisualization columns from the rows we actually have."""
    if not rows:
        return []
    preferred = preferred or _ASSET_COLUMNS
    seen = set()
    columns = []
    sample_keys = []
    for row in rows[:10]:
        if isinstance(row, dict):
            sample_keys.extend(row.keys())
    for column in preferred:
        key = column["key"]
        if key in sample_keys and key not in seen:
            columns.append(column)
            seen.add(key)
    for key in sample_keys:
        if key in seen or key == "raw_payload":
            continue
        value = next((row.get(key) for row in rows[:10] if isinstance(row, dict) and key in row), None)
        if isinstance(value, (dict, list)):
            continue
        columns.append({"key": key, "label": key.replace("_", " ").title()})
        seen.add(key)
        if len(columns) >= 10:
            break
    return columns


def _asset_visualization_envelope(
    *,
    title,
    dataset_name,
    rows,
    answer,
    visualizations,
    entity_type="asset",
    provenance=None,
    **extra,
):
    return {
        "title": title,
        "answer": answer,
        "datasets": [{
            "name": dataset_name,
            "label": title,
            "entity_type": entity_type,
            "columns": _columns_for_rows(rows),
            "rows": rows,
            "count": len(rows),
        }],
        "visualizations": visualizations,
        "provenance": {
            "resource": dataset_name,
            "returned": len(rows),
            **(provenance or {}),
        },
        **extra,
    }


# ── Agent tools ──────────────────────────────────────────────

@_tool_guard
def sitetrax_reference_tool(query: str, limit: int = 3) -> str:
    """Search the internal SiteTrax documentation/product reference. Use for conceptual
    questions about what SiteTrax does, API payload fields, status codes, headings,
    camera/video processing, asset types, and how to interpret detections.

    Do not use this for live asset status. Live operational questions must use the
    SiteTrax data tools.

    Args:
        query: The docs/product/data-model question to look up.
        limit: Maximum reference sections to return.
    """
    return json.dumps({
        "query": query,
        "matches": search_reference(query, limit=limit),
    }, default=str)

@_tool_guard
@_resolve_tool_dates
def query_assets_tool(
    container_id: str | None = None,
    location: str | None = None,
    status_code: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 250,
) -> str:
    """Query SiteTrax.io asset records. Use this to look up container scans, check status codes,
    or find assets by location. Returns matching asset records.

    When the result shows has_more=true, tell the user the real total count and ask if they want
    all records fetched. If the user says yes, call this tool again with limit=0.

    Args:
        container_id: Optional container ID to filter by (e.g. TRBU5341840).
        location: Optional location name to filter by (e.g. "Utah Intermodal Ramp").
        status_code: Optional status code (A0, A1, I1-I7).
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
        limit: Maximum records to fetch (default 250). Pass 0 for no limit.
    """
    from app.data.sitetrax_client import query_assets_with_pagination
    envelope = query_assets_with_pagination(
        container_id=container_id,
        location=location,
        status_code=status_code,
        date_from=date_from,
        date_to=date_to,
        limit=None if limit == 0 else limit,
    )
    assets = envelope["assets"]
    pagination = envelope["pagination"]
    total = pagination.get("total_available")
    has_more = pagination.get("has_more", False)
    if not assets:
        return "No matching asset records found."
    answer = f"Found {len(assets)} matching asset record(s)."
    if total is not None:
        answer = f"Found {total} matching asset record(s). Showing {len(assets)}."
    if has_more:
        answer += " More records are available. Ask the user if they want all records fetched."
    return json.dumps(_asset_visualization_envelope(
        title="Asset records",
        dataset_name="assets",
        rows=assets,
        answer=answer,
        visualizations=[
            {"type": "table", "dataset": "assets", "title": "Asset records"},
            {"type": "image_gallery", "dataset": "assets", "title": "Asset images"},
        ],
        provenance={
            "returned_total": len(assets),
            "total_available": total,
            "has_more": has_more,
            "limit": limit,
        },
    ), default=str)


@_tool_guard
def get_asset_detail_tool(asset_id: int | str) -> str:
    """Get detailed information for a single asset by its ID.
    Use when the user asks "tell me more about asset X" or "details for asset Y".

    Args:
        asset_id: The asset ID (numeric or string).
    """
    detail = get_asset_detail(asset_id)
    if not detail:
        return f"No asset found with ID {asset_id}."
    return json.dumps(detail, default=str)


@_tool_guard
def get_project_detail_tool(project_id: int | str) -> str:
    """Get detailed information for a project/yard by its ID.
    Use when the user asks "tell me about project X" or "details for yard Y".

    Args:
        project_id: The project ID.
    """
    detail = get_project_detail(project_id)
    if not detail:
        return f"No project found with ID {project_id}."
    return json.dumps(detail, default=str)


@_tool_guard
def get_project_integrations_tool(project_id: int | str) -> str:
    """Get integrations and data tools for a project (sheets, REST hooks, chain.io).
    Use when the user asks "what integrations does X have?" or "how is Utah Intermodal Ramp connected?".

    Args:
        project_id: The project ID.
    """
    data = get_project_integrations(project_id)
    if not data:
        return f"No integration data found for project {project_id}."
    return json.dumps(data, default=str)


@_tool_guard
def get_video_detail_tool(video_id: int | str) -> str:
    """Get detailed information for a single video by its ID.
    Use when the user asks "tell me about video X" or "details for clip Y".

    Args:
        video_id: The video ID.
    """
    detail = get_video_detail(video_id)
    if not detail:
        return f"No video found with ID {video_id}."
    return json.dumps(detail, default=str)

# ── Historical / activity query tools (over the live timeline) ──────────────

def _parse_dt(ts):
    try:
        return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _ago(ts) -> str:
    dt = _parse_dt(ts)
    if not dt:
        return "unknown"
    secs = max(0.0, (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds())
    if secs >= 86400:
        return f"{secs / 86400:.1f} days ago"
    if secs >= 3600:
        return f"{secs / 3600:.1f} hours ago"
    return f"{secs / 60:.0f} minutes ago"


def _date_range_meta(date_from: str | None = None, date_to: str | None = None) -> dict:
    return {
        "date_from": date_from,
        "date_to": date_to,
        "api_filters": {
            **({"created_at__gte": date_from} if date_from else {}),
            **({"created_at__lte": date_to} if date_to else {}),
        },
    }


def _date_range_label(date_from: str | None = None, date_to: str | None = None) -> str:
    if date_from and date_to:
        return f"from {date_from} to {date_to}"
    if date_from:
        return f"from {date_from}"
    if date_to:
        return f"through {date_to}"
    return "for the requested range"


def _date_in_range(value: str | None, date_from: str | None = None, date_to: str | None = None) -> bool:
    dt = _parse_dt(value)
    if not dt:
        return True
    start = _parse_dt(date_from) if date_from else None
    end = _parse_dt(date_to) if date_to else None
    if start and dt < start:
        return False
    if end and dt > end:
        return False
    return True


def _sitetrax_auth_message() -> str:
    return (
        "SiteTrax API auth is expired. The access token could not be refreshed because "
        "SITETRAX_REFRESH_TOKEN is invalid or expired. Update backend/.env with a fresh "
        "SiteTrax access/refresh token pair, then retry."
    )


@_tool_guard
def container_last_seen_tool(container_id: str) -> str:
    """When and where was a container last detected? Use for "when/where was container X last seen",
    "last location of X". Returns the most recent detection from the live SiteTrax timeline.

    Args:
        container_id: The container ID (e.g. TEMU8826524).
    """
    timeline = get_asset_timeline(container_id)
    if not timeline:
        return f"No detections found for container {container_id}."
    last = timeline[0]
    return json.dumps({
        "container_id": container_id,
        "last_seen_location": last.get("location"),
        "last_seen_time": last.get("datetime"),
        "last_seen_ago": _ago(last.get("datetime")),
        "status_code": last.get("status_code"),
        "heading": last.get("asset_heading") or None,
        "total_detections_on_record": len(timeline),
    }, default=str)


@_tool_guard
def container_facility_activity_tool(container_id: str, facility: str | None = None) -> str:
    """How many times a container has been detected at a facility — each detection is a gate-camera
    pass (an arrival/departure/sighting). Use for "how many times has X departed/been seen at Y",
    "how often does X visit Y". Returns counts per facility, heading breakdown, and first/last seen.

    Args:
        container_id: The container ID.
        facility: Optional facility/yard/project name to scope to (e.g. "Utah Intermodal Ramp"). Omit for all.
    """
    timeline = get_asset_timeline(container_id)
    detections = timeline
    if facility:
        detections = [d for d in timeline if facility.lower() in (d.get("location") or "").lower()]
    if not detections:
        where = f" at {facility}" if facility else ""
        return f"No detections found for container {container_id}{where}."
    by_facility = Counter(d.get("location") for d in detections)
    headings = Counter(d.get("asset_heading") for d in detections
                       if d.get("asset_heading") and d.get("asset_heading") != "-")
    return json.dumps({
        "container_id": container_id,
        "facility": facility or "all facilities",
        "detection_count": len(detections),
        "by_facility": dict(by_facility),
        "first_seen": detections[-1].get("datetime"),
        "last_seen": detections[0].get("datetime"),
        "headings": dict(headings) or None,
        "note": "Each detection is a gate-camera pass; direction (heading) is shown when the site records it.",
    }, default=str)


@_tool_guard
def container_dwell_tool(container_id: str, facility: str | None = None) -> str:
    """Dwell / how-long questions: how long since a container was last seen, and the gap between its
    two most recent detections (a visit-duration estimate). Use for "how long has X been at Y",
    "dwell time of X", "how long since X was seen".

    Args:
        container_id: The container ID.
        facility: Optional facility/yard name to scope to.
    """
    timeline = get_asset_timeline(container_id)
    detections = timeline
    if facility:
        detections = [d for d in timeline if facility.lower() in (d.get("location") or "").lower()]
    if not detections:
        where = f" at {facility}" if facility else ""
        return f"No detections found for container {container_id}{where}."
    last = detections[0]
    out = {
        "container_id": container_id,
        "facility": facility or last.get("location"),
        "last_seen": last.get("datetime"),
        "time_since_last_seen": _ago(last.get("datetime")),
    }
    if len(detections) >= 2:
        prev_dt, last_dt = _parse_dt(detections[1].get("datetime")), _parse_dt(last.get("datetime"))
        if prev_dt and last_dt:
            out["gap_between_two_most_recent_detections_hours"] = round(
                (last_dt - prev_dt).total_seconds() / 3600.0, 1)
    out["note"] = ("Dwell is estimated from gate detections; precise in-yard dwell needs paired "
                   "in/out events, which the camera data does not always distinguish.")
    return json.dumps(out, default=str)


# ── Facility / yard, video & metrics tools (live data) ──────────────────────

@_tool_guard
def facility_last_scan_tool(facility: str) -> str:
    """The most recent container scanned at a facility/yard — EVER, not just recently. Use for
    "what was the last container scanned at a facility", "most recent asset at Utah Intermodal Ramp", "newest detection at <yard>".

    Args:
        facility: Facility/yard/project name (e.g. "Utah Intermodal Ramp").
    """
    asset = get_facility_last_scan(facility)
    if not asset:
        return f"No scans found for facility '{facility}'. (Use list_facilities_tool to see valid names.)"
    return json.dumps({
        "facility": asset.get("location"),
        "last_asset_text": asset.get("text"),
        "asset_type": asset.get("type"),
        "last_container": asset.get("text"),
        "scanned_at": asset.get("datetime"),
        "scanned_ago": _ago(asset.get("datetime")),
        "status_code": asset.get("status_code"),
    }, default=str)


@_tool_guard
@_resolve_tool_dates
def search_images_tool(
    query: str | None = None,
    limit: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
    facility: str | None = None,
) -> str:
    """Search/list image detections. Use for "show me images at Utah Intermodal Ramp", "asset photos from yesterday",
    "pictures for this facility", or "images for container ABC".

    Args:
        query: Optional search text (facility, camera, container).
        limit: Maximum images to return (default 10, max 25).
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
        facility: Optional facility name to filter by.
    """
    clean_query = query.strip() if isinstance(query, str) else None
    looks_like_container = bool(
        clean_query
        and re.fullmatch(r"[A-Z0-9]{7,}", clean_query.upper())
        and any(ch.isdigit() for ch in clean_query)
    )
    try:
        assets = query_assets(
            container_id=clean_query,
            location=facility,
            date_from=date_from,
            date_to=date_to,
        )
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't search images right now."
    images = []
    for asset in assets:
        image_url = asset.get("asset_image") or asset.get("image_url") or asset.get("thumbnail_url") or asset.get("thumbnail")
        asset_id = asset.get("id")
        if not image_url and asset_id is not None:
            detail = get_asset_detail(asset_id) or {}
            image_url = detail.get("asset_image") or detail.get("image_url") or detail.get("thumbnail_url") or detail.get("thumbnail")
        if not image_url:
            continue
        images.append({
            **asset,
            "container_id": asset.get("text"),
            "asset_id": asset_id,
            "image_url": image_url,
            "asset_image": image_url,
            "thumbnail_url": asset.get("thumbnail_url") or asset.get("asset_image_lr") or image_url,
            "detected_at": asset.get("datetime"),
            "facility": asset.get("location"),
            "status_code": asset.get("status_code"),
            "heading": asset.get("asset_heading") or None,
            "asset": asset,
        })
        if len(images) >= max(1, min(limit, 25)):
            break
    if not images and looks_like_container and clean_query:
        try:
            images = get_container_images(clean_query, limit=limit, date_from=date_from, date_to=date_to)
        except Exception:
            images = []
    if not images:
        target = f" matching '{query}'" if query else ""
        return f"No images found{target}."
    return json.dumps({
        "query": query,
        "count": len(images),
        "images": images,
        **_date_range_meta(date_from, date_to),
    }, default=str)


@_resolve_tool_dates
@_tool_guard
def facility_recent_activity_tool(
    facility: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Recent containers detected at a facility within a time window. Use for "what's been at Utah Intermodal Ramp
    today", "containers at <yard> between two timestamps".

    Args:
        facility: Facility/yard/project name.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        assets = get_facility_recent(facility, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return f"The data for '{facility}' is currently slow or unavailable. Please try again."
    if not assets:
        return f"No containers detected at '{facility}' {_date_range_label(date_from, date_to)}."
    return json.dumps({
        "facility": facility,
        **_date_range_meta(date_from, date_to),
        "count": len(assets),
        "containers": [{"text": a.get("text"), "datetime": a.get("datetime"),
                        "status_code": a.get("status_code")} for a in assets[:15]],
    }, default=str)


@_tool_guard
def list_facilities_tool() -> str:
    """List the facilities/yards/projects in the data (with ids). Use for "what facilities/yards are
    there", or to resolve a facility name.
    """
    try:
        projects = list_projects()
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't list the facilities right now."
    if not projects:
        return "No facilities found."
    return json.dumps({"facilities": [{"id": p.get("id"), "name": p.get("name")} for p in projects]}, default=str)


@_resolve_tool_dates
@_tool_guard
def container_video_tool(
    container_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """The most recent video clip for a container. Use for "show me the video/clip of X",
    "is there footage of X". For ALL videos of a container, use get_container_videos_tool.
    Returns a temporary playback URL (expires in ~5 minutes).

    Args:
        container_id: The container ID.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        info = get_container_video(container_id, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return f"Sorry, I couldn't retrieve video for {container_id}."
    if not info:
        return f"No video found for container {container_id}."
    return json.dumps(info, default=str)



@_tool_guard
@_resolve_tool_dates
def get_container_videos_tool(
    container_id: str,
    limit: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """All video clips for a container across its detection timeline.
    Use for "show me all videos of container X", "every video clip of X", "all footage of X".
    Returns a list of video records with playback URLs.

    Args:
        container_id: The container ID.
        limit: Maximum videos to return (default 10).
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        videos = get_container_videos(container_id, limit=limit, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return f"Sorry, I couldn't retrieve videos for {container_id}."
    if not videos:
        return f"No videos found for container {container_id}."
    return json.dumps({
        "container_id": container_id,
        "count": len(videos),
        "videos": videos,
        **_date_range_meta(date_from, date_to),
    }, default=str)

@_resolve_tool_dates
@_tool_guard
def container_image_tool(
    container_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """The most recent image for a container. Use for "show me the image/photo of X",
    "what did the container look like". For ALL images of a container, use get_container_images_tool.
    Returns a direct image URL.

    Args:
        container_id: The container ID.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        info = get_container_image(container_id, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return f"Sorry, I couldn't retrieve an image for {container_id}."
    if not info:
        return f"No image found for container {container_id}."
    return json.dumps(info, default=str)



@_tool_guard
@_resolve_tool_dates
def get_container_images_tool(
    container_id: str,
    limit: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """All images for a container across its detection timeline.
    Use for "show me all images of container X", "every photo of X", "all imagery of X".
    Returns a list of image records.

    Args:
        container_id: The container ID.
        limit: Maximum images to return (default 10).
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        images = get_container_images(container_id, limit=limit, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return f"Sorry, I couldn't retrieve images for {container_id}."
    if not images:
        return f"No images found for container {container_id}."
    return json.dumps({
        "container_id": container_id,
        "count": len(images),
        "images": images,
        **_date_range_meta(date_from, date_to),
    }, default=str)


@_tool_guard
@_resolve_tool_dates
def search_videos_tool(
    query: str | None = None,
    limit: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
    facility: str | None = None,
) -> str:
    """Search or list SiteTrax videos. Use for "find videos from a facility", "latest clips",
    "videos from yesterday", "show me videos from last week", "videos from the last hour".

    Args:
        query: Optional search text (facility, camera, container).
        limit: Maximum videos to return (default 10, max 25).
        date_from: Optional start date (ISO 8601, e.g. 2026-06-01T00:00:00Z).
        date_to: Optional end date (ISO 8601).
        facility: Optional facility name to filter by (e.g. "Utah Intermodal Ramp").
    """
    try:
        videos = search_videos(
            query=query,
            limit=max(1, min(limit, 25)),
            date_from=date_from,
            date_to=date_to,
            facility=facility,
        )
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't search videos right now."
    if not videos:
        target = f" matching '{query}'" if query else ""
        return f"No videos found{target}."
    return json.dumps({
        "query": query,
        "count": len(videos),
        "videos": videos,
        **_date_range_meta(date_from, date_to),
    }, default=str)


@_tool_guard
@_resolve_tool_dates
def facility_metrics_tool(
    facility: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Aggregate container counts over time — for one facility or across all (busiest yard/day,
    daily/total volume). Use for "how many containers at Utah Intermodal Ramp this week", "busiest yard", "daily counts".
    Metrics semantics: `count` means distinct visible containers/day; `trans` means visible transactions/day; *_unfiltered includes hidden assets.

    Args:
        facility: Optional facility/yard name. Omit for an all-facilities comparison.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        rows = facility_metrics(facility=facility, date_from=date_from, date_to=date_to) if facility else project_metrics(date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't retrieve the metrics right now."
    if not rows:
        scope = f" for {facility}" if facility else ""
        return f"No metrics available{scope} {_date_range_label(date_from, date_to)}."
    total = sum((r.get("containers") or r.get("count") or 0) for r in rows)
    return json.dumps({
        "scope": facility or "all facilities",
        **_date_range_meta(date_from, date_to),
        "total_containers": total,
        "by_day": rows[:30],
    }, default=str)


@_resolve_tool_dates
@_tool_guard
def busiest_facility_tool(
    date_from: str | None = None,
    date_to: str | None = None,
    metric: str = "count",
    limit: int = 10,
) -> str:
    """Rank all facilities/yards by activity without requiring named facilities.
    Use for "which yard is busiest", "busiest facility this month", and cross-facility ranking.

    Args:
        date_from: Optional start datetime or date preset keyword.
        date_to: Optional end datetime.
        metric: Ranking metric. Use "count" for distinct visible containers or "trans" for visible transactions.
        limit: Maximum number of facilities to return.
    """
    rows = project_metrics(date_from=date_from, date_to=date_to)
    if not rows:
        return f"No facility metrics found {_date_range_label(date_from, date_to)}."
    metric_key = "trans" if str(metric or "").lower().startswith("trans") else "count"
    totals: dict[str, dict] = {}
    for row in rows:
        facility = row.get("facility") or row.get("project_name") or str(row.get("bucket_id") or row.get("bucket") or "Unknown")
        value = row.get(metric_key)
        if value is None and metric_key == "count":
            value = row.get("containers")
        try:
            numeric = float(value or 0)
        except (TypeError, ValueError):
            numeric = 0
        slot = totals.setdefault(facility, {"facility": facility, "count": 0.0, "trans": 0.0, "days": 0})
        slot[metric_key] += numeric
        slot["days"] += 1
        for other_key in ("count", "trans"):
            if other_key == metric_key:
                continue
            try:
                slot[other_key] += float(row.get(other_key) or (row.get("containers") if other_key == "count" else 0) or 0)
            except (TypeError, ValueError):
                pass
    ranking = sorted(totals.values(), key=lambda item: item.get(metric_key, 0), reverse=True)
    bounded_limit = max(1, min(int(limit or 10), 25))
    return json.dumps({
        **_date_range_meta(date_from, date_to),
        "metric": metric_key,
        "metric_semantics": {
            "count": "distinct visible containers/day",
            "trans": "visible transactions/day",
        },
        "busiest_facility": ranking[0] if ranking else None,
        "ranking": ranking[:bounded_limit],
    }, default=str)


@_resolve_tool_dates
@_tool_guard
def yard_inventory_tool(
    facility: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """List all assets currently detected at a facility/yard. Use for "what's in the yard",
    "show me all containers at Utah Intermodal Ramp", "inventory at a facility". Returns the full asset list
    with IDs, status codes, headings, and timestamps.

    Args:
        facility: The facility/yard name (e.g. "Utah Intermodal Ramp", a specific yard name).
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        results = get_facility_recent(facility, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't retrieve the yard inventory right now."
    if not results:
        return f"No assets found at {facility} {_date_range_label(date_from, date_to)}."
    return json.dumps({
        "facility": facility,
        **_date_range_meta(date_from, date_to),
        "count": len(results),
        "assets": results[:50],
    }, default=str)


@_resolve_tool_dates
@_tool_guard
def status_distribution_tool(
    facility: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Show the breakdown of status codes (A0, A1, I1-I7) for detections at a facility.
    Use for "what's the read quality at Utah Intermodal Ramp", "how many low-confidence scans", "status breakdown".

    Args:
        facility: Optional facility name. Omit for all facilities.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        if facility:
            results = get_facility_recent(facility, date_from=date_from, date_to=date_to)
        else:
            from app.data import query_assets
            results = query_assets(date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't retrieve the status distribution right now."
    if not results:
        scope = f" at {facility}" if facility else ""
        return f"No assets found{scope} {_date_range_label(date_from, date_to)}."
    counts = {}
    for r in results:
        sc = r.get("status_code") or "unknown"
        counts[sc] = counts.get(sc, 0) + 1
    return json.dumps({
        "facility": facility or "all facilities",
        **_date_range_meta(date_from, date_to),
        "total": len(results),
        "by_status": counts,
    }, default=str)


@_resolve_tool_dates
@_tool_guard
def container_company_tool(
    company_prefix: str,
    facility: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Find all containers from a specific company (by the 4-letter BIC owner code prefix).
    Use for "show me all HAPU containers", "find COSU assets", "containers from Maersk".

    Args:
        company_prefix: The 4-letter company prefix (e.g. "HAPU", "COSU", "TRBU").
        facility: Optional facility to filter by.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        from app.data import query_assets
        results = query_assets(date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't query asset records right now."
    prefix = company_prefix.upper()
    matches = [r for r in results if r.get("container_company", "") == prefix]
    if facility:
        matches = [r for r in matches if facility.lower() in (r.get("location") or "").lower()]
    if not matches:
        scope = f" at {facility}" if facility else ""
        return f"No {prefix} containers found{scope} {_date_range_label(date_from, date_to)}."
    return json.dumps({
        "company_prefix": prefix,
        "facility": facility or "all",
        **_date_range_meta(date_from, date_to),
        "count": len(matches),
        "assets": matches[:50],
    }, default=str)


@_tool_guard
def detention_list_tool(facility: str, threshold_hours: float = 72) -> str:
    """Find containers that have been at a facility longer than a threshold (detention/demurrage risk).
    Use for "what containers have been at Utah Intermodal Ramp too long", "detention risk at a facility",
    "containers exceeding dwell threshold".

    Args:
        facility: The facility/yard name.
        threshold_hours: How many hours is considered too long (default 72 = 3 days).
    """
    try:
        from app.data import query_assets
        date_from = _iso_z(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=threshold_hours * 2))
        results = query_assets(location=facility, date_from=date_from)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't query asset records right now."
    if not results:
        return f"No assets found at {facility} to check for detention."
    now = datetime.datetime.now(datetime.timezone.utc)
    flagged = []
    for r in results:
        cid = r.get("text", "")
        if not cid:
            continue
        timeline = get_asset_timeline(cid)
        facility_scans = [t for t in timeline if facility.lower() in (t.get("location") or "").lower()]
        if not facility_scans:
            continue
        latest = facility_scans[0]
        try:
            latest_dt = datetime.datetime.fromisoformat(latest.get("datetime", ""))
            dwell = (now - latest_dt).total_seconds() / 3600.0
        except (ValueError, TypeError):
            continue
        if dwell > threshold_hours:
            flagged.append({
                "container_id": cid,
                "status_code": r.get("status_code"),
                "dwell_hours": round(dwell, 1),
                "last_seen": latest.get("datetime"),
                "location": latest.get("location"),
            })
    if not flagged:
        return f"No containers at {facility} exceed the {threshold_hours}h threshold."
    flagged.sort(key=lambda x: x["dwell_hours"], reverse=True)
    return json.dumps({
        "facility": facility,
        "threshold_hours": threshold_hours,
        "count": len(flagged),
        "containers": flagged[:30],
    }, default=str)


@_resolve_tool_dates
@_tool_guard
def inbound_outbound_tool(
    facility: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Count inbound (L2R) vs outbound (R2L) detections at a gate/facility.
    Use for "how many inbound containers at Utah Intermodal Ramp today", "gate traffic direction", "inbound vs outbound".

    Args:
        facility: The facility/gate name.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        results = get_facility_recent(facility, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't retrieve the gate traffic data right now."
    if not results:
        return f"No detections at {facility} {_date_range_label(date_from, date_to)}."
    inbound = [r for r in results if (r.get("asset_heading") or "").upper() == "L2R"]
    outbound = [r for r in results if (r.get("asset_heading") or "").upper() == "R2L"]
    unknown = [r for r in results if not r.get("asset_heading")]
    return json.dumps({
        "facility": facility,
        **_date_range_meta(date_from, date_to),
        "total": len(results),
        "inbound_count": len(inbound),
        "outbound_count": len(outbound),
        "unknown_direction": len(unknown),
        "inbound_assets": [r.get("text") for r in inbound[:20]],
        "outbound_assets": [r.get("text") for r in outbound[:20]],
    }, default=str)




@_resolve_tool_dates
@_tool_guard
def chassis_activity_tool(
    chassis_id: str | None = None,
    facility: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Query chassis detections. SiteTrax also tracks chassis (different from containers).
    Chassis IDs look like 4 letters + 6-7 digits (e.g. CHAS123456). Use for "find chassis",
    "chassis at Utah Intermodal Ramp", "chassis activity".

    Args:
        chassis_id: Optional chassis ID to filter by.
        facility: Optional facility to filter by.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        from app.data import query_assets
        results = query_assets(container_id=chassis_id, location=facility, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't query chassis records right now."
    chassis = [r for r in results if "chassis" in (r.get("type") or "").lower() or (chassis_id and chassis_id.upper() in (r.get("text") or "").upper())]
    if not chassis:
        return f"No chassis found{f' matching {chassis_id}' if chassis_id else ''}{f' at {facility}' if facility else ''}."
    return json.dumps({
        "count": len(chassis),
        **_date_range_meta(date_from, date_to),
        "chassis": chassis[:20],
    }, default=str)


@_resolve_tool_dates
@_tool_guard
def duplicate_detection_tool(
    facility: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Find containers that were scanned multiple times (potential duplicates or re-scans).
    Use for "any duplicates today", "containers scanned more than once".

    Args:
        facility: Optional facility to filter by.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        from app.data import query_assets
        results = query_assets(location=facility, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't query for duplicates right now."
    seen = {}
    for r in results:
        cid = r.get("text", "")
        if cid:
            seen[cid] = seen.get(cid, 0) + 1
    dups = {cid: count for cid, count in seen.items() if count > 1}
    if not dups:
        return f"No duplicate scans found{f' at {facility}' if facility else ''} {_date_range_label(date_from, date_to)}."
    return json.dumps({
        "facility": facility or "all",
        **_date_range_meta(date_from, date_to),
        "duplicate_count": len(dups),
        "duplicates": sorted([{"container_id": cid, "scan_count": count} for cid, count in dups.items()], key=lambda x: x["scan_count"], reverse=True)[:30],
    }, default=str)


@_resolve_tool_dates
@_tool_guard
def recent_activity_by_company_tool(
    company_prefix: str,
    facility: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Show recent scan activity for a specific company/operator. Use for "HAPU activity today",
    "what did Maersk do this week", "COSCO containers at Utah Intermodal Ramp today".

    Args:
        company_prefix: The 4-letter BIC owner code (e.g. "HAPU", "COSU", "MAEU").
        facility: Optional facility to filter by.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        from app.data import query_assets
        results = query_assets(location=facility, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't query activity right now."
    prefix = company_prefix.upper()
    matches = [r for r in results if r.get("container_company", "") == prefix]
    if not matches:
        return f"No {prefix} activity found{f' at {facility}' if facility else ''} {_date_range_label(date_from, date_to)}."
    inbound = [r for r in matches if (r.get("asset_heading") or "").upper() == "L2R"]
    outbound = [r for r in matches if (r.get("asset_heading") or "").upper() == "R2L"]
    return json.dumps({
        "company": prefix,
        "facility": facility or "all",
        **_date_range_meta(date_from, date_to),
        "total_scans": len(matches),
        "inbound": len(inbound),
        "outbound": len(outbound),
        "latest_scans": matches[:10],
    }, default=str)


@_tool_guard
def get_user_preferences_tool(tool_context: ToolContext) -> str:
    """Retrieve the user's saved preferences from session state. Use when the user mentions
    "my default yard", "my usual facility", or when you need context about what the user
    typically monitors. Returns preferences stored in ADK state.
    """
    prefs = {}
    for key, value in tool_context.state.to_dict().items():
        if str(key).startswith("user:preference:"):
            prefs[str(key).replace("user:preference:", "", 1)] = value
    return json.dumps({
        "preferences": prefs,
        "session_id": tool_context.session.id if tool_context.session else None,
        "note": "Preferences are stored in ADK session/user state. Use them to fill missing parameters, but verify live asset status with data tools.",
    })


@_tool_guard
def set_user_preferences_tool(preferences_json: str, tool_context: ToolContext) -> str:
    """Save user preferences for future conversations. Use when the user
    says "my default yard is Utah Intermodal Ramp", "I usually work with a specific facility", or sets alert thresholds.
    The backend stores these in ADK state for cross-turn context.

    Args:
        preferences_json: JSON string of preferences, e.g. '{"default_facility": "Utah Intermodal Ramp", "alert_threshold_hours": 48}'.
    """
    try:
        prefs = json.loads(preferences_json)
    except json.JSONDecodeError:
        return "Invalid preferences JSON."
    for key, value in prefs.items():
        tool_context.state[f"user:preference:{key}"] = value
    return json.dumps({
        "status": "saved",
        "preferences": prefs,
        "session_id": tool_context.session.id if tool_context.session else None,
        "message": "Preferences noted. I will use these defaults when answering future questions.",
    })





@_resolve_tool_dates
@_tool_guard
def review_queue_tool(
    facility: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status_codes: str | None = None,
) -> str:
    """Find detections that need manual review (non-A0 status codes like I1-I7, A1).
    Use for "what needs review", "low confidence scans", "detections to verify",
    "which containers had bad reads". This tool reports both A0 rate and review rate.

    Args:
        facility: Optional facility to filter by.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
        status_codes: Comma-separated status codes to filter (e.g. "I1,I2,I3"). Default is all non-A0 codes.
    """
    try:
        from app.data import query_assets
        results = query_assets(location=facility, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't retrieve the review queue right now."
    if not results:
        return f"No detections found{f' at {facility}' if facility else ''} {_date_range_label(date_from, date_to)}."
    
    if status_codes:
        target_codes = {s.strip().upper() for s in status_codes.split(",")}
        review_items = [r for r in results if (r.get("status_code") or "A0") in target_codes]
    else:
        review_items = [r for r in results if (r.get("status_code") or "A0") != "A0"]
    
    if not review_items:
        return f"All {len(results)} detections{f' at {facility}' if facility else ''} have A0 (confident) status. Nothing needs review."
    
    by_code = {}
    for r in review_items:
        sc = r.get("status_code") or "unknown"
        by_code.setdefault(sc, []).append(r)

    enriched_items = []
    for r in review_items[:25]:
        item = dict(r)
        asset_id = item.get("id")
        image_url = item.get("asset_image") or item.get("image_url") or item.get("thumbnail_url") or item.get("thumbnail")
        if not image_url and asset_id is not None:
            try:
                detail = get_asset_detail(asset_id) or {}
            except Exception:
                detail = {}
            image_url = detail.get("asset_image") or detail.get("image_url") or detail.get("thumbnail_url") or detail.get("thumbnail")
        if image_url:
            item["image_url"] = image_url
            item["asset_image"] = image_url
            if not item.get("thumbnail_url"):
                item["thumbnail_url"] = image_url
        enriched_items.append(item)
    
    summary = {sc: len(items) for sc, items in by_code.items()}
    review_rate_percent = round(len(review_items) / len(results) * 100, 1) if results else 0
    a0_rate_percent = round(100 - review_rate_percent, 1) if results else 0
    return json.dumps({
        "facility": facility or "all",
        **_date_range_meta(date_from, date_to),
        "total_detections": len(results),
        "needs_review_count": len(review_items),
        "review_rate_percent": review_rate_percent,
        "a0_rate_percent": a0_rate_percent,
        "by_status_code": summary,
        "items_needing_review": enriched_items,
        "images": [item for item in enriched_items if item.get("image_url")],
        "raw_items": review_items[:25],
    }, default=str)


@_resolve_tool_dates
@_tool_guard
def turnaround_time_tool(
    facility: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Calculate gate turnaround time — how long containers spend at a facility
    between inbound (L2R) and outbound (R2L) detection.
    Use for "turnaround time", "how long do containers stay", "gate dwell",
    "container throughput time".

    Args:
        facility: The facility/gate name.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        results = get_facility_recent(facility, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return f"Sorry, I couldn't retrieve gate data for '{facility}'."
    if not results:
        return f"No gate detections at '{facility}' {_date_range_label(date_from, date_to)}."
    
    container_events = {}
    for r in results:
        cid = r.get("text", "")
        if not cid:
            continue
        heading = (r.get("asset_heading") or "").upper()
        dt = _parse_dt(r.get("datetime"))
        if not dt:
            continue
        if cid not in container_events:
            container_events[cid] = {"inbound": None, "outbound": None}
        if heading == "L2R" and (not container_events[cid]["inbound"] or dt > container_events[cid]["inbound"]):
            container_events[cid]["inbound"] = dt
        if heading == "R2L" and (not container_events[cid]["outbound"] or dt > container_events[cid]["outbound"]):
            container_events[cid]["outbound"] = dt
    
    turnarounds = []
    for cid, events in container_events.items():
        if events["inbound"] and events["outbound"] and events["outbound"] > events["inbound"]:
            hours = (events["outbound"] - events["inbound"]).total_seconds() / 3600.0
            turnarounds.append({
                "container_id": cid,
                "inbound_time": events["inbound"].isoformat(),
                "outbound_time": events["outbound"].isoformat(),
                "turnaround_hours": round(hours, 1),
            })
    
    if not turnarounds:
        return f"No complete inbound+outbound pairs found at '{facility}' {_date_range_label(date_from, date_to)}."
    
    times = [t["turnaround_hours"] for t in turnarounds]
    return json.dumps({
        "facility": facility,
        **_date_range_meta(date_from, date_to),
        "containers_with_turnaround": len(turnarounds),
        "average_turnaround_hours": round(sum(times) / len(times), 1),
        "median_turnaround_hours": round(sorted(times)[len(times)//2], 1),
        "fastest_turnaround_hours": round(min(times), 1),
        "slowest_turnaround_hours": round(max(times), 1),
        "turnarounds": sorted(turnarounds, key=lambda x: x["turnaround_hours"], reverse=True)[:20],
    }, default=str)


@_resolve_tool_dates
@_tool_guard
def facility_time_of_day_tool(
    facility: str,
    cutoff_time: str = "16:00",
    direction: str = "outbound",
    date_from: str | None = None,
    date_to: str | None = None,
    timezone_name: str = "America/Denver",
    limit: int = 30,
) -> str:
    """Analyze how often movements happen after a local cutoff time.
    Use for "late exits", "after-hours departures", "how often are there outbound moves after 4pm",
    "frequency of departures after close", and similar time-of-day questions.

    Args:
        facility: The facility/yard name.
        cutoff_time: Local clock time in HH:MM format used as the cutoff (default 16:00).
        direction: "outbound", "inbound", or "all". Outbound maps to R2L; inbound maps to L2R.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601).
        timezone_name: IANA timezone name used for local cutoff comparison.
        limit: Maximum day buckets to include in the output.
    """
    try:
        if not date_from and not date_to:
            now = datetime.datetime.now(datetime.timezone.utc)
            date_from = _iso_z(now - datetime.timedelta(days=30))
            date_to = _iso_z(now)
        results = get_facility_recent(facility, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return f"Sorry, I couldn't retrieve movement data for '{facility}'."

    if not results:
        return f"No detections found at '{facility}' {_date_range_label(date_from, date_to)}."

    try:
        cutoff_hour, cutoff_minute = [int(part) for part in cutoff_time.split(":", 1)]
    except Exception:
        cutoff_hour, cutoff_minute = 16, 0
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = ZoneInfo("UTC")

    direction = (direction or "outbound").lower()
    target_headings = {"r2l"} if direction == "outbound" else {"l2r"} if direction == "inbound" else {"r2l", "l2r"}

    daily_totals: dict[str, int] = {}
    daily_late: dict[str, int] = {}
    late_samples: list[dict] = []
    total_target = 0
    late_total = 0

    for row in results:
        heading = (row.get("asset_heading") or "").lower()
        if heading and heading not in target_headings:
            continue
        dt = _parse_dt(row.get("datetime"))
        if not dt:
            continue
        local_dt = dt.astimezone(tz)
        day_key = local_dt.date().isoformat()
        daily_totals[day_key] = daily_totals.get(day_key, 0) + 1
        total_target += 1
        cutoff_dt = local_dt.replace(hour=cutoff_hour, minute=cutoff_minute, second=0, microsecond=0)
        is_late = local_dt >= cutoff_dt
        if is_late:
            late_total += 1
            daily_late[day_key] = daily_late.get(day_key, 0) + 1
            if len(late_samples) < max(1, min(limit, 25)):
                late_samples.append({
                    "container_id": row.get("text"),
                    "facility": row.get("location") or facility,
                    "datetime": row.get("datetime"),
                    "local_datetime": local_dt.isoformat(),
                    "status_code": row.get("status_code"),
                    "asset_heading": row.get("asset_heading"),
                    "image_url": row.get("image_url") or row.get("asset_image") or row.get("thumbnail_url"),
                    "video_name": row.get("video_name"),
                    "raw_payload": row.get("raw_payload"),
                })

    by_day = []
    for day in sorted(daily_totals.keys()):
        total = daily_totals.get(day, 0)
        late = daily_late.get(day, 0)
        rate = round((late / total * 100), 1) if total else 0
        by_day.append({
            "date": day,
            "total_movements": total,
            "late_movements": late,
            "late_rate_percent": rate,
        })

    rate_percent = round((late_total / total_target * 100), 1) if total_target else 0
    answer = (
        f"{facility} had {late_total} late {direction} movement{'s' if late_total != 1 else ''} "
        f"after {cutoff_time} over {_date_range_label(date_from, date_to)}."
    )
    if total_target:
        answer += f" That is {rate_percent}% of {total_target} matching movements."

    return json.dumps({
        "answer": answer,
        "title": f"{facility} late {direction} movements after {cutoff_time}",
        "datasets": [
            {
                "name": "late_movements_by_day",
                "label": "Late Movements by Day",
                "entity_type": "movement",
                "columns": [
                    {"key": "date", "label": "Date"},
                    {"key": "total_movements", "label": "Total Movements"},
                    {"key": "late_movements", "label": "Late Movements"},
                    {"key": "late_rate_percent", "label": "Late Rate %"},
                ],
                "rows": by_day,
                "count": len(by_day),
            },
            {
                "name": "late_samples",
                "label": "Late Movement Samples",
                "entity_type": "movement",
                "columns": [
                    {"key": "container_id", "label": "Container"},
                    {"key": "facility", "label": "Facility"},
                    {"key": "local_datetime", "label": "Local Time"},
                    {"key": "status_code", "label": "Status"},
                    {"key": "asset_heading", "label": "Heading"},
                ],
                "rows": late_samples,
                "count": len(late_samples),
            },
        ],
        "visualizations": [
            {"type": "metric_grid", "dataset": "late_movements_by_day", "title": "Late exit summary"},
            {"type": "bar", "dataset": "late_movements_by_day", "title": "Late exits by day"},
            {"type": "table", "dataset": "late_movements_by_day", "title": "Daily counts"},
            {"type": "table", "dataset": "late_samples", "title": "Sample late movements"},
        ],
        "references": [
            {"label": "Status codes", "url": "https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json"},
            {"label": "SiteTrax products", "url": "https://sitetrax.io/products/"},
        ],
        "provenance": {
            "facility": facility,
            "cutoff_time": cutoff_time,
            "direction": direction,
            "timezone_name": timezone_name,
            "date_from": date_from,
            "date_to": date_to,
            "rows_scanned": len(results),
            "matching_movements": total_target,
            "late_movements": late_total,
        },
    }, default=str)


@_resolve_tool_dates
@_tool_guard
def missing_containers_tool(
    facility: str | None = None,
    days_since_last_seen: int = 7,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Find containers that were detected in the past but haven't been seen recently.
    Use for "which containers are missing", "containers not seen in 3 days",
    "missing assets", "containers that left and never returned".

    Args:
        facility: Optional facility to focus on. Omit for all facilities.
        days_since_last_seen: How many days without a detection counts as "missing" (default 7).
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        from app.data import query_assets
        results = query_assets(location=facility, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't query for missing containers right now."
    if not results:
        return f"No historical data found{f' for {facility}' if facility else ''}."
    
    now = datetime.datetime.now(datetime.timezone.utc)
    threshold = datetime.timedelta(days=days_since_last_seen)
    
    last_seen = {}
    for r in results:
        cid = r.get("text", "")
        if not cid:
            continue
        dt = _parse_dt(r.get("datetime"))
        if not dt:
            continue
        if cid not in last_seen or dt > last_seen[cid]["dt"]:
            last_seen[cid] = {"dt": dt, "location": r.get("location"), "status_code": r.get("status_code")}
    
    missing = []
    for cid, info in last_seen.items():
        if now - info["dt"] > threshold:
            missing.append({
                "container_id": cid,
                "last_seen": info["dt"].isoformat(),
                "days_missing": round((now - info["dt"]).total_seconds() / 86400, 1),
                "last_location": info["location"],
                "last_status": info["status_code"],
            })
    
    missing.sort(key=lambda x: x["days_missing"], reverse=True)
    if not missing:
        return f"All {len(last_seen)} containers have been seen within the last {days_since_last_seen} days."
    
    return json.dumps({
        "facility": facility or "all",
        "days_since_last_seen_threshold": days_since_last_seen,
        **_date_range_meta(date_from, date_to),
        "total_containers_tracked": len(last_seen),
        "missing_count": len(missing),
        "missing": missing[:30],
    }, default=str)


@_resolve_tool_dates
@_tool_guard
def camera_health_tool(
    facility: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Check camera health by comparing recent detection counts per camera.
    Use for "is camera X working", "camera status", "which cameras are offline",
    "detection counts by camera".

    Args:
        facility: Optional facility to filter by.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        from app.data import query_assets
        results = query_assets(location=facility, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't retrieve camera health data right now."
    if not results:
        return f"No detections found{f' at {facility}' if facility else ''} {_date_range_label(date_from, date_to)}."
    
    by_camera = {}
    by_camera_status = {}
    for r in results:
        cam = r.get("camera") or "unknown"
        by_camera[cam] = by_camera.get(cam, 0) + 1
        sc = r.get("status_code") or "A0"
        if cam not in by_camera_status:
            by_camera_status[cam] = {}
        by_camera_status[cam][sc] = by_camera_status[cam].get(sc, 0) + 1
    
    camera_stats = []
    for cam, count in sorted(by_camera.items(), key=lambda x: x[1], reverse=True):
        a0_rate = round(by_camera_status[cam].get("A0", 0) / count * 100, 1) if count > 0 else 0
        camera_stats.append({
            "camera": cam,
            "detection_count": count,
            "a0_rate_percent": a0_rate,
            "status_breakdown": by_camera_status[cam],
        })
    
    low_activity = [c for c in camera_stats if c["detection_count"] <= 2]
    
    return json.dumps({
        "facility": facility or "all",
        **_date_range_meta(date_from, date_to),
        "total_detections": len(results),
        "camera_count": len(camera_stats),
        "cameras": camera_stats[:30],
        "low_activity_cameras": low_activity,
    }, default=str)


@_tool_guard
def facility_summary_tool(facility: str) -> str:
    """Get a comprehensive summary of a facility/yard: inventory count, status distribution,
    recent gate traffic, detention risk, and latest activity. Use for "how is Utah Intermodal Ramp doing",
    "give me a summary of a facility", "yard overview at a facility", "facility health check".

    Args:
        facility: The facility/yard name (e.g. "Utah Intermodal Ramp", a specific yard name).
    """
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        inventory_date_from = _iso_z(now - datetime.timedelta(days=7))
        recent_date_from = _iso_z(now - datetime.timedelta(hours=24))
        date_to = _iso_z(now)

        inventory = get_facility_recent(facility, date_from=inventory_date_from, date_to=date_to)
        status_counts = {}
        for r in inventory:
            sc = r.get("status_code") or "unknown"
            status_counts[sc] = status_counts.get(sc, 0) + 1

        recent = get_facility_recent(facility, date_from=recent_date_from, date_to=date_to)
        inbound = len([r for r in recent if (r.get("asset_heading") or "").upper() == "L2R"])
        outbound = len([r for r in recent if (r.get("asset_heading") or "").upper() == "R2L"])

        detention_flagged = []
        seen = set()
        for r in inventory:
            cid = r.get("text", "")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            dt_str = r.get("datetime", "")
            try:
                latest_dt = datetime.datetime.fromisoformat(dt_str)
                dwell = (now - latest_dt).total_seconds() / 3600.0
            except (ValueError, TypeError):
                continue
            if dwell > 72:
                detention_flagged.append({"container_id": cid, "dwell_hours": round(dwell, 1)})

        detention_flagged.sort(key=lambda x: x["dwell_hours"], reverse=True)

        latest_scan = None
        if inventory:
            latest_scan = max(inventory, key=lambda r: r.get("datetime", ""))

        total_24h = len(recent)
        total_7d = len(inventory)
        a0_rate = round((status_counts.get("A0", 0) / total_7d * 100), 1) if total_7d > 0 else 0

        return json.dumps({
            "facility": facility,
            "inventory_date_from": inventory_date_from,
            "recent_date_from": recent_date_from,
            "date_to": date_to,
            "summary": {
                "total_containers_7d": total_7d,
                "total_scans_24h": total_24h,
                "a0_rate_percent": a0_rate,
                "inbound_24h": inbound,
                "outbound_24h": outbound,
                "detention_risk_count": len(detention_flagged),
                "latest_scan": latest_scan.get("text") if latest_scan else None,
                "latest_scan_time": latest_scan.get("datetime") if latest_scan else None,
            },
            "status_distribution": status_counts,
            "top_detention_risks": detention_flagged[:10],
        }, default=str)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception as e:
        return f"Sorry, I couldn't generate the facility summary right now. Error: {e}"



@_tool_guard
def asset_journey_tool(container_id: str) -> str:
    """Show the complete journey of a container across all facilities over time.
    Use for "where has this container been?", "show me the journey of TRBU5341840",
    "track container X across facilities", "container movement history".
    Returns chronological timeline of detections with facility, time, heading, and status.

    Args:
        container_id: The container ID (e.g. TRBU5341840).
    """
    try:
        timeline = get_asset_timeline(container_id)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return f"Sorry, I couldn't retrieve the journey for {container_id}."
    if not timeline:
        return f"No journey data found for container {container_id}."
    
    journey = []
    facilities_visited = set()
    for t in timeline:
        journey.append({
            "facility": t.get("location", "Unknown"),
            "datetime": t.get("datetime"),
            "heading": t.get("asset_heading", "-"),
            "status_code": t.get("status_code", "N/A"),
            "gps_lat": t.get("gps_lat"),
            "gps_lon": t.get("gps_lon"),
        })
        facilities_visited.add(t.get("location", "Unknown"))
    
    return json.dumps({
        "container_id": container_id,
        "total_detections": len(timeline),
        "facilities_visited": sorted(facilities_visited),
        "facility_count": len(facilities_visited),
        "journey": journey,
    }, default=str)


@_resolve_tool_dates
@_tool_guard
def compare_facilities_tool(
    facility_a: str,
    facility_b: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Compare two facilities side by side: scan volume, A0 rate, traffic direction, detention risk.
    Use for "compare Utah Intermodal Ramp and another facility", "how does a facility compare to Utah", "which facility is busier".

    Args:
        facility_a: First facility name (e.g. "Utah Intermodal Ramp").
        facility_b: Second facility name (e.g. "Utah Intermodal Ramp").
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    try:
        inv_a = get_facility_recent(facility_a, date_from=date_from, date_to=date_to)
        inv_b = get_facility_recent(facility_b, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't compare the facilities right now."
    
    def _stats(inv, facility):
        total = len(inv)
        a0_count = sum(1 for r in inv if r.get("status_code") == "A0")
        inbound = sum(1 for r in inv if (r.get("asset_heading") or "").upper() == "L2R")
        outbound = sum(1 for r in inv if (r.get("asset_heading") or "").upper() == "R2L")
        a0_rate = round(a0_count / total * 100, 1) if total > 0 else 0
        return {
            "facility": facility,
            "total_scans": total,
            "a0_count": a0_count,
            "a0_rate_percent": a0_rate,
            "inbound": inbound,
            "outbound": outbound,
        }
    
    stats_a = _stats(inv_a, facility_a)
    stats_b = _stats(inv_b, facility_b)
    
    winner = facility_a if stats_a["total_scans"] >= stats_b["total_scans"] else facility_b
    busier = stats_a["total_scans"] if stats_a["total_scans"] >= stats_b["total_scans"] else stats_b["total_scans"]
    
    return json.dumps({
        **_date_range_meta(date_from, date_to),
        "facility_a": stats_a,
        "facility_b": stats_b,
        "busier_facility": winner,
        "busier_scan_count": busier,
    }, default=str)



@_resolve_tool_dates
@_tool_guard
def rule_history_tool(
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Get a history of recently fired monitoring rule alerts. Use for "show me recent alerts",
    "what rules fired today", "alert history", "monitoring activity".

    Args:
        date_from: Optional start datetime in ISO 8601 format.
        date_to: Optional end datetime in ISO 8601 format.
    """
    try:
        from app.monitoring import store
        alerts = store.get_fired_alerts(hours_back=0)
        rules = {r.id: r for r in store.get_all_rules()}
    except Exception:
        return "Sorry, I couldn't retrieve the alert history right now."
    if date_from or date_to:
        def _in_range(alert):
            return _date_in_range(alert.get("timestamp"), date_from=date_from, date_to=date_to)
        alerts = [alert for alert in alerts if _in_range(alert)]
    if not alerts:
        return f"No alerts fired {_date_range_label(date_from, date_to)}."
    enriched = []
    for alert in alerts:
        rule = rules.get(alert.get("rule_id"))
        enriched.append({
            "rule_id": alert.get("rule_id"),
            "timestamp": alert.get("timestamp"),
            "template": rule.template_name.value if rule else "unknown",
            "display_name": TEMPLATES[rule.template_name].display_name if rule else "Unknown rule",
            "description": TEMPLATES[rule.template_name].description if rule else "",
            "trigger_description": TEMPLATES[rule.template_name].trigger_description if rule else "",
            "params": rule.params if rule else {},
        })
    return json.dumps({
        **_date_range_meta(date_from, date_to),
        "count": len(enriched),
        "alerts": enriched,
    }, default=str)

# Delivery channels the backend can actually send through.
# Email is wired via Resend; in-app notifications are always available.
SUPPORTED_NOTIFICATION_CHANNELS = {"in_app", "email"}

# Map common phrasings to a canonical channel id.
_CHANNEL_ALIASES = {
    "": "in_app", "in_app": "in_app", "in-app": "in_app", "inapp": "in_app",
    "app": "in_app", "notification": "in_app", "notifications": "in_app",
    "sitetrax": "in_app", "default": "in_app",
    "email": "email", "e-mail": "email", "mail": "email",
    "sms": "sms", "text": "sms", "txt": "sms", "text message": "sms",
    "voice": "voice", "call": "voice", "phone": "voice", "phone call": "voice",
    "slack": "slack", "whatsapp": "whatsapp", "teams": "teams",
    "telegram": "telegram", "webhook": "webhook", "push": "push",
}


def _normalize_channel(channel: str | None) -> str:
    key = (channel or "").strip().lower()
    return _CHANNEL_ALIASES.get(key, key or "in_app")


@_tool_guard
def create_monitoring_rule_tool(template_name: str, params: str, channel: str = "in_app") -> str:
    """Create a new monitoring rule from a template. Call this when the user asks to monitor
    or watch for something that matches an available template.

    Available templates:
    """ + TEMPLATE_DESCRIPTIONS_FOR_PROMPT + """

    Args:
        template_name: The template ID to use. Must be one of the template IDs listed above.
        params: JSON string of parameter values. e.g. '{"container_id": "TRBU5341840", "location": a specific yard name}'.
        channel: The delivery channel the user asked for, verbatim if possible (e.g. "sms",
            "email", "slack", "voice"). If the user did not specify one, leave it as the
            default "in_app". You do NOT need to decide whether a channel is supported —
            this tool detects unsupported channels and logs the capability gap itself, so
            never call log_opportunity_tool for a delivery channel.
    """
    try:
        template = TEMPLATES.get(TemplateName(template_name))
    except ValueError:
        return (
            f"Unknown template '{template_name}'. Available templates: "
            f"{', '.join(t.value for t in TemplateName)}"
        )

    try:
        parsed_params = json.loads(params)
    except json.JSONDecodeError:
        parsed_params = {}
        for key, value in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^,]+)", params):
            parsed_params[key] = value.strip().strip("\"'")
        if not parsed_params:
            return f"Invalid params JSON: {params}. Please provide valid JSON."

    missing = [p.name for p in template.params if p.required and p.name not in parsed_params]
    if missing:
        return f"Missing required parameters: {', '.join(missing)}. Required: {', '.join(p.name for p in template.params if p.required)}"

    requested_channel = _normalize_channel(channel)
    channel_supported = requested_channel in SUPPORTED_NOTIFICATION_CHANNELS
    delivery_channel = requested_channel if channel_supported else "in_app"

    existing = getattr(store, "find_duplicate_rule", None)
    if existing:
        existing = existing(template.name, parsed_params)

    if existing:
        # Duplicate detected — don't create a new rule.
        response = {
            "status": "created",
            "already_exists": True,
            "rule_id": existing.id,
            "template": template.display_name,
            "params": parsed_params,
            "delivery_channel": delivery_channel,
            "message": (
                f"A monitoring rule for this already exists (ID: {existing.id}). "
                f"You'll be notified when: {template.trigger_description}."
            ),
        }
    else:
        try:
            rule = store.create_rule(template_name=template.name, params=parsed_params)
        except Exception:
            return "Sorry, I couldn't create the monitoring rule. Please try again."
        response = {
            "status": "created",
            "rule_id": rule.id,
            "template": template.display_name,
            "params": parsed_params,
            "delivery_channel": delivery_channel,
            "message": (
                f"Monitoring rule created. You'll be notified via Email. "
            ),
        }

    # Deterministically log a capability gap when the requested channel can't be delivered.
    if not channel_supported:
        ch = requested_channel.upper()
        if existing:
            response["message"] = (
                f"A monitoring rule for this already exists (ID: {existing.id}). "
                f"You'll be notified via in-app notifications when: {template.trigger_description}. "
                f"{ch} delivery isn't supported yet — I've logged it as a capability gap."
            )
        else:
            response["message"] = (
                f"Monitoring rule created. You'll be notified via in-app notifications when: "
                f"{template.trigger_description}. {ch} delivery isn't supported yet — I've logged it as a capability gap."
            )
        try:
            opp = store.log_opportunity(
                user_request=f"Send notifications via {requested_channel}",
                reason=f"Delivery channel '{requested_channel}' is not supported. "
                       f"Supported channels: {', '.join(sorted(SUPPORTED_NOTIFICATION_CHANNELS))}.",
                category="Notification Channels",
            )
            response["channel_gap_logged"] = True
            response["unsupported_channel"] = requested_channel
            # Nested payload so the frontend renders a distinct "Opportunity logged" card.
            response["channel_gap"] = {
                "status": "logged",
                "opportunity_id": opp.id,
                "category": "Notification Channels",
                "message": (
                    f"{ch} delivery isn't available yet. I've logged it as a capability "
                    f"gap so the team can wire up {ch} notifications."
                ),
            }
        except Exception:
            # Rule creation already succeeded; don't fail the whole call on gap-logging.
            response["channel_gap_logged"] = False

    return json.dumps(response)


@_tool_guard
def facility_health_check_tool(facility: str) -> str:
    """Run a comprehensive health check on a facility by querying inventory,
    status distribution, camera health, detention risk, and gate traffic.
    Use for "how is my yard doing", "facility health check", "yard status",
    "give me an overview of Utah Intermodal Ramp", "what is the state of a facility".

    Args:
        facility: The facility/yard name.
    """
    try:
        import json
        results = {}
        now = datetime.datetime.now(datetime.timezone.utc)
        inventory_date_from = _iso_z(now - datetime.timedelta(days=7))
        recent_date_from = _iso_z(now - datetime.timedelta(hours=24))
        date_to = _iso_z(now)

        # 1. Inventory
        inventory = get_facility_recent(facility, date_from=inventory_date_from, date_to=date_to)
        results["inventory_7d"] = len(inventory)
        results["inventory_date_from"] = inventory_date_from
        results["recent_date_from"] = recent_date_from
        results["date_to"] = date_to

        # 2. Status distribution
        status_counts = {}
        for r in inventory:
            sc = r.get("status_code") or "unknown"
            status_counts[sc] = status_counts.get(sc, 0) + 1
        results["status_distribution"] = status_counts

        # 3. Recent activity (24h)
        recent = get_facility_recent(facility, date_from=recent_date_from, date_to=date_to)
        inbound = sum(1 for r in recent if (r.get("asset_heading") or "").upper() == "L2R")
        outbound = sum(1 for r in recent if (r.get("asset_heading") or "").upper() == "R2L")
        results["scans_24h"] = len(recent)
        results["inbound_24h"] = inbound
        results["outbound_24h"] = outbound

        # 4. Camera health
        by_camera = {}
        for r in recent:
            cam = r.get("camera") or "unknown"
            by_camera[cam] = by_camera.get(cam, 0) + 1
        camera_stats = []
        for cam, count in sorted(by_camera.items(), key=lambda x: x[1], reverse=True):
            a0_count = sum(1 for r in recent if r.get("camera") == cam and r.get("status_code") == "A0")
            a0_rate = round(a0_count / count * 100, 1) if count > 0 else 0
            camera_stats.append({"camera": cam, "detections": count, "a0_rate": a0_rate})
        results["cameras"] = camera_stats

        # 5. Detention risk
        detention = []
        seen = set()
        for r in inventory:
            cid = r.get("text", "")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            try:
                dt = datetime.datetime.fromisoformat(r.get("datetime", ""))
                dwell = (now - dt).total_seconds() / 3600.0
            except Exception:
                continue
            if dwell > 72:
                detention.append({"container_id": cid, "dwell_hours": round(dwell, 1)})
        detention.sort(key=lambda x: x["dwell_hours"], reverse=True)
        results["detention_risk"] = detention[:10]
        results["detention_count"] = len(detention)

        # 6. A0 rate
        total = len(inventory)
        a0_rate = round(status_counts.get("A0", 0) / total * 100, 1) if total > 0 else 0
        results["a0_rate_percent"] = a0_rate

        # Overall health score
        health_score = 100
        if a0_rate < 90:
            health_score -= (90 - a0_rate) * 2
        if len(detention) > 5:
            health_score -= min(20, len(detention) * 2)
        if len(recent) < 10:
            health_score -= 10
        health_score = max(0, min(100, round(health_score)))

        results["facility"] = facility
        results["health_score"] = health_score
        results["health_rating"] = "Excellent" if health_score >= 90 else "Good" if health_score >= 75 else "Fair" if health_score >= 50 else "Poor"

        return json.dumps({
            "status": "health_check",
            "facility": facility,
            "health_score": health_score,
            "health_rating": results["health_rating"],
            "message": f"Facility health check for {facility}: {results['health_rating']} ({health_score}/100)."
                       + f" {results['inventory_7d']} containers in 7 days, {a0_rate}% A0 rate,"
                       + f" {len(recent)} scans in 24h ({inbound} in, {outbound} out),"
                       + f" {len(detention)} detention risks.",
            "report": results,
        }, default=str)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return f"Sorry, I couldn't run the health check for '{facility}'."


@_resolve_tool_dates
@_tool_guard
def generate_facility_report_tool(
    facility: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Generate a comprehensive facility health report and save it as a downloadable artifact.
    Use for "generate report for Utah Intermodal Ramp", "facility health report", "yard summary report",
    "export Utah Intermodal Ramp data", "create a report".

    The report includes: inventory summary, status distribution, camera health,
    detention risk, gate traffic, turnaround analysis, and missing containers.

    Args:
        facility: The facility/yard name.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    import datetime
    try:
        inventory = get_facility_recent(facility, date_from=date_from, date_to=date_to)
        recent = get_facility_recent(facility, date_from=date_from, date_to=date_to)
        status_counts = {}
        for r in inventory:
            sc = r.get("status_code") or "unknown"
            status_counts[sc] = status_counts.get(sc, 0) + 1
        inbound = sum(1 for r in recent if (r.get("asset_heading") or "").upper() == "L2R")
        outbound = sum(1 for r in recent if (r.get("asset_heading") or "").upper() == "R2L")
        now = datetime.datetime.now(datetime.timezone.utc)
        detention_flagged = []
        seen = set()
        for r in inventory:
            cid = r.get("text", "")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            try:
                latest_dt = datetime.datetime.fromisoformat(r.get("datetime", ""))
                dwell = (now - latest_dt).total_seconds() / 3600.0
            except Exception:
                continue
            if dwell > 72:
                detention_flagged.append({"container_id": cid, "dwell_hours": round(dwell, 1)})
        detention_flagged.sort(key=lambda x: x["dwell_hours"], reverse=True)
        total_24h = len(recent)
        total_7d = len(inventory)
        a0_rate = round((status_counts.get("A0", 0) / total_7d * 100), 1) if total_7d > 0 else 0
        report = {
            "facility": facility,
            "report_date": now.isoformat(),
            **_date_range_meta(date_from, date_to),
            "summary": {
                "total_containers_7d": total_7d,
                "total_scans_24h": total_24h,
                "a0_rate_percent": a0_rate,
                "inbound_24h": inbound,
                "outbound_24h": outbound,
                "detention_risk_count": len(detention_flagged),
            },
            "status_distribution": status_counts,
            "detention_risk": detention_flagged[:20],
            "top_containers": [{
                "container_id": r.get("text"),
                "status_code": r.get("status_code"),
                "datetime": r.get("datetime"),
            } for r in inventory[:10]],
        }
        return json.dumps({
            "status": "generated",
            "facility": facility,
            **_date_range_meta(date_from, date_to),
            "report": report,
            "message": f"Facility report for {facility} generated successfully." +
                       f" {total_7d} containers {_date_range_label(date_from, date_to)}, {a0_rate}% A0 rate," +
                       f" {len(detention_flagged)} detention risks.",
        }, default=str)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return f"Sorry, I couldn't generate the report for '{facility}'."


@_resolve_tool_dates
@_tool_guard
def export_to_csv_tool(
    facility: str | None = None,
    container_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Export asset detections to a CSV file and return a download link.
    Use for "export to CSV", "download yard data", "spreadsheet export",
    "get Excel file", "export container data".

    Args:
        facility: Optional facility to filter by.
        container_id: Optional container ID to filter by.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601 or a date preset keyword. Rolling windows: last_hour, last_24h, last_7d, last_30d, last_90d, or generic last_<N><m|h|d|w|mo|y> (e.g. last_45d, past_6h). Calendar periods: today, yesterday, this_week, last_week, this_month, last_month, this_quarter, last_quarter, this_year, last_year, ytd/mtd/wtd/qtd, a named month (june, dec_2025), or a quarter (q2, q4_2025). Calendar presets are timezone UTC; closed periods set both bounds automatically. maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601 or relative keyword; maps to created_at__lte).
    """
    import csv, io, os
    try:
        from app.data import query_assets
        results = query_assets(location=facility, container_id=container_id, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't query the data for export."
    if not results:
        return f"No data found{f' for {facility}' if facility else ''}{f' container {container_id}' if container_id else ''}."
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "container_id", "type", "status_code", "datetime", "location",
        "camera", "gps_lat", "gps_lon", "asset_heading", "video_name"
    ])
    writer.writeheader()
    for r in results:
        writer.writerow({
            "container_id": r.get("text", ""),
            "type": r.get("type", ""),
            "status_code": r.get("status_code", ""),
            "datetime": r.get("datetime", ""),
            "location": r.get("location", ""),
            "camera": r.get("camera", ""),
            "gps_lat": r.get("gps_lat", ""),
            "gps_lon": r.get("gps_lon", ""),
            "asset_heading": r.get("asset_heading", ""),
            "video_name": r.get("video_name", ""),
        })
    
    csv_data = output.getvalue()
    output.close()
    
    return json.dumps({
        "status": "exported",
        "facility": facility or "all",
        **_date_range_meta(date_from, date_to),
        "row_count": len(results),
        "csv_data": csv_data,
        "message": f"Exported {len(results)} detections to CSV.",
    })


@_tool_guard
def log_opportunity_tool(user_request: str, reason: str, category: str) -> str:
    """Log an automation opportunity that the system cannot currently fulfill.
    Call this ONLY when the user asks for something genuinely outside all available tools.
    Do NOT call this for notification delivery channels (SMS, voice, Slack, etc.) — those
    are handled automatically by create_monitoring_rule_tool's `channel` argument, which
    logs the channel gap itself.
    DO NOT call this for questions that can be answered with existing tools like:
    query_assets_tool, container_last_seen_tool,
    container_facility_activity_tool, container_dwell_tool, facility_last_scan_tool,
    facility_recent_activity_tool, yard_inventory_tool, status_distribution_tool,
    container_company_tool, detention_list_tool, inbound_outbound_tool,
    facility_summary_tool, duplicate_detection_tool, chassis_activity_tool,
    recent_activity_by_company_tool, facility_metrics_tool, search_videos_tool,
    container_video_tool, create_monitoring_rule_tool.

    Args:
        user_request: The original request from the user.
        reason: Why this can't be automated yet (e.g. "No matching template").
        category: Suggested category for this capability (e.g. "Equipment Maintenance").
    """
    try:
        opp = store.log_opportunity(
            user_request=user_request,
            reason=reason,
            category=category,
        )
    except Exception:
        return "Sorry, I couldn't log this opportunity. Please try again."

    return json.dumps({
        "status": "logged",
        "opportunity_id": opp.id,
        "category": category,
        "message": (
            f"I can't automate that yet — no existing template supports '{category}'. "
            f"But I've logged it as a new automation opportunity. "
            f"Our team can build a custom monitoring agent for this."
        ),
    })


# ── Builder Agent definition ─────────────────────────────────

async def save_session_to_memory_callback(callback_context):
    """Persist completed ADK session events into the configured memory service."""
    try:
        await callback_context.add_session_to_memory()
    except ValueError:
        logger.debug("ADK memory service unavailable; skipping session memory save")
    except Exception:
        logger.exception("Failed to save ADK session to memory")



@_tool_guard
@_resolve_tool_dates
def get_video_metrics_tool(
    facility: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Aggregated video metrics totals for a facility or all facilities.
    Use for "how many videos", "video volume", "video metrics at Utah Intermodal Ramp".
    The live API returns one totals dict (`total_count`, `total_size`, `total_length`), not daily rows.

    Args:
        facility: Optional facility name.
        date_from: Optional start date (ISO 8601).
        date_to: Optional end date (ISO 8601).
    """
    try:
        data = get_video_metrics(facility=facility, date_from=date_from, date_to=date_to)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't retrieve video metrics."
    return json.dumps(data, default=str)


@_tool_guard
def get_auth_self_tool() -> str:
    """Get the current authenticated SiteTrax account and the projects/yards assigned to it.
    Use for "who am I authenticated as?", "what account is this?", "which facilities/yards/projects
    do I have?", "is the SiteTrax API token working?", or auth diagnostics. The facility list is
    fetched live — never assume facility names; rely on this (or list_facilities_tool) to learn them.
    """
    try:
        account = get_auth_self()
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't retrieve the authenticated SiteTrax profile."
    try:
        projects = list_projects()
    except Exception:
        projects = []
    return json.dumps(
        {
            "account": account,
            "facilities": [{"id": p.get("id"), "name": p.get("name")} for p in projects],
        },
        default=str,
    )


@_tool_guard
def get_feedback_choices_tool() -> str:
    """List read-only SiteTrax feedback choices used for review workflows.
    Use when the user asks what feedback/review dispositions are available.
    """
    try:
        return json.dumps({"choices": get_feedback_choices()}, default=str)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return "Sorry, I couldn't retrieve feedback choices."


@_tool_guard
def get_project_last_video_tool(project_id: int | str) -> str:
    """Get the most recent video for a project/facility by project ID.

    Args:
        project_id: SiteTrax project/facility ID.
    """
    try:
        video = get_project_last_video(project_id)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return f"Sorry, I couldn't retrieve the last video for project {project_id}."
    if not video:
        return f"No last video found for project {project_id}."
    return json.dumps(video, default=str)


@_tool_guard
def sitetrax_image_url_to_base64_tool(image_url: str, max_bytes: int = 5_000_000) -> str:
    """Convert a SiteTrax-hosted image URL into a base64 data URL for CSP-restricted clients.
    Only accepts HTTPS URLs from sitetrax.io or subdomains such as *.sitetrax.io.

    Args:
        image_url: The SiteTrax image URL to fetch.
        max_bytes: Maximum image size to fetch; default 5 MB.
    """
    try:
        return json.dumps(sitetrax_image_url_to_base64(image_url, max_bytes=max_bytes), default=str)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception as e:
        return json.dumps({"error": "image_base64_failed", "detail": str(e)}, default=str)


@_tool_guard
def sitetrax_schema_tool(resource: str | None = None) -> str:
    """Inspect the read-only SiteTrax endpoint registry.
    Use this when you are unsure which SiteTrax resource, filters, fields, or relationships
    are available for a user's data question.

    Args:
        resource: Optional resource name, such as assets, videos, asset_timeline,
            asset_metrics, projects, project_metrics, or video_metrics.
    """
    try:
        return json.dumps(get_sitetrax_schema(resource), default=str)
    except Exception as e:
        return json.dumps({
            "error": "schema_lookup_failed",
            "detail": str(e),
            "hint": "Use sitetrax_schema_tool with no resource to list allowed resources.",
        }, default=str)


@_tool_guard
@_resolve_tool_dates
def sitetrax_query_tool(
    resource: str,
    filters_json: str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    ordering: str | None = None,
    limit: int = 50,
    include_related: str | None = None,
) -> str:
    """Schema-guided read-only query across allowed SiteTrax data resources.
    Prefer this for broad or novel SiteTrax data questions because it returns a generic
    visualization envelope with datasets, visualizations, references, provenance, and
    full redacted raw payloads.

    Args:
        resource: Allowed resource from sitetrax_schema_tool, e.g. assets, videos,
            asset_timeline, asset_detail, asset_metrics, project_metrics, projects,
            project_names, video_metrics.
        filters_json: JSON object string for filters. Examples:
            {"facility":"Utah Intermodal Ramp"}, {"container_id":"TRDU1930583"},
            {"status_code":"I1,I6"}, {"id":1558716}.
        search: Optional free-text search when supported by the resource.
        date_from: Optional start datetime in SiteTrax API format (ISO 8601).
        date_to: Optional end datetime in SiteTrax API format (ISO 8601).
        ordering: Optional ordering string, e.g. -created_at.
        limit: Maximum returned rows, bounded to 250.
        include_related: Optional comma-separated related data: playback_url, video_detail, all.
    """
    try:
        data = sitetrax_query(
            resource=resource,
            filters=filters_json,
            search=search,
            date_from=date_from,
            date_to=date_to,
            ordering=ordering,
            limit=limit,
            include_related=include_related,
        )
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception as e:
        return json.dumps({
            "error": "sitetrax_query_failed",
            "detail": str(e),
            "hint": "Call sitetrax_schema_tool to inspect allowed resources and filters.",
        }, default=str)
    return json.dumps(data, default=str)


@_tool_guard
def sitetrax_report_tool(
    query_spec_json: str,
    title: str = "SiteTrax report",
    format: str = "json",
) -> str:
    """Create a downloadable read-only report from a generic SiteTrax query.
    The query_spec_json must contain the same arguments accepted by sitetrax_query_tool.

    Args:
        query_spec_json: JSON object with resource, filters_json or filters, search,
            date_from, date_to, ordering, limit, include_related.
        title: Report title.
        format: "json" or "csv".
    """
    try:
        spec = json.loads(query_spec_json or "{}")
        if not isinstance(spec, dict):
            raise ValueError("query_spec_json must be a JSON object")
        filters = spec.get("filters_json", spec.get("filters"))
        envelope = sitetrax_query(
            resource=spec.get("resource", "assets"),
            filters=filters,
            search=spec.get("search"),
            date_from=spec.get("date_from"),
            date_to=spec.get("date_to"),
            ordering=spec.get("ordering"),
            limit=spec.get("limit", 250),
            include_related=spec.get("include_related"),
        )
        fmt = (format or "json").lower()
        dataset = (envelope.get("datasets") or [{}])[0]
        rows = dataset.get("rows") or []
        safe_title = re.sub(r"[^A-Za-z0-9_.-]+", "_", title).strip("_") or "sitetrax_report"
        if fmt == "csv":
            output = io.StringIO()
            columns = [c.get("key") for c in dataset.get("columns", []) if c.get("key")]
            if not columns and rows:
                columns = [k for k, v in rows[0].items() if k != "raw_payload" and not isinstance(v, (dict, list))]
            writer = csv.DictWriter(output, fieldnames=columns or ["value"], extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row if isinstance(row, dict) else {"value": row})
            content = output.getvalue()
            mime_type = "text/csv"
            filename = f"{safe_title}.csv"
        else:
            fmt = "json"
            content = json.dumps(envelope, indent=2, default=str)
            mime_type = "application/json"
            filename = f"{safe_title}.json"
        return json.dumps({
            **envelope,
            "status": "report_generated",
            "title": title,
            "download": {
                "filename": filename,
                "format": fmt,
                "mime_type": mime_type,
                "content": content,
            },
            "answer": f"{title} is ready with {dataset.get('count', len(rows))} row(s).",
        }, default=str)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception as e:
        return json.dumps({"error": "report_failed", "detail": str(e)}, default=str)


@_tool_guard
def get_timeline_with_videos_tool(container_id: str, limit: int = 20) -> str:
    """Power tool: full detection timeline enriched with video playback URLs.
    Use for "show me the full history of container X with videos",
    "every detection of X with footage".

    Args:
        container_id: The container ID.
        limit: Maximum timeline entries (default 20).
    """
    try:
        timeline = get_timeline_with_videos(container_id, limit=limit)
    except SiteTraxAuthError:
        return _sitetrax_auth_message()
    except Exception:
        return f"Sorry, I couldn't retrieve the timeline for {container_id}."
    if not timeline:
        return f"No timeline data found for {container_id}."
    return json.dumps(_asset_visualization_envelope(
        title=f"Timeline for {container_id.upper()}",
        dataset_name="asset_timeline",
        rows=timeline,
        answer=f"Found {len(timeline)} timeline record(s) for {container_id.upper()}.",
        visualizations=[
            {"type": "timeline", "dataset": "asset_timeline", "title": "Detection timeline"},
            {"type": "image_gallery", "dataset": "asset_timeline", "title": "Detection images"},
            {"type": "video_gallery", "dataset": "asset_timeline", "title": "Related videos"},
            {"type": "table", "dataset": "asset_timeline", "title": "Timeline records"},
        ],
        container_id=container_id,
        count=len(timeline),
        timeline=timeline,
    ), default=str)


BUILDER_PROMPT = """You are SiteTrax.io Atlas Agent — an intelligent operations assistant for logistics and supply chain teams.

SiteTrax uses AI-powered OCR on gate cameras, mobile devices, drones, and vehicle-mounted systems to detect intermodal container IDs, chassis numbers, and asset markings. You have access to the full SiteTrax REST API.

## Data Model

- **container_id**: 4-letter BIC owner code + 7 digits (e.g. TRBU5341840)
- **company_prefix**: First 4 letters of container ID (e.g. "TRBU" = Triton)
- **status_code**: A0=confident, A1=assigned, I1-I7=low-confidence partial reads
- **asset_heading**: L2R=typically inbound, R2L=typically outbound
- **location/facility**: Yard or project name (e.g. "Utah Intermodal Ramp", a specific yard name)
- **datetime**: UTC timestamp of detection
- **video**: Every detection may link to a source video clip with a temporary playback URL
- **asset_image**: Many detections also include a direct image URL for the detected asset
- For facility-level image searches or recent image lists, use `search_images_tool`.

## Reasoning Guidelines

1. **Infer intent, don't pattern-match.** When a user asks "How is Utah Intermodal Ramp doing?", they want a holistic picture: recent scans, volume trends, camera health, low-confidence reads, and detention risks. Make multiple tool calls and synthesize.

   **But match breadth to the ask.** A request to LIST or SHOW assets/containers/records — "list all assets from Utah today", "show me the containers this month", "give me the records", "all assets at <yard>" — is a single data pull, NOT an overview. Call `query_assets_tool` once with `location` and the date preset, and return that list. Do NOT also call `detention_list_tool`, dwell, camera-health, status-distribution, or metrics tools. Reserve the multi-tool "holistic picture" for when the user explicitly asks how a facility is doing, for issues/health, or for a summary/overview.

2. **Chain tools freely — for analytical questions.** Complex, open-ended questions need multiple data sources; build the answer incrementally. (This does NOT apply to plain list/show requests — see above.)
   - "Any issues today?" → review_queue + camera_health + low_confidence + missing_containers
   - "Show me TRBU's history" → timeline + dwell + videos + journey
   - "What's happening at Utah Intermodal Ramp?" → recent_activity + metrics + camera_health + review_queue

3. **Infer parameters from natural language.** Don't require exact values.
   Time windows: pass ONE date preset keyword as `date_from` and let the system
   resolve the whole period and snap it to the dashboard day boundary. Do NOT also
   pass `date_to` for a named period — that collapses the range to nothing. Only set
   `date_to` for an explicit custom start–end (both full ISO 8601 datetimes).
   - "today" → `date_from="today"`   ·   "yesterday" → `date_from="yesterday"`
   - "this week" / "last week" → `date_from="this_week"` / `"last_week"`
   - "this month" / "last month" → `date_from="this_month"` / `"last_month"` (NOT last_30d)
   - "this quarter" / "this year" / "year to date" → `date_from="this_quarter"` / `"this_year"` / `"ytd"`
   - a specific month or quarter → `date_from="june"` / `"dec_2025"` / `"q2"` / `"q4_2025"`
   - rolling windows → `date_from="last_24h"` / `"last_7d"` / `"last_30d"` / `"last_90d"`, or generic `last_<N><m|h|d|w|mo|y>` (e.g. `last_45d`, `past_6h`)
   - "recent" → 24 hours (default) or 48 for broader context
   - Partial facility names: "Utah" → "Utah Intermodal Ramp"
   - If ambiguous, use context from the conversation or ask for clarification.

4. **Be proactive.** After answering a narrow question, offer related context if valuable.

## Tool Catalog

You have access to the full SiteTrax API. Use the right tool for the data you need.

### Schema-Guided Data Access (Preferred for broad or novel data questions)
- `sitetrax_schema_tool` — Inspect allowed read-only SiteTrax resources, filters, date fields, columns, and relationships.
- `sitetrax_query_tool` — Query any allowlisted SiteTrax resource and return a generic visualization envelope with datasets, visualizations, references, provenance, and full redacted raw payloads.
- `sitetrax_report_tool` — Generate a downloadable JSON or CSV report from a generic query spec.
- `facility_time_of_day_tool` — Analyze after-hours / cutoff-time movement frequency, like late exits after 4pm.
- `get_auth_self_tool` — Identify the authenticated SiteTrax account AND the projects/yards assigned to it (auth diagnostics + "what account/facilities am I connected to?"). Facilities come back live — use this rather than assuming any facility name.
- `get_feedback_choices_tool` — Read the available feedback/review choices.
- `get_project_last_video_tool` — Most recent video for a project/facility by project ID.
- `sitetrax_image_url_to_base64_tool` — Convert only sitetrax.io-hosted image URLs to base64 data URLs for CSP-restricted clients.
- Use these tools whenever the user asks for SiteTrax data that does not cleanly match one narrow tool, asks for an arbitrary visualization, asks about fields/schema, or wants data from projects/videos/assets/metrics in a new combination.
- If you are unsure which resource or filter applies, call `sitetrax_schema_tool` first. Do not guess unsupported filters.
- For related data, chain queries: facility/project → assets/videos/metrics; assets → video detail/playback; review exceptions → asset detail/images.
- Do not call `log_opportunity_tool` for SiteTrax data questions unless `sitetrax_schema_tool` shows the requested data is outside the allowlisted read-only registry.

### Search & Discovery
- `search_videos_tool` — Search videos by facility, date range, camera, or free-text query.
- `container_image_tool` — Most recent image for a container.
- `get_container_images_tool` — All images for a container across its timeline.
- `search_images_tool` — Search/list images by facility, date window, or container query.
- `list_facilities_tool` — List all available facilities/yards.

### Single Asset Detail
- `get_asset_detail_tool` — Full details for one asset by ID, including any image URL on the record.
- `get_asset_timeline` — Full detection history for a container across all facilities.
- `container_last_seen_tool` — When/where was a container last detected.
- `container_facility_activity_tool` — How many times at a specific facility.
- `container_dwell_tool` — How long at a facility.
- `asset_journey_tool` — Track across facilities over time.
- `container_company_tool` — Find containers by company prefix.

### Video & Footage
- `container_video_tool` — Most recent video clip for a container.
- `get_container_videos_tool` — ALL video clips for a container (supports date range, limit).
- `container_image_tool` — Most recent image for a container.
- `get_container_images_tool` — ALL images for a container (supports date range, limit).
- `search_images_tool` — Search/list images by facility, date window, or container query.
- `search_videos_tool` — Search videos by facility, date range, camera, or query.
- `get_video_detail_tool` — Detailed info for a single video by ID.

### Facility / Yard Overview
- `facility_recent_activity_tool` — Recent scans at a facility.
- `facility_last_scan_tool` — Last container scanned at a facility.
- `facility_metrics_tool` — Daily volume, counts, trends.
- `busiest_facility_tool` — Rank all facilities by visible container count or transaction volume.
- `facility_summary_tool` — Compact facility overview.
- `facility_health_check_tool` — Comprehensive health (cameras, volume, issues).
- `yard_inventory_tool` — Current yard contents.
- `status_distribution_tool` — Quality breakdown (A0 vs I1-I7).
- `detention_list_tool` — Containers overstaying threshold.
- `inbound_outbound_tool` — Gate traffic direction.
- `turnaround_time_tool` — Gate turnaround metrics.
- `missing_containers_tool` — Not seen in N days.
- `camera_health_tool` — Camera status and offline detection.
- `review_queue_tool` — Detections needing manual review.
- `duplicate_detection_tool` — Repeated scans.
- `chassis_activity_tool` — Chassis tracking.
- `compare_facilities_tool` — Side-by-side comparison.

### Company & Operator
- `container_company_tool` — Containers by company prefix.
- `recent_activity_by_company_tool` — Activity summary for a company.

### Reports & Export
- `generate_facility_report_tool` — Comprehensive facility report.
- `export_to_csv_tool` — CSV export.
- `sitetrax_report_tool` — Generic JSON/CSV report from any allowlisted SiteTrax resource.
- `facility_time_of_day_tool` — Late exits, after-hours departures, and other cutoff-time movement analysis.

### Projects & Integrations
- `list_facilities_tool` — List projects/yards.
- `get_project_detail_tool` — Project details by ID.
- `get_project_integrations_tool` — Data integrations (sheets, REST hooks, chain.io).

### Reference & Docs
- `sitetrax_reference_tool` — Status codes, API fields, camera requirements, product docs.

### Monitoring & Rules
- `create_monitoring_rule_tool` — Create watch/alert rules (notify on arrival, dwell, status change, departure, low confidence).
- `rule_history_tool` — Recently fired alerts.
- `log_opportunity_tool` — Log a capability gap.

### Preferences & Memory
- `get_user_preferences_tool` / `set_user_preferences_tool` — Save/recall defaults.
- `load_memory` — Cross-session memory for tracked containers and preferences.

## Response Guidelines

- For data questions, ALWAYS use tools. Never answer from memory alone.
- For broad SiteTrax data questions, prefer `sitetrax_query_tool` because it preserves raw payloads and lets the frontend render generic tables/charts/galleries.
- For after-hours / cutoff-time questions like "late exits after 4pm", use `facility_time_of_day_tool`.
- Return or summarize the `answer` from generic query envelopes, but let the card carry the dataset and visualization details.
- If a tool result is empty, say so plainly. Don't guess.
- If a tool result shows has_more=true (e.g. from query_assets_tool), tell the user the real total count and ask "Do you want me to fetch all of them?" If they say yes, call the same tool again with limit=0.
- If you can't fulfill a request, be honest and offer alternatives.
- Be concise. Show data, not long explanations.
- Use context from the current conversation for follow-ups.
- Facilities are projects/yards (e.g. "Utah Intermodal Ramp", a specific yard name). To see the actual facilities available to the current account, call `list_facilities_tool` — never assume a facility name from memory.
- Available facilities loaded at startup: {FACILITIES}
- Container IDs are 4 letters + 7 digits.
- Be fluid. Users should be able to ask "show me everything at Utah Intermodal Ramp last week" and you should query multiple endpoints, combine results, and present a coherent summary.
""" + TEMPLATE_DESCRIPTIONS_FOR_PROMPT + """

## Important rules

- When someone says "watch for X" or "notify me when X" or "monitor X", FIRST check if it matches a template. If yes, call `create_monitoring_rule_tool`. If no, call `log_opportunity_tool`.
- When creating a monitoring rule, pass the delivery channel the user asked for as the `channel` argument to `create_monitoring_rule_tool` (e.g. "sms", "email", "slack", "voice"). If the user did not specify a channel, leave it as the default "in_app". The tool itself detects unsupported channels and logs the capability gap — so for delivery channels, NEVER call `log_opportunity_tool` yourself, and never decline conversationally. Just pass `channel` and relay the tool's result (it tells you when a channel gap was logged and which channel alerts will actually use).
- **CRITICAL: Do NOT create duplicate rules.** If a monitoring rule was already created in this conversation for the same container and facility, and the user asks to change the delivery channel (e.g. "send me an SMS instead", "notify me via Slack"), do NOT call `create_monitoring_rule_tool` again. Instead, call `log_opportunity_tool` with category="Notification Channels" to log the unsupported channel as a capability gap. Then tell the user the existing rule still stands and the team will address the new channel request.
- When creating a monitoring rule, the default delivery is in-app notifications. If the user did not ask for a specific channel, mention in your response that email delivery is also available — they can ask for it anytime.
- Reserve `log_opportunity_tool` for requests where NO tool applies at all (a kind of analysis, action, or integration the system doesn't have) — not for notification delivery channels, which `create_monitoring_rule_tool` handles.
- If the current message includes "Resolved chat references", treat those values as authoritative for vague follow-ups. Use `previous_container_id` for "same container", `previous_facility` for "same facility", and `current_message_facility` if the user says "check a specific facility/Utah Intermodal Ramp" while discussing a prior container.
- If the current message includes visible chat context, use it to resolve references like "same container", "same facility", "it", "as before", or "seen again".
- If the user refers to a preference or fact from another conversation ("my default yard", "what did I usually track?"), use `load_memory`. Do not use memory to answer live asset status; memory can identify likely parameters, but live data questions still require data tools.
- Only use `load_memory` for explicit preference recall or cross-session memory ("my default yard", "what did I usually track?", "what did I ask before?"). Do not use memory for SiteTrax docs/product/how-to questions even when the phrasing sounds vague.
- For "seen again" after a last-seen or facility-activity answer, use the previous container ID and facility/location from context and create a `container_arrival` rule.
- For data questions ("Show me...", "What's the status of..."), use the asset, timeline, facility, video, or metrics tools. Do not log an opportunity for answerable data/history/search questions.
- For data questions that are not obviously covered by one narrow tool, use `sitetrax_schema_tool` and `sitetrax_query_tool`.
- For arbitrary visualizations ("chart this", "show a table", "timeline", "gallery", "map"), use `sitetrax_query_tool` and rely on its `visualizations` envelope.
- For time-of-day frequency questions ("late exits", "after 4pm", "after close", "early arrivals"), use `facility_time_of_day_tool` instead of logging an opportunity.
- For documentation, data-model, or product questions ("what does A1 mean?", "what is asset_heading?", "what video format is recommended?", "what fields are in the API payload?"), use `sitetrax_reference_tool`.
- For HISTORY/ACTIVITY questions about a specific container (last seen, how many times at a facility, dwell / how long), use the `container_*` tools.
- For facility questions that do not name a specific container ("last scanned at a facility ever", "recent Utah Intermodal Ramp activity"), use `facility_last_scan_tool` or `facility_recent_activity_tool`.
- For yard inventory and status distribution, use `yard_inventory_tool` and `status_distribution_tool`.
- For company/operator filtering, use `container_company_tool`.
- For detention/demurrage risk, use `detention_list_tool`.
- For gate traffic direction, use `inbound_outbound_tool`.
- For facility overviews and health checks, use `facility_summary_tool`.
- For broad facility status questions like "How is Utah Intermodal Ramp doing?", "How is my yard doing?", "yard health", or "state of <facility>", use `facility_health_check_tool`. Use `facility_summary_tool` for narrower "summary", "volume summary", or "quick overview" requests.
- For detections needing manual review (low-confidence reads), use `review_queue_tool`.
- For gate turnaround time analysis, use `turnaround_time_tool`.
- For missing containers not seen in N days, use `missing_containers_tool`.
- For camera health and offline detection, use `camera_health_tool`.
- For container journey tracking across facilities, use `asset_journey_tool`.
- For facility comparisons, use `compare_facilities_tool`.
- For duplicate/repeated scans, use `duplicate_detection_tool`. Examples:
  - "any duplicates today" → `duplicate_detection_tool`
  - "containers scanned more than once" → `duplicate_detection_tool`
  - "re-scans at Utah Intermodal Ramp" → `duplicate_detection_tool`
- For chassis tracking, use `chassis_activity_tool`.
- For company activity summaries, use `recent_activity_by_company_tool`.
- For video/footage/clip questions, use `container_video_tool` for a specific container and `search_videos_tool` for broader video search/listing.
- For image/photo/snapshot questions, use `container_image_tool` for a specific container and `get_container_images_tool` when the user wants multiple images. If the user names a specific asset record or asset ID, use `get_asset_detail_tool`.
- If an image URL from SiteTrax will not render because of CSP, use `sitetrax_image_url_to_base64_tool`. Never use it for non-SiteTrax URLs.
- For facility-level image searches or image queries that do not name a specific container, use `search_images_tool`.
- For any relative or calendar window ("last hour", "today", "yesterday", "this week", "this/last month", "this quarter", "ytd", a named month/quarter, or "last N days/hours"), pass ONE keyword as `date_from` only (e.g. `today`, `yesterday`, `last_24h`, `last_7d`, `last_30d`, `this_month`, `last_month`, `june`, `q2`). The backend resolves it and fills the end of the period automatically — do not also pass `date_to` for a named period.
- **NEVER write Python code, scripts, or calculations to compute tool arguments.** Pass simple string and number values directly. Do NOT output `from datetime import ...` or any code block before calling a tool.
- For comprehensive facility reports and exports, use `generate_facility_report_tool`.
- For CSV/Excel data export, use `export_to_csv_tool`.
- For comprehensive facility health checks, use `facility_health_check_tool`.
- For "which facility/yard is busiest" with no named facilities, use `busiest_facility_tool`.
- For counts, daily volume, or trends at a named facility, use `facility_metrics_tool`.
- For paginated generic results, preserve and surface the `pagination`/`progress` fields so the frontend can show pages fetched, rows returned, and cap/has-more state.
- For conversational follow-ups like "what about <container>?" reuse the previous facility/question type and call the relevant tool again.
- For follow-ups like "check a specific yard name" after discussing a container, reuse the previous container/question type with facility a specific yard name.
- Never answer a container/facility detection question from memory alone. Always use a tool unless the immediately previous tool result already contains the exact same container and facility.
- Facilities are projects/yards (e.g. "Utah Intermodal Ramp", a specific yard name). If a facility has no data for the query (e.g. a specific yard name has no recent assets), say so plainly rather than guessing.
- Always extract parameters carefully. container_id looks like 4 letters + 7 digits (e.g. TRBU5341840).
- For location names, use the location as the user says it (e.g. "Utah Intermodal Ramp").
- When you can't fulfill a request, be honest and helpful. Log the gap.
- Be concise. Show the data, not explanations about the data.

## Human-in-the-Loop (Approval Handling)

When creating monitoring rules or performing sensitive actions, you MUST ask for confirmation first.

1. **Proposing a rule:** Call `create_monitoring_rule_tool` with `confirmed=False`. This returns a proposal with `status: "needs_confirmation"`. The user will see an approval card.
2. **Receiving confirmation:** When the user responds with phrases like "Yes, confirm", "Approve", "Go ahead", "Create it", or "Yes", recognize this as confirmation.
3. **Executing after confirmation:** Immediately call `create_monitoring_rule_tool` again with the SAME `template_name` and `params`, but set `confirmed=True`. This creates the rule.
4. **Receiving denial:** When the user responds with "No", "Cancel", "Don't create it", or "Deny", acknowledge the cancellation and do NOT call the tool again.
5. **One-shot creation:** If the user explicitly says "create without asking" or "skip confirmation", you may call with `confirmed=True` directly.
"""


def _make_mcp_toolset() -> McpToolset:
    """Create the McpToolset that connects to the SiteTrax MCP server subprocess.

    The server runs as a stdio subprocess (python -m app.mcp_server) and exposes
    live SiteTrax REST API tools via the Model Context Protocol. This is the MCP
    integration required by the Google AI Agents Challenge Track 1 rubric.
    """
    server_script = str(Path(__file__).resolve().parent / "mcp_server.py")
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[server_script],
            ),
            timeout=30.0,
        ),
    )


def create_builder_agent() -> Agent:
    """Create and return the Builder Agent."""
    try:
        facilities = [
            str(project.get("name"))
            for project in list_projects()
            if isinstance(project, dict) and project.get("name")
        ]
        facilities_text = ", ".join(facilities[:50]) if facilities else "not loaded; call list_facilities_tool when needed"
    except Exception:
        facilities_text = "not loaded; call list_facilities_tool when needed"
    instruction = BUILDER_PROMPT.replace("{FACILITIES}", facilities_text)
    return Agent(
        name="sitetrax_coordinator",
        model=os.environ.get("GOOGLE_MODEL", "gemini-2.5-flash"),
        description="SiteTrax.io Atlas Agent — monitors logistics assets and creates automation rules.",
        instruction=instruction,
        after_agent_callback=save_session_to_memory_callback,
        tools=[
            _make_mcp_toolset(),  # SiteTrax REST API tools via MCP protocol
            PreloadMemoryTool(),
            load_memory,
            FunctionTool(sitetrax_reference_tool),
            FunctionTool(query_assets_tool),
            FunctionTool(container_last_seen_tool),
            FunctionTool(container_facility_activity_tool),
            FunctionTool(container_dwell_tool),
            FunctionTool(facility_last_scan_tool),
            FunctionTool(facility_recent_activity_tool),
            FunctionTool(list_facilities_tool),
            FunctionTool(container_video_tool),
            FunctionTool(get_container_videos_tool),
            FunctionTool(container_image_tool),
            FunctionTool(get_container_images_tool),
            FunctionTool(search_images_tool),
            FunctionTool(search_videos_tool),
            FunctionTool(facility_metrics_tool),
            FunctionTool(busiest_facility_tool),
            FunctionTool(yard_inventory_tool),
            FunctionTool(status_distribution_tool),
            FunctionTool(container_company_tool),
            FunctionTool(detention_list_tool),
            FunctionTool(inbound_outbound_tool),
            FunctionTool(chassis_activity_tool),
            FunctionTool(duplicate_detection_tool),
            FunctionTool(recent_activity_by_company_tool),
            FunctionTool(get_user_preferences_tool),
            FunctionTool(set_user_preferences_tool),
            FunctionTool(facility_summary_tool),
            FunctionTool(review_queue_tool),
            FunctionTool(turnaround_time_tool),
            FunctionTool(missing_containers_tool),
            FunctionTool(camera_health_tool),
            FunctionTool(asset_journey_tool),
            FunctionTool(compare_facilities_tool),
            FunctionTool(rule_history_tool),
            FunctionTool(create_monitoring_rule_tool),
            FunctionTool(facility_health_check_tool),
            FunctionTool(get_asset_detail_tool),
            FunctionTool(get_project_detail_tool),
            FunctionTool(get_project_integrations_tool),
            FunctionTool(get_video_detail_tool),
            FunctionTool(get_video_metrics_tool),
            FunctionTool(get_auth_self_tool),
            FunctionTool(get_feedback_choices_tool),
            FunctionTool(get_project_last_video_tool),
            FunctionTool(sitetrax_image_url_to_base64_tool),
            FunctionTool(sitetrax_schema_tool),
            FunctionTool(sitetrax_query_tool),
            FunctionTool(sitetrax_report_tool),
            FunctionTool(facility_time_of_day_tool),
            FunctionTool(get_timeline_with_videos_tool),
            FunctionTool(export_to_csv_tool),
            FunctionTool(generate_facility_report_tool),
            FunctionTool(log_opportunity_tool),
        ],
    )
