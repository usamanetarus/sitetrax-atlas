"""SiteTrax MCP Server — exposes live SiteTrax REST API tools via the Model Context Protocol.

Run as a stdio subprocess (launched automatically by the ADK agent's McpToolset):
    python -m app.mcp_server

Or start directly for testing:
    cd backend && python -m app.mcp_server
"""

from __future__ import annotations

# ── Path bootstrap ─────────────────────────────────────────────────────────────
# When launched as a subprocess (python /path/to/app/mcp_server.py), Python adds
# the *script's directory* (app/) to sys.path, not the backend root. We need the
# backend root so `from app.data import ...` resolves correctly.
import sys
from pathlib import Path as _Path
_backend_root = str(_Path(__file__).resolve().parents[1])
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

# Load .env before any app.* imports so USE_REAL_API / SITETRAX_* vars are available
# in the subprocess environment (subprocess inherits parent env, but this also covers
# direct invocation and local dev where the parent hasn't loaded .env yet).
from dotenv import load_dotenv
load_dotenv(_Path(__file__).resolve().parents[1] / ".env")

import json
import logging

from mcp.server.fastmcp import FastMCP

from app.data import query_assets, get_latest_scan, get_asset_timeline
from app.data.sitetrax_client import (
    get_facility_last_scan,
    facility_metrics,
    get_sitetrax_schema,
    sitetrax_query,
    get_auth_self,
    get_feedback_choices,
    get_project_last_video,
    sitetrax_image_url_to_base64,
    SiteTraxAuthError,
    list_projects,
    get_facility_recent,
    get_container_video,
    get_container_videos,
    get_container_image,
    get_container_images,
    get_video_url,
    get_video_metrics,
    project_metrics,
    asset_metrics,
    facility_overview,
    query_assets_with_pagination,
    search_videos,
    get_asset_detail,
    get_project_detail,
    get_project_integrations,
    get_video_detail,
    export_assets,
    resolve_buckets,
)
from app.knowledge import search_reference

logger = logging.getLogger("sitetrax.mcp")

mcp = FastMCP(
    "SiteTrax",
    instructions=(
        "SiteTrax logistics platform tools. Use these to query live container/asset data, "
        "facility scan history, daily metrics, video playback, and SiteTrax product documentation."
    ),
)


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _columns_for_rows(rows: list[dict]) -> list[dict]:
    preferred = [
        ("text", "Container"),
        ("container_id", "Container"),
        ("facility", "Facility"),
        ("location", "Location"),
        ("status_code", "Status"),
        ("heading", "Heading"),
        ("asset_heading", "Heading"),
        ("created_at", "Detected at"),
        ("datetime", "Detected at"),
        ("id", "ID"),
    ]
    keys = []
    for row in rows[:10]:
        if isinstance(row, dict):
            keys.extend(row.keys())
    seen = set()
    columns = []
    for key, label in preferred:
        if key in keys and key not in seen:
            columns.append({"key": key, "label": label})
            seen.add(key)
    for key in keys:
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


def _timeline_envelope(container_id: str, entries: list[dict]) -> dict:
    return {
        "title": f"Timeline for {container_id.upper()}",
        "answer": f"Found {len(entries)} timeline record(s) for {container_id.upper()}.",
        "container_id": container_id,
        "count": len(entries),
        "timeline": entries,
        "datasets": [{
            "name": "asset_timeline",
            "label": f"Timeline for {container_id.upper()}",
            "entity_type": "asset",
            "columns": _columns_for_rows(entries),
            "rows": entries,
            "count": len(entries),
        }],
        "visualizations": [
            {"type": "timeline", "dataset": "asset_timeline", "title": "Detection timeline"},
            {"type": "image_gallery", "dataset": "asset_timeline", "title": "Detection images"},
            {"type": "table", "dataset": "asset_timeline", "title": "Timeline records"},
        ],
        "provenance": {
            "resource": "asset_timeline",
            "returned": len(entries),
            "tool": "sitetrax_asset_timeline",
        },
    }


# ── Existing tools ──────────────────────────────────────────────────────────────

@mcp.tool()
def sitetrax_schema(resource: str = "") -> str:
    """Inspect the read-only SiteTrax endpoint registry.

    Args:
        resource: Optional resource name. Leave empty to list all resources.
    """
    try:
        return json.dumps(get_sitetrax_schema(resource or None), default=str)
    except Exception as e:
        return json.dumps({"error": "schema_lookup_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_query_data(
    resource: str,
    filters_json: str = "",
    search: str = "",
    date_from: str = "",
    date_to: str = "",
    ordering: str = "",
    limit: int = 50,
    include_related: str = "",
) -> str:
    """Query any allowlisted read-only SiteTrax resource and return a visualization envelope.

    Args:
        resource: Allowed resource from sitetrax_schema, such as assets, videos, asset_metrics, projects.
        filters_json: JSON object string for filters, e.g. {"facility":"Utah Intermodal Ramp"}.
        search: Optional free-text search.
        date_from: Optional ISO 8601 start datetime.
        date_to: Optional ISO 8601 end datetime.
        ordering: Optional ordering, e.g. -created_at.
        limit: Maximum rows, capped server-side.
        include_related: Optional comma-separated relationships, e.g. playback_url,video_detail.
    """
    try:
        return json.dumps(sitetrax_query(
            resource=resource,
            filters=filters_json or None,
            search=search or None,
            date_from=date_from or None,
            date_to=date_to or None,
            ordering=ordering or None,
            limit=limit,
            include_related=include_related or None,
        ), default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_query_data failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_image_url_to_base64_data(image_url: str, max_bytes: int = 5000000) -> str:
    """Convert a SiteTrax-hosted image URL to a base64 data URL for CSP-restricted clients.

    Only HTTPS URLs hosted by sitetrax.io or *.sitetrax.io are accepted.

    Args:
        image_url: SiteTrax image URL.
        max_bytes: Maximum image size to fetch, default 5 MB.
    """
    try:
        return json.dumps(sitetrax_image_url_to_base64(image_url, max_bytes=max_bytes), default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        return json.dumps({"error": "image_base64_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_auth_self() -> str:
    """Get the authenticated SiteTrax user/account profile for auth diagnostics."""
    try:
        return json.dumps(get_auth_self(), default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_feedback_choices() -> str:
    """List read-only feedback/review choices."""
    try:
        return json.dumps({"choices": get_feedback_choices()}, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_project_last_video(project_id: str) -> str:
    """Get the most recent video for a project/facility by project ID.

    Args:
        project_id: SiteTrax project/facility ID.
    """
    try:
        return json.dumps(get_project_last_video(project_id) or {"found": False, "project_id": project_id}, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_search_assets(
    container_id: str = "",
    location: str = "",
    status_code: str = "",
    date_from: str = "",
    date_to: str = "",
) -> str:
    """Search live SiteTrax asset/container records (first 50, no pagination metadata).

    Use to find containers by ID, filter by yard location, or filter by status code
    (A0=confident, A1=interpolated, I1-I7=issues). Returns up to 50 matching records
    with timestamps, status, and GPS coordinates.

    Args:
        container_id: Container or asset ID to search for (e.g. TRDU1930583).
        location: Facility/yard name to filter by (e.g. "Utah Intermodal Ramp").
        status_code: Status code filter (e.g. "A0", "I1").
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601, maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601, maps to created_at__lte).
    """
    try:
        records = query_assets(
            container_id=container_id or None,
            location=location or None,
            status_code=status_code or None,
            date_from=date_from or None,
            date_to=date_to or None,
        )
        return json.dumps({"count": len(records), "assets": records[:50]}, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_search_assets failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_latest_scan(container_id: str) -> str:
    """Get the most recent scan/detection for a specific container.

    Returns the latest asset record including location, timestamp, status code,
    GPS coordinates, and video reference.

    Args:
        container_id: The container ID to look up (e.g. TRDU1930583).
    """
    try:
        record = get_latest_scan(container_id)
        return json.dumps(record or {"found": False, "container_id": container_id}, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_latest_scan failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_asset_timeline(container_id: str, limit: int = 20) -> str:
    """Retrieve the full detection timeline for a container across all facilities.

    Returns a chronological list of every time the container was scanned — including
    which facility, what time, what status, and what camera detected it.

    Args:
        container_id: Container ID to look up (e.g. TRDU1930583).
        limit: Maximum number of timeline entries to return (default 20).
    """
    try:
        timeline = get_asset_timeline(container_id)
        entries = timeline[:limit] if isinstance(timeline, list) else []
        return json.dumps(_timeline_envelope(container_id, entries), default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_asset_timeline failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_facility_last_scan(facility: str) -> str:
    """Get the most recent container scanned at a specific facility.

    Useful for checking whether a yard is active and what was last detected there.

    Args:
        facility: Facility name to look up (e.g. "Utah Intermodal Ramp", or another live project name).
    """
    try:
        record = get_facility_last_scan(facility)
        return json.dumps(record or {"found": False, "facility": facility}, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_facility_last_scan failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_facility_metrics(facility: str = "", date_from: str = "", date_to: str = "") -> str:
    """Get daily scan volume metrics for a facility or across all facilities.

    Returns a day-by-day breakdown of container detections, useful for spotting
    trends, traffic spikes, or idle periods.

    Args:
        facility: Facility name to filter by. Leave empty for all facilities.
        date_from: Optional start datetime in the SiteTrax API format (ISO 8601, maps to created_at__gte).
        date_to: Optional end datetime in the SiteTrax API format (ISO 8601, maps to created_at__lte).
    """
    try:
        result = facility_metrics(facility=facility or None, date_from=date_from or None, date_to=date_to or None)
        return json.dumps(result, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_facility_metrics failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_reference_lookup(query: str, limit: int = 3) -> str:
    """Search the SiteTrax product documentation and knowledge base.

    Use for conceptual questions: what SiteTrax does, API payload fields, status codes,
    asset headings, camera/video processing, integrations (Zapier, Chain.io), compliance
    (CTPAT, EPA/WAIRE), pricing model, capture modes (Snap/Drive/Mobile/Virtual Gate).

    Do NOT use for live asset status — use the data tools for that.

    Args:
        query: The product/docs question to look up.
        limit: Maximum number of reference sections to return (default 3).
    """
    matches = search_reference(query, limit=limit)
    return json.dumps({"query": query, "matches": matches}, default=str)


# ── NEW: Discovery / pagination / metrics / video / image tools ────────────────

@mcp.tool()
def sitetrax_list_projects(search: str = "", full_detail: bool = False) -> str:
    """List SiteTrax projects/facilities.

    Use this to discover available facility names before querying data.

    Args:
        search: Optional free-text search to filter project names.
        full_detail: If True, returns full project records; otherwise lightweight names.
    """
    try:
        projects = list_projects(search=search or None, full_detail=full_detail)
        return json.dumps({
            "count": len(projects),
            "projects": projects,
        }, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_list_projects failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_search_assets_paginated(
    container_id: str = "",
    location: str = "",
    status_code: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 250,
) -> str:
    """Search SiteTrax assets with pagination metadata (total count, has_more).

    Use when you need the real total count or cap-reached signal.
    If has_more is true, ask the user whether to fetch all records.

    Args:
        container_id: Container or asset ID to search for.
        location: Facility/yard name to filter by.
        status_code: Status code filter (e.g. "A0", "I1").
        date_from: Optional start datetime (ISO 8601, maps to created_at__gte).
        date_to: Optional end datetime (ISO 8601, maps to created_at__lte).
        limit: Maximum rows to fetch (default 250). Pass 0 or a very large number to fetch all.
    """
    try:
        envelope = query_assets_with_pagination(
            container_id=container_id or None,
            location=location or None,
            status_code=status_code or None,
            date_from=date_from or None,
            date_to=date_to or None,
            limit=(None if limit <= 0 else limit),
        )
        assets = envelope.get("assets", [])
        pagination = envelope.get("pagination", {})
        total = pagination.get("total_available")
        has_more = pagination.get("has_more", False)
        cap = pagination.get("cap_reached", False)
        answer = f"Found {total} matching asset record(s). Showing {len(assets)}."
        if has_more or cap:
            answer += " More records are available. Ask the user if they want all records fetched."
        return json.dumps({
            "answer": answer,
            "assets": assets,
            "pagination": pagination,
        }, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_search_assets_paginated failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_fetch_all_assets(
    container_id: str = "",
    location: str = "",
    status_code: str = "",
    date_from: str = "",
    date_to: str = "",
) -> str:
    """Fetch ALL matching SiteTrax asset records across all pages.

    WARNING: This may take time for large result sets. Use only when the user
    explicitly asks for all records.

    Args:
        container_id: Container or asset ID to search for.
        location: Facility/yard name to filter by.
        status_code: Status code filter (e.g. "A0", "I1").
        date_from: Optional start datetime (ISO 8601, maps to created_at__gte).
        date_to: Optional end datetime (ISO 8601, maps to created_at__lte).
    """
    try:
        envelope = query_assets_with_pagination(
            container_id=container_id or None,
            location=location or None,
            status_code=status_code or None,
            date_from=date_from or None,
            date_to=date_to or None,
            limit=None,
        )
        assets = envelope.get("assets", [])
        pagination = envelope.get("pagination", {})
        return json.dumps({
            "answer": f"Fetched all {len(assets)} matching asset record(s).",
            "assets": assets,
            "pagination": pagination,
        }, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_fetch_all_assets failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_facility_recent(facility: str, date_from: str = "", date_to: str = "", hours_back: int = 0) -> str:
    """Get recent asset detections at a specific facility.

    Args:
        facility: Facility name (e.g. "Utah Intermodal Ramp").
        date_from: Optional start datetime (ISO 8601, maps to created_at__gte).
        date_to: Optional end datetime (ISO 8601, maps to created_at__lte).
        hours_back: If >0, overrides date_from to fetch the last N hours.
    """
    try:
        records = get_facility_recent(
            facility=facility,
            date_from=date_from or None,
            date_to=date_to or None,
            hours_back=(hours_back if hours_back > 0 else None),
        )
        return json.dumps({
            "facility": facility,
            "count": len(records),
            "assets": records,
        }, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_facility_recent failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_container_video(container_id: str, date_from: str = "", date_to: str = "", hours_back: int = 0) -> str:
    """Get the most recent video clip for a specific container.

    Args:
        container_id: Container ID (e.g. TRDU1930583).
        date_from: Optional start datetime (ISO 8601).
        date_to: Optional end datetime (ISO 8601).
        hours_back: If >0, overrides date_from to search within the last N hours.
    """
    try:
        video = get_container_video(
            container_id,
            date_from=date_from or None,
            date_to=date_to or None,
            hours_back=(hours_back if hours_back > 0 else None),
        )
        return json.dumps(video or {"found": False, "container_id": container_id}, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_container_video failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_container_videos(container_id: str, limit: int = 10, date_from: str = "", date_to: str = "", hours_back: int = 0) -> str:
    """Get all video clips for a specific container.

    Args:
        container_id: Container ID (e.g. TRDU1930583).
        limit: Maximum videos to return (default 10).
        date_from: Optional start datetime (ISO 8601).
        date_to: Optional end datetime (ISO 8601).
        hours_back: If >0, overrides date_from to search within the last N hours.
    """
    try:
        videos = get_container_videos(
            container_id,
            limit=limit,
            date_from=date_from or None,
            date_to=date_to or None,
            hours_back=(hours_back if hours_back > 0 else None),
        )
        return json.dumps({
            "container_id": container_id,
            "count": len(videos),
            "videos": videos,
        }, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_container_videos failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_container_image(container_id: str, date_from: str = "", date_to: str = "", hours_back: int = 0) -> str:
    """Get the most recent detection image for a specific container.

    Args:
        container_id: Container ID (e.g. TRDU1930583).
        date_from: Optional start datetime (ISO 8601).
        date_to: Optional end datetime (ISO 8601).
        hours_back: If >0, overrides date_from to search within the last N hours.
    """
    try:
        image = get_container_image(
            container_id,
            date_from=date_from or None,
            date_to=date_to or None,
            hours_back=(hours_back if hours_back > 0 else None),
        )
        return json.dumps(image or {"found": False, "container_id": container_id}, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_container_image failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_container_images(container_id: str, limit: int = 10, date_from: str = "", date_to: str = "", hours_back: int = 0) -> str:
    """Get all detection images for a specific container.

    Args:
        container_id: Container ID (e.g. TRDU1930583).
        limit: Maximum images to return (default 10).
        date_from: Optional start datetime (ISO 8601).
        date_to: Optional end datetime (ISO 8601).
        hours_back: If >0, overrides date_from to search within the last N hours.
    """
    try:
        images = get_container_images(
            container_id,
            limit=limit,
            date_from=date_from or None,
            date_to=date_to or None,
            hours_back=(hours_back if hours_back > 0 else None),
        )
        return json.dumps({
            "container_id": container_id,
            "count": len(images),
            "images": images,
        }, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_container_images failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_container_image_base64(container_id: str, max_bytes: int = 5000000, hours_back: int = 0) -> str:
    """Get the most recent detection image for a container as a base64 data URL.

    Useful when the client cannot directly display external image URLs.

    Args:
        container_id: Container ID (e.g. TRDU1930583).
        max_bytes: Maximum image size to fetch, default 5 MB.
        hours_back: If >0, search within the last N hours.
    """
    try:
        image = get_container_image(
            container_id,
            hours_back=(hours_back if hours_back > 0 else None),
        )
        if not image or not image.get("image_url"):
            return json.dumps({"found": False, "container_id": container_id}, default=str)
        b64 = sitetrax_image_url_to_base64(image["image_url"], max_bytes=max_bytes)
        return json.dumps({
            "container_id": container_id,
            "image": b64,
            "detected_at": image.get("detected_at"),
            "facility": image.get("facility"),
            "status_code": image.get("status_code"),
        }, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_container_image_base64 failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_search_videos(
    facility: str = "",
    container_id: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
) -> str:
    """Search SiteTrax video records.

    Args:
        facility: Facility name to filter by.
        container_id: Container ID to filter by.
        date_from: Optional start datetime (ISO 8601, maps to created_at__gte).
        date_to: Optional end datetime (ISO 8601, maps to created_at__lte).
        limit: Maximum rows to return (default 50).
    """
    try:
        videos = search_videos(
            facility=facility or None,
            container_id=container_id or None,
            date_from=date_from or None,
            date_to=date_to or None,
            limit=limit,
        )
        return json.dumps({
            "count": len(videos),
            "videos": videos,
        }, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_search_videos failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_video_metrics(facility: str = "", date_from: str = "", date_to: str = "") -> str:
    """Get aggregated video metrics for a facility or across all facilities.

    Args:
        facility: Facility name to filter by. Leave empty for all facilities.
        date_from: Optional start datetime (ISO 8601, maps to created_at__gte).
        date_to: Optional end datetime (ISO 8601, maps to created_at__lte).
    """
    try:
        result = get_video_metrics(
            facility=facility or None,
            date_from=date_from or None,
            date_to=date_to or None,
        )
        return json.dumps(result, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_video_metrics failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_project_metrics(date_from: str = "", date_to: str = "", days: int = 0) -> str:
    """Get per-facility daily project metrics across all facilities.

    Args:
        date_from: Optional start datetime (ISO 8601, maps to created_at__gte).
        date_to: Optional end datetime (ISO 8601, maps to created_at__lte).
        days: If >0, overrides date range to the last N days.
    """
    try:
        result = project_metrics(
            date_from=date_from or None,
            date_to=date_to or None,
            days=(days if days > 0 else None),
        )
        return json.dumps({"count": len(result), "metrics": result}, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_project_metrics failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_asset_metrics(facility: str = "", date_from: str = "", date_to: str = "") -> str:
    """Get aggregated asset metrics for a facility or across all facilities.

    Args:
        facility: Facility name to filter by. Leave empty for all facilities.
        date_from: Optional start datetime (ISO 8601, maps to created_at__gte).
        date_to: Optional end datetime (ISO 8601, maps to created_at__lte).
    """
    try:
        import datetime as _dt
        since = _dt.datetime.fromisoformat(date_from) if date_from else None
        until = _dt.datetime.fromisoformat(date_to) if date_to else None
        bucket_ids = resolve_buckets(facility) if facility else None
        result = asset_metrics(
            bucket_ids=bucket_ids,
            since=since,
            until=until,
        )
        return json.dumps(result, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_asset_metrics failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_facility_overview(facility: str, date_from: str = "", date_to: str = "", days: int = 0) -> str:
    """Get a holistic facility snapshot: metrics, recent activity, last scan, video metrics.

    Args:
        facility: Facility name (e.g. "Utah Intermodal Ramp").
        date_from: Optional start datetime (ISO 8601).
        date_to: Optional end datetime (ISO 8601).
        days: If >0, overrides date range to the last N days.
    """
    try:
        result = facility_overview(
            facility=facility,
            date_from=date_from or None,
            date_to=date_to or None,
            days=(days if days > 0 else None),
        )
        return json.dumps(result, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_facility_overview failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_asset_detail(asset_id: str) -> str:
    """Get full detail for a specific asset by its ID.

    Args:
        asset_id: SiteTrax asset ID.
    """
    try:
        detail = get_asset_detail(asset_id)
        return json.dumps(detail or {"found": False, "asset_id": asset_id}, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_asset_detail failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_project_detail(project_id: str) -> str:
    """Get full detail for a specific project/facility by its ID.

    Args:
        project_id: SiteTrax project ID.
    """
    try:
        detail = get_project_detail(project_id)
        return json.dumps(detail or {"found": False, "project_id": project_id}, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_project_detail failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_project_integrations(project_id: str) -> str:
    """Get integrations configured for a specific project/facility.

    Args:
        project_id: SiteTrax project ID.
    """
    try:
        detail = get_project_integrations(project_id)
        return json.dumps(detail or {"found": False, "project_id": project_id}, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_project_integrations failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_video_detail(video_id: str) -> str:
    """Get full detail for a specific video by its ID.

    Args:
        video_id: SiteTrax video ID.
    """
    try:
        detail = get_video_detail(video_id)
        return json.dumps(detail or {"found": False, "video_id": video_id}, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_video_detail failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


@mcp.tool()
def sitetrax_export_assets(
    container_id: str = "",
    location: str = "",
    status_code: str = "",
    date_from: str = "",
    date_to: str = "",
    format: str = "json",
) -> str:
    """Export matching SiteTrax asset records as JSON or CSV.

    Args:
        container_id: Container or asset ID to search for.
        location: Facility/yard name to filter by.
        status_code: Status code filter (e.g. "A0", "I1").
        date_from: Optional start datetime (ISO 8601, maps to created_at__gte).
        date_to: Optional end datetime (ISO 8601, maps to created_at__lte).
        format: Export format — "json" or "csv" (default "json").
    """
    try:
        result = export_assets(
            container_id=container_id or None,
            location=location or None,
            status_code=status_code or None,
            date_from=date_from or None,
            date_to=date_to or None,
            fmt=format,
        )
        return json.dumps(result, default=str)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_export_assets failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})


# ── NEW: Composite analysis tools ───────────────────────────────────────────────

@mcp.tool()
def sitetrax_review_queue(
    facility: str = "",
    date_from: str = "",
    date_to: str = "",
    status_codes: str = "",
) -> str:
    """Find detections that need manual review (non-A0 status codes like I1-I7, A1).

    Use for "what needs review", "low confidence scans", "detections to verify",
    "which containers had bad reads".

    Args:
        facility: Optional facility to filter by.
        date_from: Optional start datetime (ISO 8601, maps to created_at__gte).
        date_to: Optional end datetime (ISO 8601, maps to created_at__lte).
        status_codes: Comma-separated status codes to filter (e.g. "I1,I2,I3"). Default is all non-A0 codes.
    """
    try:
        results = query_assets(
            location=facility or None,
            date_from=date_from or None,
            date_to=date_to or None,
        )
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_review_queue failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})

    if not results:
        scope = f" at {facility}" if facility else ""
        return json.dumps({"answer": f"No detections found{scope}.", "items": []}, default=str)

    if status_codes:
        target_codes = {s.strip().upper() for s in status_codes.split(",")}
        review_items = [r for r in results if (r.get("status_code") or "A0") in target_codes]
    else:
        review_items = [r for r in results if (r.get("status_code") or "A0") != "A0"]

    if not review_items:
        return json.dumps({
            "answer": f"All {len(results)} detections have A0 (confident) status. Nothing needs review.",
            "total_detections": len(results),
            "needs_review_count": 0,
            "items": [],
        }, default=str)

    by_code = {}
    for r in review_items:
        sc = r.get("status_code") or "unknown"
        by_code.setdefault(sc, []).append(r)

    summary = {sc: len(items) for sc, items in by_code.items()}
    review_rate = round(len(review_items) / len(results) * 100, 1) if results else 0
    a0_rate = round(100 - review_rate, 1) if results else 0

    return json.dumps({
        "facility": facility or "all",
        "total_detections": len(results),
        "needs_review_count": len(review_items),
        "review_rate_percent": review_rate,
        "a0_rate_percent": a0_rate,
        "by_status_code": summary,
        "items": review_items[:25],
    }, default=str)


@mcp.tool()
def sitetrax_camera_health(
    facility: str = "",
    date_from: str = "",
    date_to: str = "",
) -> str:
    """Check camera health by comparing recent detection counts per camera.

    Use for "is camera X working", "camera status", "which cameras are offline",
    "detection counts by camera".

    Args:
        facility: Optional facility to filter by.
        date_from: Optional start datetime (ISO 8601, maps to created_at__gte).
        date_to: Optional end datetime (ISO 8601, maps to created_at__lte).
    """
    try:
        results = query_assets(
            location=facility or None,
            date_from=date_from or None,
            date_to=date_to or None,
        )
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_camera_health failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})

    if not results:
        scope = f" at {facility}" if facility else ""
        return json.dumps({"answer": f"No detections found{scope}.", "cameras": []}, default=str)

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
        "total_detections": len(results),
        "camera_count": len(camera_stats),
        "cameras": camera_stats[:30],
        "low_activity_cameras": low_activity,
    }, default=str)


@mcp.tool()
def sitetrax_status_distribution(
    facility: str = "",
    date_from: str = "",
    date_to: str = "",
) -> str:
    """Show the breakdown of status codes (A0, A1, I1-I7) for detections.

    Use for "what's the read quality at Utah Intermodal Ramp", "how many low-confidence scans",
    "status breakdown".

    Args:
        facility: Optional facility name. Omit for all facilities.
        date_from: Optional start datetime (ISO 8601, maps to created_at__gte).
        date_to: Optional end datetime (ISO 8601, maps to created_at__lte).
    """
    try:
        if facility:
            results = get_facility_recent(facility, date_from=date_from or None, date_to=date_to or None)
        else:
            results = query_assets(date_from=date_from or None, date_to=date_to or None)
    except SiteTraxAuthError as e:
        return json.dumps({"error": "auth_error", "detail": str(e)})
    except Exception as e:
        logger.exception("sitetrax_status_distribution failed")
        return json.dumps({"error": "query_failed", "detail": str(e)})

    if not results:
        scope = f" at {facility}" if facility else ""
        return json.dumps({"answer": f"No assets found{scope}.", "by_status": {}}, default=str)

    counts = {}
    for r in results:
        sc = r.get("status_code") or "unknown"
        counts[sc] = counts.get(sc, 0) + 1

    return json.dumps({
        "facility": facility or "all facilities",
        "total": len(results),
        "by_status": counts,
    }, default=str)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
