"""SiteTrax.io real REST API client — drop-in replacement for mock_data.py.

Read-only endpoints only. Uses JWT auth with automatic refresh:
  - access token from SITETRAX_ACCESS_TOKEN
  - on HTTP 401, POST {base}/auth/token/refresh/ with {"refresh": SITETRAX_REFRESH_TOKEN}
    -> {"access": "<new token>"} (SimpleJWT, no rotation), then retry once.

Time formats (live API):
  - `datetime`   -> UTC ISO8601 with `Z` (e.g. 2026-06-02T21:26:37.129035Z)  ← we use this
  - `scanned_at` / `created_at` -> ISO8601 with a tz offset (e.g. ...-04:00)
  - Date FILTERS (`created_at__gte/__lte`) are snapped to the dashboard
    business-day boundary by `_snap_date_filters` and sent as
    `YYYY-MM-DD 20:00:00` (UTC, space-separated). The hour is always 20:00:00 so
    the agent's date ranges line up with the dashboards. See that function.
"""

import datetime
import base64
import json
import logging
import os
import random
import re
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from . import mock_data

logger = logging.getLogger("sitetrax")

_API_BASE = os.getenv("SITETRAX_API_BASE", "").rstrip("/")
_REFRESH_PATH = os.getenv("SITETRAX_REFRESH_PATH", "/auth/token/refresh/")
_TIMEOUT = 20.0
_REFRESH_SKEW_SECONDS = int(os.getenv("SITETRAX_REFRESH_SKEW_SECONDS", "60"))

# Access token is refreshed in place; refresh token is long-lived and read per-call.
_access_token = os.getenv("SITETRAX_ACCESS_TOKEN", "")
_refresh_token = os.getenv("SITETRAX_REFRESH_TOKEN", "")
_token_lock = threading.Lock()

# Project list cache (lightweight names only, ~300s TTL)
_PROJECTS_CACHE_TTL = 300.0
_projects_cache: list = []  # mutable container: [timestamp, results] or empty
_projects_lock = threading.Lock()
_env_path = Path(__file__).resolve().parents[2] / ".env"
_env_mtime: float | None = _env_path.stat().st_mtime if _env_path.exists() else None
if _env_path.exists():
    load_dotenv(_env_path, override=False)
    _API_BASE = os.getenv("SITETRAX_API_BASE", "").rstrip("/")
    _REFRESH_PATH = os.getenv("SITETRAX_REFRESH_PATH", "/auth/token/refresh/")
    _access_token = os.getenv("SITETRAX_ACCESS_TOKEN", _access_token)
    _refresh_token = os.getenv("SITETRAX_REFRESH_TOKEN", _refresh_token)


class SiteTraxAuthError(RuntimeError):
    """Raised when SiteTrax access cannot be refreshed with the configured token."""

class SiteTraxAPIError(RuntimeError):
    """Raised when a SiteTrax API call fails (timeout, connect error, 5xx)."""

class SiteTraxNotFoundError(RuntimeError):
    """Raised when a SiteTrax API returns 404."""

class UnknownFacilityError(RuntimeError):
    """Raised when resolve_buckets cannot find any matching facility."""
    def __init__(self, facility: str, known_names: list[str] | None = None):
        self.facility = facility
        self.known_names = known_names or []
        super().__init__(f"Unknown facility: {facility}")


def _jwt_exp(token: str) -> int | None:
    """Return a JWT exp claim without verifying the signature. For diagnostics only."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        return int(data["exp"]) if data.get("exp") else None
    except Exception:
        return None


def get_auth_status() -> dict:
    """Non-sensitive SiteTrax token status for health/debug endpoints."""
    _reload_env_if_changed()
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    access_exp = _jwt_exp(_access_token)
    refresh_exp = _jwt_exp(_refresh_token)
    return {
        "access_token_configured": bool(_access_token),
        "refresh_token_configured": bool(_refresh_token),
        "access_token_expires_at": (
            datetime.datetime.fromtimestamp(access_exp, datetime.timezone.utc).isoformat()
            if access_exp else None
        ),
        "refresh_token_expires_at": (
            datetime.datetime.fromtimestamp(refresh_exp, datetime.timezone.utc).isoformat()
            if refresh_exp else None
        ),
        "access_token_expired": access_exp is not None and access_exp <= now,
        "refresh_token_expired": refresh_exp is not None and refresh_exp <= now,
    }


# ── Auth / token management ─────────────────────────────────────────────────

def _reload_env_if_changed() -> None:
    """Reload local .env token values after key rotation without restarting dev server.

    Cloud Run config still comes from environment variables and requires a new revision
    for rotated values. This path is mainly for local development, where the user can
    edit backend/.env while uvicorn is already running.
    """
    global _API_BASE, _REFRESH_PATH, _access_token, _refresh_token, _env_mtime
    if not _env_path.exists():
        return
    mtime = _env_path.stat().st_mtime
    if _env_mtime is not None and mtime <= _env_mtime:
        return
    load_dotenv(_env_path, override=True)
    _env_mtime = mtime
    _API_BASE = os.getenv("SITETRAX_API_BASE", "").rstrip("/")
    _REFRESH_PATH = os.getenv("SITETRAX_REFRESH_PATH", "/auth/token/refresh/")
    _access_token = os.getenv("SITETRAX_ACCESS_TOKEN", _access_token)
    _refresh_token = os.getenv("SITETRAX_REFRESH_TOKEN", _refresh_token)
    logger.info("Reloaded SiteTrax auth configuration from backend/.env")


def _access_needs_refresh() -> bool:
    if not _access_token:
        return True
    exp = _jwt_exp(_access_token)
    if exp is None:
        return False
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    return exp <= now + _REFRESH_SKEW_SECONDS


def _refresh_access() -> str:
    """Exchange the refresh token for a new access token. Updates the module token."""
    global _access_token, _refresh_token
    _reload_env_if_changed()
    refresh = _refresh_token or os.getenv("SITETRAX_REFRESH_TOKEN", "")
    if not refresh:
        raise SiteTraxAuthError("SITETRAX_REFRESH_TOKEN not set")
    resp = httpx.post(f"{_API_BASE}{_REFRESH_PATH}", json={"refresh": refresh}, timeout=_TIMEOUT)
    if resp.status_code == 401:
        raise SiteTraxAuthError("SiteTrax refresh token is invalid or expired")
    resp.raise_for_status()
    body = resp.json()
    token = body.get("access", "")
    if not token:
        raise SiteTraxAuthError("refresh response missing 'access'")
    _access_token = token
    if body.get("refresh"):
        _refresh_token = body["refresh"]
    logger.info("SiteTrax access token refreshed")
    return token


def _ensure_access_token() -> None:
    """Refresh before a request if the access token is missing or about to expire."""
    _reload_env_if_changed()
    if not _access_needs_refresh():
        return
    with _token_lock:
        _reload_env_if_changed()
        if _access_needs_refresh():
            _refresh_access()


# ── Date preset engine ──────────────────────────────────────────────────────
# Canonical home for relative/calendar date-keyword resolution. Lives in the
# client (the lowest shared layer) so BOTH the ADK agent and the MCP servers
# resolve "today" / "this_month" / "june" identically — previously only the
# agent did, so the MCP tools choked on keywords. See `_snap_date_filters`.

_MONTH_NAMES = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

_LAST_N_RE = re.compile(
    r"^(?:last|past|previous)?_?(\d+)_?"
    r"(minutes|minute|mins|min|hours|hour|hrs|hr|days|day|weeks|week|wks|wk|"
    r"months|month|mon|mo|quarters|quarter|qtr|years|year|yrs|yr|m|h|d|w|q|y)$"
)

_ROLLING_ALIASES = {
    "last_minute": datetime.timedelta(minutes=1),
    "last_hour": datetime.timedelta(hours=1),
    "past_hour": datetime.timedelta(hours=1),
    "hourly": datetime.timedelta(hours=1),
    "last_day": datetime.timedelta(hours=24),
    "last_24_hours": datetime.timedelta(hours=24),
}


def _delta_for(n: int, unit: str) -> datetime.timedelta | None:
    if unit in ("m", "min", "mins", "minute", "minutes"):
        return datetime.timedelta(minutes=n)
    if unit in ("h", "hr", "hrs", "hour", "hours"):
        return datetime.timedelta(hours=n)
    if unit in ("d", "day", "days"):
        return datetime.timedelta(days=n)
    if unit in ("w", "wk", "wks", "week", "weeks"):
        return datetime.timedelta(weeks=n)
    if unit in ("mo", "mon", "month", "months"):
        return datetime.timedelta(days=30 * n)  # rolling approximation
    if unit in ("q", "qtr", "quarter", "quarters"):
        return datetime.timedelta(days=91 * n)  # rolling approximation
    if unit in ("y", "yr", "yrs", "year", "years"):
        return datetime.timedelta(days=365 * n)  # rolling approximation
    return None


def _add_months(dt: datetime.datetime, n: int) -> datetime.datetime:
    """Calendar-correct month shift, anchored to day 1."""
    m = dt.month - 1 + n
    y = dt.year + m // 12
    return dt.replace(year=y, month=m % 12 + 1, day=1)


def _period(start: datetime.datetime, end: datetime.datetime | None,
            now: datetime.datetime) -> tuple[str, str | None]:
    """ISO-stamp a [start, end) period; leave it open if end is still in the future."""
    return _iso_z(start), (None if end is None or end > now else _iso_z(end))


def resolve_date_range(value) -> tuple[str | None, str | None]:
    """Resolve a keyword/ISO string into a (date_from, date_to) ISO pair.

    Rolling windows and current/"to-date" periods return (start, None). Closed
    calendar periods return (start, end). Unrecognised values and already-ISO
    strings pass through unchanged as (value, None).
    """
    if not value:
        return value, None
    raw = str(value).strip()

    try:  # already an ISO datetime/date → pass through untouched
        datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return raw, None
    except (ValueError, TypeError):
        pass

    v = raw.lower().replace(" ", "_").replace("-", "_")
    now = datetime.datetime.now(datetime.timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Rolling windows
    if v in _ROLLING_ALIASES:
        return _iso_z(now - _ROLLING_ALIASES[v]), None
    m = _LAST_N_RE.match(v)
    if m:
        delta = _delta_for(int(m.group(1)), m.group(2))
        if delta is not None:
            return _iso_z(now - delta), None

    # Calendar: day
    if v in ("today", "current_day"):
        return _period(midnight, midnight + datetime.timedelta(days=1), now)
    if v in ("yesterday", "prev_day", "previous_day"):
        return _period(midnight - datetime.timedelta(days=1), midnight, now)

    # Calendar: week (Monday-anchored)
    week_start = midnight - datetime.timedelta(days=now.weekday())
    if v in ("this_week", "week_to_date", "wtd", "current_week"):
        return _period(week_start, week_start + datetime.timedelta(days=7), now)
    if v in ("last_week", "previous_week", "prior_week"):
        return _period(week_start - datetime.timedelta(days=7), week_start, now)

    # Calendar: month
    month_start = midnight.replace(day=1)
    if v in ("this_month", "month_to_date", "mtd", "current_month"):
        return _period(month_start, _add_months(month_start, 1), now)
    if v in ("last_month", "previous_month", "prior_month"):
        return _period(_add_months(month_start, -1), month_start, now)

    # Calendar: quarter
    quarter_start = midnight.replace(month=((now.month - 1) // 3) * 3 + 1, day=1)
    if v in ("this_quarter", "quarter_to_date", "qtd", "current_quarter"):
        return _period(quarter_start, _add_months(quarter_start, 3), now)
    if v in ("last_quarter", "previous_quarter", "prior_quarter"):
        return _period(_add_months(quarter_start, -3), quarter_start, now)

    # Calendar: year
    year_start = midnight.replace(month=1, day=1)
    if v in ("this_year", "year_to_date", "ytd", "current_year"):
        return _period(year_start, year_start.replace(year=year_start.year + 1), now)
    if v in ("last_year", "previous_year", "prior_year"):
        return _period(year_start.replace(year=year_start.year - 1), year_start, now)

    # Explicit quarter: q1 / q3_2025
    qm = re.match(r"^q([1-4])(?:_?(\d{4}))?$", v)
    if qm:
        qi, yr = int(qm.group(1)), int(qm.group(2)) if qm.group(2) else now.year
        start = midnight.replace(year=yr, month=(qi - 1) * 3 + 1, day=1)
        if not qm.group(2) and start > now:
            start = start.replace(year=yr - 1)
        return _period(start, _add_months(start, 3), now)

    # Named month: june / dec_2025
    nm = re.match(r"^([a-z]+)(?:_?(\d{4}))?$", v)
    if nm and nm.group(1) in _MONTH_NAMES:
        mon = _MONTH_NAMES[nm.group(1)]
        yr = int(nm.group(2)) if nm.group(2) else now.year
        start = midnight.replace(year=yr, month=mon, day=1)
        if not nm.group(2) and start > now:
            start = start.replace(year=yr - 1)
        return _period(start, _add_months(start, 1), now)

    return raw, None  # unrecognised → leave for the API to validate/reject


def resolve_date(value) -> str | None:
    """Single-point resolver: the start bound of a preset/ISO value."""
    return resolve_date_range(value)[0]


# ── Business-day boundary normalization ─────────────────────────────────────
# The dashboards define a "day" on a fixed UTC offset whose midnight lands at
# 20:00:00 UTC. Every date filter we send must snap to that boundary so the
# agent's numbers line up with what the dashboards show. So a query for June
# (today = the 9th) goes out as:
#     created_at__gte=2026-05-31 20:00:00   (start of June 1, business tz)
#     created_at__lte=2026-06-09 20:00:00   (end of today,   business tz)
# The hour is ALWAYS 20:00:00. This is a fixed-offset boundary (no DST shift);
# change _BIZ_BOUNDARY_HOUR_UTC if the dashboard timezone policy changes.
_BIZ_BOUNDARY_HOUR_UTC = int(os.getenv("SITETRAX_DAY_BOUNDARY_HOUR_UTC", "20"))


def _parse_filter_dt(value) -> datetime.datetime | None:
    """Parse an ISO/space datetime (with or without tz/Z) into an aware UTC dt."""
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def _biz_floor(dt: datetime.datetime) -> datetime.datetime:
    """Latest business-day boundary (HH:20:00:00 UTC) at or before dt."""
    b = dt.replace(hour=_BIZ_BOUNDARY_HOUR_UTC, minute=0, second=0, microsecond=0)
    return b if b <= dt else b - datetime.timedelta(days=1)


def _biz_ceil(dt: datetime.datetime) -> datetime.datetime:
    """Earliest business-day boundary (HH:20:00:00 UTC) at or after dt."""
    b = dt.replace(hour=_BIZ_BOUNDARY_HOUR_UTC, minute=0, second=0, microsecond=0)
    return b if b >= dt else b + datetime.timedelta(days=1)


def _fmt_biz(dt: datetime.datetime) -> str:
    """Render as the dashboard wire format: 'YYYY-MM-DD 20:00:00' (UTC, no Z)."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _is_utc_midnight(dt: datetime.datetime) -> bool:
    return (dt.hour, dt.minute, dt.second, dt.microsecond) == (0, 0, 0, 0)


def _snap_date_filters(params: dict | None) -> dict | None:
    """Resolve date presets, then snap any *__gte / *__lte filters to the
    business-day boundary. This is the single chokepoint for every live query,
    so both the agent and the MCP servers get identical date handling.

    - Keyword values ("today", "this_month", "june"…) are resolved to ISO first.
      A closed-period keyword in `__gte` (e.g. "yesterday") backfills `__lte`.
    - `__gte` (inclusive start) floors to the boundary at/just-before it, so a
      UTC-midnight day start becomes the prior 20:00:00.
    - `__lte` snaps to the boundary that closes its day: an exclusive UTC-midnight
      end (how closed periods are encoded) floors; any other instant ceils so the
      whole final day is included.
    - When a `__gte` is present without a matching `__lte`, we add one at the end
      of the current business day so open-ended periods ("this month", "today")
      still terminate on the dashboard boundary.
    """
    if not params:
        return params
    out = dict(params)
    now = datetime.datetime.now(datetime.timezone.utc)

    def snap_upper(dt: datetime.datetime) -> datetime.datetime:
        return _biz_floor(dt) if _is_utc_midnight(dt) else _biz_ceil(dt)

    gte_fields = {k[:-5] for k in out if k.endswith("__gte")}
    for field in gte_fields:
        gkey, lkey = f"{field}__gte", f"{field}__lte"
        # Resolve presets → ISO; a closed period's end backfills a missing __lte.
        g_start, g_end = resolve_date_range(out.get(gkey))
        gdt = _parse_filter_dt(g_start)
        if gdt is not None:
            out[gkey] = _fmt_biz(_biz_floor(gdt))
        if out.get(lkey):
            _, l_end = resolve_date_range(out.get(lkey))
            ldt = _parse_filter_dt(l_end or out.get(lkey))
            if ldt is not None:
                out[lkey] = _fmt_biz(snap_upper(ldt))
        elif g_end is not None:
            out[lkey] = _fmt_biz(snap_upper(_parse_filter_dt(g_end)))
        elif gdt is not None:
            out[lkey] = _fmt_biz(_biz_ceil(now))  # open-ended → end of current day

    # Lone __lte filters (no matching __gte) still get resolved + snapped.
    for key in list(out):
        if key.endswith("__lte") and key[:-5] not in gte_fields and out.get(key):
            _, l_end = resolve_date_range(out.get(key))
            ldt = _parse_filter_dt(l_end or out.get(key))
            if ldt is not None:
                out[key] = _fmt_biz(snap_upper(ldt))
    return out


def _request(path: str, params: dict | None = None, timeout: float | None = None):
    """GET an API path with auth; refresh once on 401 and retry. Returns parsed JSON."""
    params = _snap_date_filters(params)
    url = f"{_API_BASE}{path}"
    last = None
    for attempt in range(3):
        if attempt == 0:
            _ensure_access_token()
        headers = {"Authorization": f"Bearer {_access_token}", "Accept": "application/json"}
        try:
            last = httpx.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout or _TIMEOUT,
                follow_redirects=True,
            )
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            if attempt < 2:
                # Exponential backoff with jitter before retry
                delay = (1.5 ** attempt) + random.uniform(0, 0.5)
                logger.warning("SiteTrax request timeout/connect on %s, retrying in %.1fs: %s", path, delay, exc)
                import time
                time.sleep(delay)
                continue
            raise SiteTraxAPIError(f"SiteTrax API unreachable for {path}: {exc}") from exc

        if last.status_code == 401 and attempt == 0:
            with _token_lock:
                _refresh_access()
            continue
        if last.status_code == 401:
            raise SiteTraxAuthError("SiteTrax access token is invalid and refresh did not recover it")
        if last.status_code == 404:
            raise SiteTraxNotFoundError(f"SiteTrax resource not found: {path}")
        if 500 <= last.status_code < 600:
            if attempt < 2:
                delay = (1.5 ** attempt) + random.uniform(0, 0.5)
                logger.warning("SiteTrax server error %s on %s, retrying in %.1fs", last.status_code, path, delay)
                import time
                time.sleep(delay)
                continue
            raise SiteTraxAPIError(f"SiteTrax server error {last.status_code} on {path}")
        if 400 <= last.status_code < 500:
            raise SiteTraxAPIError(f"SiteTrax client error {last.status_code} on {path}: {last.text[:200]}")
        last.raise_for_status()
        return last.json()
    last.raise_for_status()


# ── Pagination helper ───────────────────────────────────────────────────────

def _fetch_all_pages(path: str, params: dict | None = None, max_results: int = 200, timeout: float | None = None) -> list[dict]:
    """Auto-fetch paginated results until no more pages or max_results reached."""
    return _fetch_pages_with_meta(path, params, max_results=max_results, timeout=timeout)["rows"]


def _fetch_pages_with_meta(path: str, params: dict | None = None, max_results: int = 200, timeout: float | None = None) -> dict:
    """Auto-fetch paginated results and return rows plus UI-friendly progress metadata."""
    results = []
    page = 1
    params = dict(params or {})
    progress = []
    total_count = None
    has_next_page = False
    while len(results) < max_results:
        params["page"] = page
        data = _request(path, params, timeout)
        if not isinstance(data, dict):
            break
        if total_count is None and isinstance(data.get("count"), int):
            total_count = data["count"]
        batch = _unwrap(data)
        if not batch:
            break
        results.extend(batch)
        fetched = min(len(results), max_results)
        expected = min(total_count, max_results) if total_count is not None else None
        progress.append({
            "page": page,
            "rows_in_page": len(batch),
            "rows_fetched": fetched,
            "expected_rows": expected,
            "percent": round((fetched / expected) * 100, 1) if expected else None,
        })
        has_next_page = bool(data.get("next"))
        if not has_next_page:
            break
        page += 1
    rows = results[:max_results]
    expected_rows = min(total_count, max_results) if total_count is not None else len(rows)
    cap_reached = total_count is not None and len(rows) < total_count and len(rows) >= max_results
    # Fallback: if count is missing but next page existed, we definitely have more
    has_more = (total_count is not None and len(rows) < total_count) or (cap_reached and has_next_page)
    if cap_reached:
        logger.warning(
            "SiteTrax pagination truncated for %s after %s/%s rows (limit=%s)",
            path,
            len(rows),
            total_count,
            max_results,
        )
    return {
        "rows": rows,
        "pagination": {
            "paginated": True,
            "pages_fetched": len(progress),
            "rows_returned": len(rows),
            "total_available": total_count,
            "limit": max_results,
            "cap_reached": cap_reached,
            "has_more": has_more,
            "progress": {
                "status": "complete",
                "label": f"Fetched {len(rows)} row{'s' if len(rows) != 1 else ''}"
                + (f" across {len(progress)} page{'s' if len(progress) != 1 else ''}" if progress else ""),
                "percent": 100 if expected_rows else None,
                "steps": progress,
            },
        },
    }


# ── Mapping helpers ─────────────────────────────────────────────────────────

def _safe_float(value) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _norm_dt(ts) -> str:
    """Normalize an ISO timestamp (handles `Z`); returns an aware ISO string or ''."""
    if not ts:
        return ""
    try:
        return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).isoformat()
    except (ValueError, TypeError):
        return str(ts)


def _unwrap(data) -> list[dict]:
    """Return the list of records from a list response or a DRF {results:[...]} page."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "data", "assets", "records", "metrics", "videos", "projects", "choices"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def _asset_image_url(raw: dict) -> str:
    """Return the canonical image URL across SiteTrax's mixed field casing."""
    if not isinstance(raw, dict):
        return ""
    return (
        raw.get("AssetImage")
        or raw.get("asset_image")
        or raw.get("image_url")
        or raw.get("image")
        or raw.get("thumbnail_url")
        or raw.get("thumbnail")
        or ""
    )


def _asset_thumbnail_url(raw: dict) -> str:
    """Return the preferred thumbnail/low-res URL, falling back to the full image."""
    if not isinstance(raw, dict):
        return ""
    return (
        raw.get("asset_image_lr")
        or raw.get("thumbnail_url")
        or raw.get("thumbnail")
        or raw.get("thumbnail_md")
        or raw.get("thumbnail_hr")
        or _asset_image_url(raw)
    )


_SENSITIVE_KEY_PARTS = ("token", "secret", "password", "credential", "authorization", "api_key")


def _redact_payload(value):
    """Keep payload shape complete while removing credentials before returning it to the UI."""
    if isinstance(value, dict):
        redacted = {}
        for key, child in value.items():
            key_text = str(key).lower()
            if any(part in key_text for part in _SENSITIVE_KEY_PARTS):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact_payload(child)
        return redacted
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    return value


def _map_asset(raw: dict) -> dict:
    """Map a live SiteTrax asset to the internal record shape (mock_data.py schema)."""
    if not isinstance(raw, dict):
        return {}
    text = raw.get("Text") or raw.get("text") or ""
    bucket = raw.get("bucket") if isinstance(raw.get("bucket"), dict) else {}
    camera = raw.get("camera") if isinstance(raw.get("camera"), dict) else {}
    video = raw.get("video") or raw.get("video_id") or raw.get("video_name") or ""
    if isinstance(video, dict):
        video = video.get("id") or video.get("name") or ""
    # `datetime` is UTC; fall back to scanned_at/created_at (offset) only if missing.
    dt = _norm_dt(raw.get("datetime") or raw.get("scanned_at") or raw.get("created_at") or "")
    image_url = _asset_image_url(raw)
    thumbnail_url = _asset_thumbnail_url(raw)
    return {
        "id": raw.get("id", 0),
        "video_name": str(video or ""),
        "type": raw.get("Type") or raw.get("type") or "container",
        "text": text,
        "datetime": dt,
        "datetime_original": _norm_dt(raw.get("scanned_at", "")) or dt,
        "datetime_digitized": _norm_dt(raw.get("created_at", "")) or dt,
        "gps_lat": _safe_float(raw.get("gps_lat", 0.0)),
        "gps_lon": _safe_float(raw.get("gps_lon", 0.0)),
        "asset_image": image_url,
        "image_url": image_url,
        "thumbnail_url": thumbnail_url,
        "asset_image_lr": raw.get("asset_image_lr") or thumbnail_url,
        "container_company": (text[:4].upper() if len(text) >= 4 else "UNKNOWN"),
        "container_country": "UNKNOWN",
        "status": raw.get("Status_Code") or raw.get("status") or "A0",
        "status_code": raw.get("Status_Code") or raw.get("status_code") or "A0",
        "camera": camera.get("name") or camera.get("serial") or raw.get("camera") or "api",
        "location": bucket.get("name") or raw.get("location") or "Unknown",
        "stacking": raw.get("Stacking") or raw.get("stacking") or "",
        "sorting": raw.get("sorting") or "",
        "asset_heading": raw.get("AssetHeading") or "",
        "bucket_id": bucket.get("id"),
        "raw_payload": _redact_payload(raw),
    }


def _map_asset_with_project(asset: dict | None, project: dict | None = None) -> dict | None:
    """Map an asset and enrich `/sv/assets/last/` wrapper project context."""
    if not isinstance(asset, dict):
        return None
    mapped = _map_asset(asset)
    if isinstance(project, dict):
        project_name = project.get("name") or project.get("display_name") or project.get("title")
        if project_name:
            mapped["facility"] = project_name
            if not mapped.get("location") or mapped.get("location") == "Unknown":
                mapped["location"] = project_name
        if project.get("id") and not mapped.get("bucket_id"):
            mapped["bucket_id"] = project.get("id")
    return mapped


def _iso_z(dt: datetime.datetime) -> str:
    """Format a UTC datetime as the ISO8601 the API's date filters require."""
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Public API (read-only) ──────────────────────────────────────────────────

def _build_asset_params(
    container_id: str | None = None,
    location: str | None = None,
    camera: str | None = None,
    status_code: str | None = None,
    hours_back: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Build the request params dict for /sv/assets/ queries."""
    now = datetime.datetime.now(datetime.timezone.utc)
    params: dict = {"page": 1}
    if container_id:
        params["search"] = container_id
    if status_code:
        params["Status_Code__in"] = status_code
    if date_from:
        params["created_at__gte"] = date_from
    elif hours_back:
        params["created_at__gte"] = _iso_z(now - datetime.timedelta(hours=hours_back))
    if date_to:
        params["created_at__lte"] = date_to
    if location:
        buckets = resolve_buckets(location)
        if buckets:
            params["bucket__in"] = ",".join(str(b) for b in buckets)
    if camera:
        params["camera"] = camera
    return params


def query_assets(
    container_id: str | None = None,
    location: str | None = None,
    camera: str | None = None,
    status_code: str | None = None,
    hours_back: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int | None = 250,
) -> list[dict]:
    """Query live assets via GET /sv/assets/.

    Supports container_id, location (bucket name), camera, status_code, and API-native
    date_from/date_to filters mapped to created_at__gte/created_at__lte.
    hours_back is a deprecated compatibility fallback for internal scheduler paths.
    *limit* caps pagination (default 250). Pass None for no cap.
    """
    params = _build_asset_params(container_id, location, camera, status_code, hours_back, date_from, date_to)
    max_results = limit if limit is not None else 10000
    records = _fetch_all_pages("/sv/assets/", params, max_results=max_results, timeout=_FACILITY_TIMEOUT)
    mapped = [_map_asset(r) for r in records]
    return mapped


def query_assets_with_pagination(
    container_id: str | None = None,
    location: str | None = None,
    camera: str | None = None,
    status_code: str | None = None,
    hours_back: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int | None = 250,
) -> dict:
    """Query live assets and return {assets: [...], pagination: {...}}.

    Use this when you need the real total count or cap-reached signal.
    *limit* caps pagination (default 250). Pass None for no cap.
    """
    params = _build_asset_params(container_id, location, camera, status_code, hours_back, date_from, date_to)
    max_results = limit if limit is not None else 10000
    meta = _fetch_pages_with_meta("/sv/assets/", params, max_results=max_results, timeout=_FACILITY_TIMEOUT)
    meta["rows"] = [_map_asset(r) for r in meta["rows"]]
    return {
        "assets": meta["rows"],
        "pagination": {
            "showing": len(meta["rows"]),
            "total_available": meta.get("total_available"),
            "has_more": meta.get("has_more", False),
            "limit": limit,
            "cap_reached": meta.get("cap_reached", False),
            "progress": meta.get("progress"),
        },
    }


def _within_date_range(value: str | None, date_from: str | None = None, date_to: str | None = None) -> bool:
    if not value:
        return True
    try:
        dt = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if date_from:
            start = datetime.datetime.fromisoformat(str(date_from).replace("Z", "+00:00"))
            if dt < start:
                return False
        if date_to:
            end = datetime.datetime.fromisoformat(str(date_to).replace("Z", "+00:00"))
            if dt > end:
                return False
    except (TypeError, ValueError):
        return True
    return True


def _normalize_container_text(text: str) -> str:
    """Normalize container text for exact-match API queries."""
    return text.strip().upper()


def get_latest_scan(container_id: str) -> dict | None:
    """Most recent detection of a container via GET /sv/assets/timeline/?Text=."""
    timeline = get_asset_timeline(container_id)
    return timeline[0] if timeline else None


def get_asset_timeline(text: str) -> list[dict]:
    """Full detection history for a container (GET /sv/assets/timeline/?Text=), newest first."""
    requested_text = _normalize_container_text(text)
    records = _unwrap(_request("/sv/assets/timeline/", {"Text": requested_text}))
    partial_match = False
    matched_text = requested_text
    if not records:
        search_rows = _fetch_all_pages(
            "/sv/assets/",
            {"page": 1, "search": requested_text},
            max_results=10,
            timeout=_FACILITY_TIMEOUT,
        )
        if search_rows:
            def newest_key(row: dict) -> str:
                return str(row.get("datetime") or row.get("scanned_at") or row.get("created_at") or "")

            newest = sorted(search_rows, key=newest_key, reverse=True)[0]
            candidate = _normalize_container_text(str(newest.get("Text") or newest.get("text") or ""))
            if candidate and candidate != requested_text:
                retry_records = _unwrap(_request("/sv/assets/timeline/", {"Text": candidate}))
                if retry_records:
                    records = retry_records
                    matched_text = candidate
                    partial_match = True
    mapped = [_map_asset(r) for r in records]
    if partial_match:
        for row in mapped:
            row["partial_match"] = True
            row["requested_text"] = requested_text
            row["matched_text"] = matched_text
    return mapped


def get_last_asset(bucket_ids: list | None = None) -> dict | None:
    """Most recent asset overall or for given project buckets (GET /sv/assets/last/)."""
    params = {}
    if bucket_ids:
        params["bucket__in"] = ",".join(str(b) for b in bucket_ids)
    data = _request("/sv/assets/last/", params)
    asset = data.get("asset") if isinstance(data, dict) else None
    project = data.get("project") if isinstance(data, dict) else None
    return _map_asset_with_project(asset, project)


def get_asset(asset_id) -> dict | None:
    """A single asset's detail (GET /sv/assets/{id})."""
    data = _request(f"/sv/assets/{asset_id}/", None)
    asset = data if isinstance(data, dict) else None
    return _map_asset(asset) if isinstance(asset, dict) else None


def list_projects(search: str | None = None, full_detail: bool = False) -> list[dict]:
    """List projects. Lightweight names via /sv/project/name/ by default.
    Set full_detail=True for paginated full detail via /sv/project/."""
    if full_detail:
        params: dict = {"page": 1}
        if search:
            params["search"] = search
        return _fetch_all_pages("/sv/project/", params, max_results=500, timeout=_FACILITY_TIMEOUT)

    # Cache only the lightweight no-search path (used by resolve_buckets)
    if not search:
        with _projects_lock:
            now = datetime.datetime.now(datetime.timezone.utc).timestamp()
            if _projects_cache and (now - _projects_cache[0]) < _PROJECTS_CACHE_TTL:
                return _projects_cache[1]

    results = _fetch_all_pages(
        "/sv/project/name/",
        {"page": 1, **({"search": search} if search else {})},
        max_results=500,
        timeout=_FACILITY_TIMEOUT,
    )

    if not search:
        with _projects_lock:
            _projects_cache[:] = [datetime.datetime.now(datetime.timezone.utc).timestamp(), results]
    return results


def asset_metrics(bucket_ids: list | None = None,
                  since: datetime.datetime | None = None,
                  until: datetime.datetime | None = None) -> dict:
    """Aggregated asset metrics (GET /sv/assets/metrics/)."""
    params: dict = {"page": 1}
    if bucket_ids:
        params["bucket__in"] = ",".join(str(b) for b in bucket_ids)
    if since:
        params["created_at__gte"] = _iso_z(since)
    if until:
        params["created_at__lte"] = _iso_z(until)
    return _request("/sv/assets/metrics/", params)


def resolve_buckets(facility: str) -> list[int]:
    """Resolve a facility/yard/project name to matching bucket id(s) via /sv/project/name/."""
    if not facility:
        return []
    try:
        results = list_projects()
    except SiteTraxAuthError:
        raise
    except Exception:
        return []
    name_lower = facility.lower().strip()
    tokens = set(name_lower.split())

    # Ranked matching: exact (ci) → prefix → all-tokens-present → substring of project name only
    exact_matches = []
    prefix_matches = []
    token_matches = []
    substring_matches = []

    for p in results:
        if not isinstance(p, dict):
            continue
        pname = (p.get("name") or "").lower()
        pid = p.get("id")
        if pid is None:
            continue

        if pname == name_lower:
            exact_matches.append(int(pid))
        elif pname.startswith(name_lower + " ") or pname.startswith(name_lower + "-"):
            prefix_matches.append(int(pid))
        elif tokens and tokens.issubset(set(pname.split())):
            token_matches.append(int(pid))
        elif name_lower in pname:
            substring_matches.append(int(pid))
        # NOTE: never reverse-containment (pname in name_lower) — avoids "Ford" → "Norfolk" false positives

    # Return best tier only, in order of preference
    for tier in (exact_matches, prefix_matches, token_matches, substring_matches):
        if tier:
            return list(dict.fromkeys(tier))  # preserve order, dedupe
    # Raise typed error with known names so the agent can explain what's available
    known_names = [p.get("name") for p in results if isinstance(p, dict) and p.get("name")]
    raise UnknownFacilityError(facility, known_names=known_names)


# ── Facility (bucket) resolution + facility-scoped queries ──────────────────

_FACILITY_TIMEOUT = float(os.getenv("SITETRAX_FACILITY_TIMEOUT", "90"))  # bucket-scoped queries can be slow


def get_facility_last_scan(facility: str) -> dict | None:
    """Most recent asset at a facility (resolved to bucket)."""
    buckets = resolve_buckets(facility)
    if not buckets:
        return None
    data = _request("/sv/assets/last/", {"bucket__in": ",".join(str(b) for b in buckets)},
                    timeout=_FACILITY_TIMEOUT)
    asset = data.get("asset") if isinstance(data, dict) else None
    project = data.get("project") if isinstance(data, dict) else None
    return _map_asset_with_project(asset, project)


def get_facility_recent(
    facility: str,
    date_from: str | None = None,
    date_to: str | None = None,
    hours_back: int | None = None,
) -> list[dict]:
    """Recent assets at a facility (resolved to bucket)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    buckets = resolve_buckets(facility)
    params = {"page": 1}
    if date_from:
        params["created_at__gte"] = date_from
    elif hours_back:
        params["created_at__gte"] = _iso_z(now - datetime.timedelta(hours=hours_back))
    if date_to:
        params["created_at__lte"] = date_to
    if buckets:
        params["bucket__in"] = ",".join(str(b) for b in buckets)
    return [_map_asset(r) for r in _unwrap(_request("/sv/assets/", params, timeout=_FACILITY_TIMEOUT))]


# ── Video ───────────────────────────────────────────────────────────────────

def _map_video(raw: dict) -> dict:
    cam = raw.get("camera") if isinstance(raw.get("camera"), dict) else {}
    bucket = raw.get("bucket") if isinstance(raw.get("bucket"), dict) else {}
    return {
        "id": raw.get("id"),
        "created_at": _norm_dt(raw.get("created_at", "")),
        "length_seconds": raw.get("length"),
        "number_of_assets": raw.get("number_of_assets"),
        "asset_ids": raw.get("assets") or [],
        "facility": bucket.get("name") or cam.get("name"),
        "thumbnail_url": raw.get("thumbnail_url") or raw.get("thumbnail") or raw.get("thumbnail_md") or raw.get("thumbnail_hr"),
        "thumbnail": raw.get("thumbnail_url") or raw.get("thumbnail") or raw.get("thumbnail_md") or raw.get("thumbnail_hr"),
        "status": raw.get("status"),
        "raw_payload": _redact_payload(raw),
    }


def _map_project(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}
    return {
        "id": raw.get("id"),
        "name": raw.get("name") or raw.get("display_name") or raw.get("title"),
        "created_at": _norm_dt(raw.get("created_at", "")),
        "updated_at": _norm_dt(raw.get("updated_at", "")),
        "raw_payload": _redact_payload(raw),
    }


def _map_identity(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}
    return _redact_payload(raw)


def _map_metric(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}
    mapped = dict(raw)
    for key in ("created_at_day", "date", "day", "created_at"):
        if mapped.get(key):
            mapped[key] = _norm_dt(mapped.get(key))
    mapped["raw_payload"] = _redact_payload(raw)
    return mapped


def _project_name_lookup(projects: list | None) -> dict:
    lookup = {}
    for project in projects or []:
        if not isinstance(project, dict):
            continue
        pid = project.get("id")
        name = project.get("name") or project.get("display_name") or project.get("title")
        if pid is not None and name:
            lookup[pid] = name
            lookup[str(pid)] = name
    return lookup


def _metric_bucket_id(row: dict):
    bucket = row.get("bucket") or row.get("project") or row.get("project_id") or row.get("bucket_id")
    if isinstance(bucket, dict):
        return bucket.get("id")
    return bucket


def _join_project_metric_rows(data) -> list[dict]:
    if isinstance(data, dict):
        metrics = data.get("metrics") if isinstance(data.get("metrics"), list) else _unwrap(data)
        projects = data.get("projects") if isinstance(data.get("projects"), list) else []
        lookup = _project_name_lookup(projects)
    else:
        metrics = data if isinstance(data, list) else []
        lookup = {}
    rows = []
    for row in metrics:
        mapped = _map_metric(row)
        bucket_id = _metric_bucket_id(row) if isinstance(row, dict) else None
        facility = lookup.get(bucket_id) or lookup.get(str(bucket_id))
        if facility:
            mapped["facility"] = facility
            mapped["project_name"] = facility
        if bucket_id is not None:
            mapped["bucket_id"] = bucket_id
        rows.append(mapped)
    return rows


@dataclass(frozen=True)
class SiteTraxEndpointSpec:
    resource: str
    path: str
    description: str
    entity_type: str
    paginated: bool = True
    search_param: str | None = "search"
    date_field: str | None = "created_at"
    id_filter: str | None = None
    allowed_filters: tuple[str, ...] = ()
    default_ordering: str | None = None
    columns: tuple[str, ...] = ()
    visualizations: tuple[str, ...] = ("table",)
    relationships: tuple[str, ...] = ()

    def public_dict(self) -> dict:
        data = asdict(self)
        data["date_filters"] = (
            {"date_from": f"{self.date_field}__gte", "date_to": f"{self.date_field}__lte"}
            if self.date_field else {}
        )
        return data


_ENDPOINTS: dict[str, SiteTraxEndpointSpec] = {
    "assets": SiteTraxEndpointSpec(
        resource="assets",
        path="/sv/assets/",
        description="Detected asset/container records with status, heading, image, camera, project, GPS, and video reference.",
        entity_type="asset",
        allowed_filters=("bucket__in", "camera", "Status_Code__in", "Type", "status_code", "facility", "location"),
        columns=("id", "text", "status_code", "datetime", "location", "camera", "asset_heading", "image_url", "video_name"),
        visualizations=("table", "timeline", "image_gallery"),
        relationships=("asset_detail", "video_detail", "video_playback_url", "project"),
    ),
    "asset_timeline": SiteTraxEndpointSpec(
        resource="asset_timeline",
        path="/sv/assets/timeline/",
        description="Full detection timeline for one container or asset text.",
        entity_type="asset",
        paginated=False,
        search_param=None,
        date_field=None,
        id_filter="Text",
        allowed_filters=("Text", "container_id"),
        columns=("id", "text", "status_code", "datetime", "location", "camera", "asset_heading", "image_url", "video_name"),
        visualizations=("timeline", "table", "image_gallery"),
        relationships=("asset_detail", "video_detail", "video_playback_url"),
    ),
    "asset_detail": SiteTraxEndpointSpec(
        resource="asset_detail",
        path="/sv/assets/{id}/",
        description="Single asset record detail by asset ID.",
        entity_type="asset",
        paginated=False,
        search_param=None,
        date_field=None,
        id_filter="id",
        allowed_filters=("id", "asset_id"),
        columns=("id", "text", "status_code", "datetime", "location", "camera", "asset_heading", "image_url", "video_name"),
        visualizations=("table", "image_gallery", "json"),
        relationships=("video_detail", "video_playback_url"),
    ),
    "asset_last": SiteTraxEndpointSpec(
        resource="asset_last",
        path="/sv/assets/last/",
        description="Most recent asset overall or within a project/facility bucket.",
        entity_type="asset",
        paginated=False,
        search_param=None,
        allowed_filters=("bucket__in", "facility", "location"),
        columns=("id", "text", "status_code", "datetime", "location", "camera", "asset_heading", "image_url", "video_name"),
        visualizations=("table", "image_gallery"),
        relationships=("asset_detail", "video_detail", "video_playback_url"),
    ),
    "asset_metrics": SiteTraxEndpointSpec(
        resource="asset_metrics",
        path="/sv/assets/metrics/",
        description="Daily asset scan metrics. `count` is distinct visible containers/day, `trans` is visible transactions/day, and *_unfiltered includes hidden assets.",
        entity_type="metric",
        allowed_filters=("bucket__in", "facility", "location"),
        columns=("created_at_day", "count", "trans", "count_unfiltered", "trans_unfiltered", "bucket"),
        visualizations=("metric_grid", "line", "bar", "table"),
    ),
    "project_metrics": SiteTraxEndpointSpec(
        resource="project_metrics",
        path="/sv/assets/project_metrics/",
        description="Per-project/facility daily asset metrics joined to facility names. `count` is distinct visible containers/day; `trans` is visible transactions/day.",
        entity_type="metric",
        paginated=False,
        allowed_filters=("bucket__in", "facility", "location"),
        columns=("created_at_day", "facility", "bucket", "bucket_id", "count", "trans", "count_unfiltered", "trans_unfiltered"),
        visualizations=("bar", "line", "table"),
        relationships=("project",),
    ),
    "projects": SiteTraxEndpointSpec(
        resource="projects",
        path="/sv/project/",
        description="Full project/facility records.",
        entity_type="project",
        allowed_filters=("id", "name"),
        columns=("id", "name", "created_at", "updated_at"),
        visualizations=("table", "json"),
        relationships=("project_integrations", "assets", "videos"),
    ),
    "project_names": SiteTraxEndpointSpec(
        resource="project_names",
        path="/sv/project/name/",
        description="Lightweight project/facility names used for facility resolution.",
        entity_type="project",
        allowed_filters=("id", "name"),
        columns=("id", "name"),
        visualizations=("table",),
    ),
    "project_detail": SiteTraxEndpointSpec(
        resource="project_detail",
        path="/sv/project/{id}/",
        description="Single project/facility detail by project ID.",
        entity_type="project",
        paginated=False,
        search_param=None,
        date_field=None,
        id_filter="id",
        allowed_filters=("id", "project_id"),
        columns=("id", "name", "created_at", "updated_at"),
        visualizations=("table", "json"),
        relationships=("project_integrations",),
    ),
    "project_integrations": SiteTraxEndpointSpec(
        resource="project_integrations",
        path="/sv/project/{id}/datatools/",
        description="Configured project integrations and data tools.",
        entity_type="integration",
        paginated=False,
        search_param=None,
        date_field=None,
        id_filter="id",
        allowed_filters=("id", "project_id"),
        columns=("id", "name", "type", "status"),
        visualizations=("table", "json"),
    ),
    "videos": SiteTraxEndpointSpec(
        resource="videos",
        path="/sv/videos/",
        description="Processed video clips with asset IDs, thumbnails, camera, project, status, and timestamps.",
        entity_type="video",
        allowed_filters=("bucket__in", "facility", "location", "camera", "status", "stream_type"),
        default_ordering="-created_at",
        columns=("id", "created_at", "facility", "length_seconds", "number_of_assets", "thumbnail_url", "status"),
        visualizations=("video_gallery", "table", "bar"),
        relationships=("video_detail", "video_playback_url", "assets"),
    ),
    "video_detail": SiteTraxEndpointSpec(
        resource="video_detail",
        path="/sv/video/{id}/",
        description="Single video detail by video ID.",
        entity_type="video",
        paginated=False,
        search_param=None,
        date_field=None,
        id_filter="id",
        allowed_filters=("id", "video_id"),
        columns=("id", "created_at", "facility", "length_seconds", "number_of_assets", "thumbnail_url", "status"),
        visualizations=("video_gallery", "table", "json"),
        relationships=("video_playback_url", "assets"),
    ),
    "video_playback_url": SiteTraxEndpointSpec(
        resource="video_playback_url",
        path="/sv/video/{id}/get_url/",
        description="Temporary playback URL for one video.",
        entity_type="video_playback_url",
        paginated=False,
        search_param=None,
        date_field=None,
        id_filter="id",
        allowed_filters=("id", "video_id"),
        columns=("object_url",),
        visualizations=("table",),
    ),
    "video_metrics": SiteTraxEndpointSpec(
        resource="video_metrics",
        path="/sv/videos/metrics/",
        description="Single totals dict for video processing metrics: total_count, total_size, and total_length.",
        entity_type="metric",
        paginated=False,
        allowed_filters=("bucket__in", "facility", "location"),
        columns=("total_count", "total_size", "total_length"),
        visualizations=("metric_grid", "line", "bar", "table"),
    ),
    "auth_self": SiteTraxEndpointSpec(
        resource="auth_self",
        path="/auth/self/",
        description="Authenticated SiteTrax user/account profile for the current API token.",
        entity_type="identity",
        paginated=False,
        search_param=None,
        date_field=None,
        columns=("id", "email", "name", "first_name", "last_name"),
        visualizations=("table", "json"),
    ),
    "feedback_choices": SiteTraxEndpointSpec(
        resource="feedback_choices",
        path="/feedback_choices/",
        description="Read-only feedback choice catalog used by review/feedback UI.",
        entity_type="feedback_choice",
        paginated=False,
        search_param=None,
        date_field=None,
        columns=("id", "name", "label", "value"),
        visualizations=("table", "json"),
    ),
    "project_last_video": SiteTraxEndpointSpec(
        resource="project_last_video",
        path="/sv/project/{id}/get_last_video/",
        description="Most recent video for one project/facility by project ID.",
        entity_type="video",
        paginated=False,
        search_param=None,
        date_field=None,
        id_filter="id",
        allowed_filters=("id", "project_id"),
        columns=("id", "created_at", "facility", "length_seconds", "number_of_assets", "thumbnail_url", "status"),
        visualizations=("video_gallery", "table", "json"),
        relationships=("video_detail", "video_playback_url"),
    ),
    "assets_export": SiteTraxEndpointSpec(
        resource="assets_export",
        path="/assets/export/",
        description="Raw export payload for asset records.",
        entity_type="asset_export",
        paginated=False,
        allowed_filters=("bucket__in", "facility", "location"),
        columns=("id", "Text", "Status_Code", "datetime", "bucket", "camera"),
        visualizations=("table", "json"),
    ),
}


_RESOURCE_ALIASES = {
    "asset": "assets",
    "container": "assets",
    "containers": "assets",
    "timeline": "asset_timeline",
    "facility": "projects",
    "facilities": "project_names",
    "project": "projects",
    "video": "videos",
    "metrics": "asset_metrics",
    "self": "auth_self",
    "me": "auth_self",
    "feedback": "feedback_choices",
    "last_video": "project_last_video",
}


def _resource_key(resource: str | None) -> str:
    key = (resource or "assets").strip().lower()
    key = _RESOURCE_ALIASES.get(key, key)
    if key not in _ENDPOINTS:
        raise ValueError(f"Unsupported SiteTrax resource '{resource}'. Use sitetrax_schema_tool to inspect allowed resources.")
    return key


def get_sitetrax_schema(resource: str | None = None) -> dict:
    """Return the read-only SiteTrax endpoint registry exposed to the agent."""
    if resource:
        key = _resource_key(resource)
        return {"resource": key, "schema": _ENDPOINTS[key].public_dict()}
    return {
        "resources": {key: spec.public_dict() for key, spec in _ENDPOINTS.items()},
        "rules": {
            "access": "read-only allowlist",
            "date_window": "Use full ISO 8601 date_from/date_to; these map to endpoint date filters.",
            "payloads": "Rows preserve complete redacted SiteTrax payloads under raw_payload when available.",
        },
    }


def _coerce_filters(filters) -> dict:
    if not filters:
        return {}
    if isinstance(filters, str):
        try:
            parsed = json.loads(filters)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return filters if isinstance(filters, dict) else {}


def _fill_path(spec: SiteTraxEndpointSpec, filters: dict) -> tuple[str, dict]:
    params = dict(filters)
    path = spec.path
    if "{id}" in path:
        raw_id = params.pop("id", None) or params.pop("asset_id", None) or params.pop("video_id", None) or params.pop("project_id", None)
        if raw_id in (None, ""):
            raise ValueError(f"Resource '{spec.resource}' requires an id filter.")
        path = path.replace("{id}", str(raw_id))
    return path, params


def _apply_common_filters(
    spec: SiteTraxEndpointSpec,
    filters: dict,
    search: str | None,
    date_from: str | None,
    date_to: str | None,
    ordering: str | None,
) -> tuple[dict, dict]:
    params: dict = {}
    ignored: dict = {}
    allowed = set(spec.allowed_filters)
    filters = dict(filters or {})

    facility = filters.pop("facility", None) or filters.pop("location", None)
    if facility and ("facility" in allowed or "location" in allowed or "bucket__in" in allowed):
        buckets = resolve_buckets(str(facility))
        if buckets:
            params["bucket__in"] = ",".join(str(b) for b in buckets)
        else:
            ignored["facility"] = f"No bucket resolved for {facility}"

    container = filters.pop("container_id", None)
    if container and spec.id_filter == "Text":
        params["Text"] = container
    elif container and spec.search_param:
        search = search or str(container)
    elif container:
        ignored["container_id"] = "Resource does not support container_id"

    status_code = filters.pop("status_code", None)
    if status_code and "Status_Code__in" in allowed:
        params["Status_Code__in"] = status_code
    elif status_code:
        ignored["status_code"] = "Resource does not support status_code"

    for key, value in filters.items():
        if key in allowed and value not in (None, ""):
            params[key] = value
        elif key not in {"id", "asset_id", "video_id", "project_id"}:
            ignored[key] = "Unsupported filter for this resource"

    if search and spec.search_param:
        params[spec.search_param] = search
    elif search and not spec.search_param:
        ignored["search"] = "Resource does not support free-text search"

    if spec.date_field:
        if date_from:
            params[f"{spec.date_field}__gte"] = date_from
        if date_to:
            params[f"{spec.date_field}__lte"] = date_to
    elif date_from or date_to:
        ignored["date_range"] = "Resource does not support date filtering"

    sort = ordering or spec.default_ordering
    if sort:
        params["ordering"] = sort

    return params, ignored


def _map_resource_row(resource: str, raw) -> dict:
    if not isinstance(raw, dict):
        return {"value": raw}
    if resource in {"assets", "asset_timeline", "asset_detail", "asset_last"}:
        return _map_asset(raw)
    if resource in {"videos", "video_detail"}:
        return _map_video(raw)
    if resource in {"projects", "project_names", "project_detail"}:
        return _map_project(raw)
    if resource in {"auth_self", "feedback_choices"}:
        return _map_identity(raw)
    if resource == "project_last_video":
        return _map_video(raw)
    if resource in {"asset_metrics", "project_metrics", "video_metrics"}:
        return _map_metric(raw)
    row = dict(raw)
    row["raw_payload"] = _redact_payload(raw)
    return row


def _extract_rows(resource: str, data, spec: SiteTraxEndpointSpec) -> list[dict]:
    if resource == "project_metrics":
        return _join_project_metric_rows(data)
    if spec.paginated:
        raw_rows = _unwrap(data)
    elif isinstance(data, list):
        raw_rows = data
    elif isinstance(data, dict):
        raw_rows = data.get("results") if isinstance(data.get("results"), list) else [data]
    else:
        raw_rows = [{"value": data}]
    return [_map_resource_row(resource, row) for row in raw_rows]


def _columns_for(rows: list[dict], preferred: tuple[str, ...]) -> list[dict]:
    keys: list[str] = []
    for key in preferred:
        if any(isinstance(row, dict) and row.get(key) not in (None, "") for row in rows):
            keys.append(key)
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            if key == "raw_payload" or key in keys:
                continue
            if isinstance(value, (dict, list)):
                continue
            keys.append(key)
            if len(keys) >= 12:
                break
        if len(keys) >= 12:
            break
    return [{"key": key, "label": key.replace("_", " ").title()} for key in keys]


def _suggest_visualizations(spec: SiteTraxEndpointSpec, dataset_name: str, rows: list[dict]) -> list[dict]:
    visualizations = []
    for viz_type in spec.visualizations:
        visualizations.append({"type": viz_type, "dataset": dataset_name, "title": spec.description})
    if rows and any(row.get("raw_payload") for row in rows if isinstance(row, dict)):
        visualizations.append({"type": "json", "dataset": dataset_name, "title": "Raw payloads"})
    return visualizations


def _reference_for_resource(spec: SiteTraxEndpointSpec) -> list[dict]:
    refs = [{
        "label": "SiteTrax API output fields",
        "url": "https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-output-json",
    }]
    if spec.entity_type == "video":
        refs.append({"label": "SiteTrax video input", "url": "https://docs.sitetrax.io/books/sitetraxio-api/page/sitetraxio-api-input-video"})
    elif spec.entity_type == "project":
        refs.append({"label": "SiteTrax products", "url": "https://sitetrax.io/products/"})
    return refs


def _enrich_related(resource: str, rows: list[dict], include_related) -> list[dict]:
    if not include_related:
        return rows
    if isinstance(include_related, str):
        include = {part.strip() for part in include_related.split(",") if part.strip()}
    elif include_related is True:
        include = {"all"}
    elif isinstance(include_related, list):
        include = {str(part) for part in include_related}
    else:
        include = set()
    if not include:
        return rows

    enriched = []
    for row in rows:
        next_row = dict(row)
        if resource in {"videos", "video_detail"} and ({"all", "playback_url", "video_playback_url"} & include) and row.get("id"):
            try:
                next_row["url"] = get_video_url(row["id"])
                next_row["video_id"] = row["id"]
            except Exception:
                next_row["url"] = None
        if resource in {"assets", "asset_timeline", "asset_detail", "asset_last"}:
            vid = row.get("video_name")
            if vid and ({"all", "video", "video_detail"} & include):
                detail = get_video_detail(vid) or {}
                next_row["video"] = detail
            if vid and ({"all", "playback_url", "video_playback_url"} & include):
                try:
                    next_row["video_url"] = get_video_url(vid)
                except Exception:
                    next_row["video_url"] = None
        enriched.append(next_row)
    return enriched


def sitetrax_query(
    resource: str,
    filters: dict | str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    ordering: str | None = None,
    limit: int = 50,
    include_related=None,
) -> dict:
    """Schema-guided read-only SiteTrax query returning a generic visualization envelope."""
    key = _resource_key(resource)
    spec = _ENDPOINTS[key]
    filters_dict = _coerce_filters(filters)
    path, remaining_filters = _fill_path(spec, filters_dict)
    params, ignored_filters = _apply_common_filters(spec, remaining_filters, search, date_from, date_to, ordering)
    bounded_limit = max(1, min(int(limit or 50), 250))

    if spec.paginated:
        page_result = _fetch_pages_with_meta(path, params, max_results=bounded_limit, timeout=_FACILITY_TIMEOUT)
        rows = [_map_resource_row(key, row) for row in page_result["rows"]]
        pagination = page_result["pagination"]
    else:
        data = _request(path, params or None, timeout=_FACILITY_TIMEOUT)
        rows = _extract_rows(key, data, spec)[:bounded_limit]
        pagination = {
            "paginated": False,
            "pages_fetched": 1 if rows else 0,
            "rows_returned": len(rows),
            "total_available": len(rows),
            "limit": bounded_limit,
            "cap_reached": False,
            "has_more": False,
            "progress": {
                "status": "complete",
                "label": f"Fetched {len(rows)} row{'s' if len(rows) != 1 else ''}",
                "percent": 100 if rows else None,
                "steps": [{
                    "page": 1,
                    "rows_in_page": len(rows),
                    "rows_fetched": len(rows),
                    "expected_rows": len(rows),
                    "percent": 100 if rows else None,
                }] if rows else [],
            },
        }

    rows = _enrich_related(key, rows, include_related)
    dataset_name = key
    columns = _columns_for(rows, spec.columns)
    dataset = {
        "name": dataset_name,
        "label": spec.resource.replace("_", " ").title(),
        "entity_type": spec.entity_type,
        "columns": columns,
        "rows": rows,
        "count": len(rows),
    }
    return {
        "answer": f"Found {len(rows)} {spec.entity_type} record{'s' if len(rows) != 1 else ''} for {spec.resource}.",
        "datasets": [dataset],
        "visualizations": _suggest_visualizations(spec, dataset_name, rows),
        "references": _reference_for_resource(spec),
        "provenance": {
            "resource": key,
            "endpoint": path,
            "params": params,
            "ignored_filters": ignored_filters,
            "date_from": date_from,
            "date_to": date_to,
            "limit": bounded_limit,
            "returned": len(rows),
            "access": "read-only allowlist",
        },
        "pagination": pagination,
        "progress": pagination["progress"],
    }


def search_videos(
    query: str | None = None,
    limit: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
    facility: str | None = None,
    hours_back: int | None = None,
) -> list[dict]:
    """Search/list videos (GET /sv/videos/), newest first.

    Supports:
      - query: free-text search
      - date_from / date_to: ISO datetime strings
      - hours_back: deprecated compatibility fallback; prefer date_from/date_to.
      - facility: facility name (resolved to server-side bucket__in filter)
    """
    params: dict = {"page": 1, "ordering": "-created_at"}
    if query:
        params["search"] = query
    if hours_back is not None and not date_from and not date_to:
        now = datetime.datetime.now(datetime.timezone.utc)
        date_from = _iso_z(now - datetime.timedelta(hours=max(1, int(hours_back))))
        date_to = _iso_z(now)
    if date_from:
        params["created_at__gte"] = date_from
    if date_to:
        params["created_at__lte"] = date_to
    if facility:
        buckets = resolve_buckets(facility)
        if buckets:
            params["bucket__in"] = ",".join(str(b) for b in buckets)
    videos = [_map_video(v) for v in _fetch_all_pages(
        "/sv/videos/",
        params,
        max_results=max(1, min(int(limit or 10), 250)),
        timeout=_FACILITY_TIMEOUT,
    )]
    return videos[:limit]


def get_video_url(video_id) -> str | None:
    """Temporary (5-min) playback URL for a video (GET /sv/video/{id}/get_url/)."""
    data = _request(f"/sv/video/{video_id}/get_url/", None)
    return data.get("object_url") if isinstance(data, dict) else None


def get_container_video(
    container_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    hours_back: int | None = None,
) -> dict | None:
    """The most recent video clip for a container (timeline -> video id -> playback URL)."""
    try:
        timeline = get_asset_timeline(container_id)
    except Exception:
        return None
    from datetime import datetime, timezone, timedelta
    cutoff = None
    if hours_back is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    for det in timeline:
        if cutoff is not None:
            try:
                dt = datetime.fromisoformat(str(det.get("datetime", "")).replace("Z", "+00:00"))
                if dt < cutoff:
                    continue
            except Exception:
                pass
        if not _within_date_range(det.get("datetime"), date_from=date_from, date_to=date_to):
            continue
        vid = det.get("video_name")
        if isinstance(vid, dict):
            vid = vid.get("id") or vid.get("name")
        if vid:
            try:
                url = get_video_url(vid)
            except Exception:
                url = None
            detail = get_video_detail(vid) or {}
            return {
                **detail,
                "container_id": container_id,
                "video_id": vid,
                "url": url,
                "thumbnail_url": detail.get("thumbnail_url") or detail.get("thumbnail") or detail.get("thumbnail_md") or detail.get("thumbnail_hr"),
                "thumbnail": detail.get("thumbnail") or detail.get("thumbnail_md") or detail.get("thumbnail_hr"),
                "detected_at": det.get("datetime"),
                "facility": det.get("location") or detail.get("facility"),
                "asset": det,
                "video": detail,
            }
    return None


def get_container_videos(
    container_id: str,
    limit: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
    hours_back: int | None = None,
) -> list[dict]:
    """All video clips for a container across its timeline."""
    try:
        timeline = get_asset_timeline(container_id)
    except Exception:
        return []
    from datetime import datetime, timezone, timedelta
    cutoff = None
    if hours_back is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    results = []
    seen_vids = set()
    for det in timeline:
        if cutoff is not None:
            try:
                dt = datetime.fromisoformat(str(det.get("datetime", "")).replace("Z", "+00:00"))
                if dt < cutoff:
                    continue
            except Exception:
                pass
        if not _within_date_range(det.get("datetime"), date_from=date_from, date_to=date_to):
            continue
        vid = det.get("video_name")
        if isinstance(vid, dict):
            vid = vid.get("id") or vid.get("name")
        if not vid or vid in seen_vids:
            continue
        seen_vids.add(vid)
        try:
            url = get_video_url(vid)
        except Exception:
            url = None
        detail = get_video_detail(vid) or {}
        results.append({
            **detail,
            "container_id": container_id,
            "video_id": vid,
            "url": url,
            "thumbnail_url": detail.get("thumbnail_url") or detail.get("thumbnail") or detail.get("thumbnail_md") or detail.get("thumbnail_hr"),
            "thumbnail": detail.get("thumbnail") or detail.get("thumbnail_md") or detail.get("thumbnail_hr"),
            "detected_at": det.get("datetime"),
            "facility": det.get("location") or detail.get("facility"),
            "asset": det,
            "video": detail,
        })
        if len(results) >= limit:
            break
    return results

def get_container_image(
    container_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    hours_back: int | None = None,
) -> dict | None:
    """The most recent image for a container (timeline -> asset_image URL)."""
    try:
        timeline = get_asset_timeline(container_id)
    except Exception:
        return None
    from datetime import datetime, timezone, timedelta
    cutoff = None
    if hours_back is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    for det in timeline:
        if cutoff is not None:
            try:
                dt = datetime.fromisoformat(str(det.get("datetime", "")).replace("Z", "+00:00"))
                if dt < cutoff:
                    continue
            except Exception:
                pass
        if not _within_date_range(det.get("datetime"), date_from=date_from, date_to=date_to):
            continue
        image_url = det.get("asset_image") or det.get("image_url") or det.get("thumbnail_url")
        asset_id = det.get("id")
        if not image_url and asset_id is not None:
            detail = get_asset_detail(asset_id) or {}
            image_url = detail.get("asset_image") or detail.get("image_url") or detail.get("thumbnail_url") or detail.get("thumbnail")
        if image_url:
            return {
                **det,
                "container_id": container_id,
                "asset_id": asset_id,
                "image_url": image_url,
                "asset_image": image_url,
                "thumbnail_url": det.get("thumbnail_url") or det.get("asset_image_lr") or image_url,
                "detected_at": det.get("datetime"),
                "facility": det.get("location"),
                "status_code": det.get("status_code"),
                "heading": det.get("asset_heading") or None,
                "asset": det,
            }
    return None


def get_container_images(
    container_id: str,
    limit: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
    hours_back: int | None = None,
) -> list[dict]:
    """All images for a container across its detection timeline."""
    try:
        timeline = get_asset_timeline(container_id)
    except Exception:
        return []
    from datetime import datetime, timezone, timedelta
    cutoff = None
    if hours_back is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    results = []
    seen_ids = set()
    for det in timeline:
        if cutoff is not None:
            try:
                dt = datetime.fromisoformat(str(det.get("datetime", "")).replace("Z", "+00:00"))
                if dt < cutoff:
                    continue
            except Exception:
                pass
        if not _within_date_range(det.get("datetime"), date_from=date_from, date_to=date_to):
            continue
        image_url = det.get("asset_image") or det.get("image_url") or det.get("thumbnail_url")
        asset_id = det.get("id")
        if not image_url and asset_id is not None:
            detail = get_asset_detail(asset_id) or {}
            image_url = detail.get("asset_image") or detail.get("image_url") or detail.get("thumbnail_url") or detail.get("thumbnail")
        if not image_url or asset_id in seen_ids:
            continue
        seen_ids.add(asset_id)
        results.append({
            **det,
            "container_id": container_id,
            "asset_id": asset_id,
            "image_url": image_url,
            "asset_image": image_url,
            "thumbnail_url": det.get("thumbnail_url") or det.get("asset_image_lr") or image_url,
            "detected_at": det.get("datetime"),
            "facility": det.get("location"),
            "status_code": det.get("status_code"),
            "heading": det.get("asset_heading") or None,
            "asset": det,
        })
        if len(results) >= limit:
            break
    return results


def get_video_metrics(
    facility: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Aggregated video metrics (GET /sv/videos/metrics/). Returns a single totals dict."""
    params: dict = {}
    if facility:
        buckets = resolve_buckets(facility)
        if buckets:
            params["bucket__in"] = ",".join(str(b) for b in buckets)
    if date_from:
        params["created_at__gte"] = date_from
    if date_to:
        params["created_at__lte"] = date_to
    data = _request("/sv/videos/metrics/", params, timeout=_FACILITY_TIMEOUT)
    # The API returns a single totals dict, not a list of rows
    if isinstance(data, dict):
        return _map_metric(data)
    return {}


# ── Asset detail / export / project ────────────────────────────────────────

def get_asset_detail(asset_id: int | str) -> dict | None:
    """Single asset detail (GET /sv/assets/{id})."""
    try:
        data = _request(f"/sv/assets/{asset_id}/", None)
    except Exception:
        return None
    return _map_asset(data) if isinstance(data, dict) else None


def export_assets(
    facility: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Export assets payload (GET /assets/export/). Returns raw export data."""
    params: dict = {}
    if facility:
        buckets = resolve_buckets(facility)
        if buckets:
            params["bucket__in"] = ",".join(str(b) for b in buckets)
    if date_from:
        params["created_at__gte"] = date_from
    if date_to:
        params["created_at__lte"] = date_to
    return _request("/assets/export/", params)


def get_project_detail(project_id: int | str) -> dict | None:
    """Single project detail (GET /sv/project/{id}/)."""
    try:
        return _request(f"/sv/project/{project_id}/", None)
    except Exception:
        return None


def get_project_integrations(project_id: int | str) -> dict | None:
    """Project integrations/datatools (GET /sv/project/{id}/datatools/)."""
    try:
        return _request(f"/sv/project/{project_id}/datatools/", None)
    except Exception:
        return None


def get_video_detail(video_id: int | str) -> dict | None:
    """Single video detail (GET /sv/video/{id}/)."""
    try:
        data = _request(f"/sv/video/{video_id}/", None)
    except Exception:
        return None
    return _map_video(data) if isinstance(data, dict) else None


def get_auth_self() -> dict:
    """Current authenticated SiteTrax user/profile (GET /auth/self/)."""
    data = _request("/auth/self/", None)
    return _redact_payload(data) if isinstance(data, dict) else {"value": data}


def get_feedback_choices() -> list[dict]:
    """Read-only feedback choices (GET /feedback_choices/)."""
    data = _request("/feedback_choices/", None)
    return [_redact_payload(row) for row in _unwrap(data)]


def get_project_last_video(project_id: int | str) -> dict | None:
    """Most recent video for a project (GET /sv/project/{id}/get_last_video/)."""
    data = _request(f"/sv/project/{project_id}/get_last_video/", None, timeout=_FACILITY_TIMEOUT)
    return _map_video(data) if isinstance(data, dict) else None


def sitetrax_image_url_to_base64(image_url: str, max_bytes: int = 5_000_000) -> dict:
    """Fetch a SiteTrax-hosted image and return a data URL for clients with strict CSP.

    Only HTTPS URLs whose hostname is sitetrax.io or a subdomain of sitetrax.io are
    accepted. The response is capped to avoid turning this into a general proxy.
    """
    parsed = urlparse(image_url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "sitetrax.io" or host.endswith(".sitetrax.io")):
        raise ValueError("Only https image URLs hosted on sitetrax.io subdomains are allowed")

    _ensure_access_token()
    headers = {"Accept": "image/*", "Authorization": f"Bearer {_access_token}"}
    resp_ctx = httpx.stream("GET", image_url, headers=headers, timeout=_TIMEOUT, follow_redirects=True)
    with resp_ctx as resp:
        if resp.status_code == 401:
            with _token_lock:
                _refresh_access()
            headers["Authorization"] = f"Bearer {_access_token}"
            resp.close()
            with httpx.stream("GET", image_url, headers=headers, timeout=_TIMEOUT, follow_redirects=True) as retry:
                retry.raise_for_status()
                content_type = (retry.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
                if not content_type.startswith("image/"):
                    raise ValueError(f"URL did not return an image content-type: {content_type or 'unknown'}")
                chunks = []
                size = 0
                for chunk in retry.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError(f"Image exceeds max_bytes limit ({max_bytes})")
                    chunks.append(chunk)
                raw = b"".join(chunks)
                encoded = base64.b64encode(raw).decode("ascii")
                return {
                    "source_url": image_url,
                    "content_type": content_type,
                    "size_bytes": len(raw),
                    "base64": encoded,
                    "data_url": f"data:{content_type};base64,{encoded}",
                }
        resp.raise_for_status()
        content_type = (resp.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if not content_type.startswith("image/"):
            raise ValueError(f"URL did not return an image content-type: {content_type or 'unknown'}")
        chunks = []
        size = 0
        for chunk in resp.iter_bytes():
            size += len(chunk)
            if size > max_bytes:
                raise ValueError(f"Image exceeds max_bytes limit ({max_bytes})")
            chunks.append(chunk)

    raw = b"".join(chunks)
    encoded = base64.b64encode(raw).decode("ascii")
    return {
        "source_url": image_url,
        "content_type": content_type,
        "size_bytes": len(raw),
        "base64": encoded,
        "data_url": f"data:{content_type};base64,{encoded}",
    }


# ── Metrics (read-only) ─────────────────────────────────────────────────────

def facility_metrics(
    facility: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    days: int | None = None,
) -> list[dict]:
    """Daily asset counts for one facility (resolved to bucket) or all (GET /sv/assets/metrics/)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    params: dict = {"page": 1}
    if date_from:
        params["created_at__gte"] = date_from
    elif days:
        params["created_at__gte"] = _iso_z(now - datetime.timedelta(days=days))
    if date_to:
        params["created_at__lte"] = date_to
    elif days:
        params["created_at__lte"] = _iso_z(now)
    if facility:
        buckets = resolve_buckets(facility)
        if buckets:
            params["bucket__in"] = ",".join(str(b) for b in buckets)
    return [_map_metric(row) for row in _fetch_all_pages("/sv/assets/metrics/", params, max_results=500, timeout=_FACILITY_TIMEOUT)]


def project_metrics(
    date_from: str | None = None,
    date_to: str | None = None,
    days: int | None = None,
) -> list[dict]:
    """Per-facility daily counts across all projects (GET /sv/assets/project_metrics/)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    params = {"page": 1}
    if date_from:
        params["created_at__gte"] = date_from
    elif days:
        params["created_at__gte"] = _iso_z(now - datetime.timedelta(days=days))
    if date_to:
        params["created_at__lte"] = date_to
    elif days:
        params["created_at__lte"] = _iso_z(now)
    data = _request("/sv/assets/project_metrics/", params, timeout=_FACILITY_TIMEOUT)
    return _join_project_metric_rows(data)


# ── Power tools ─────────────────────────────────────────────────────────────

def query_sitetrax(
    entity_type: str,
    query: str | None = None,
    facility: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status_codes: str | None = None,
    limit: int = 50,
) -> dict:
    """Power tool: unified query across assets, videos, projects, or metrics.
    entity_type: 'assets' | 'videos' | 'projects' | 'metrics'
    Returns unified shape: { count, results }
    """
    entity_type = (entity_type or "assets").lower()
    params: dict = {"page": 1}
    if facility:
        buckets = resolve_buckets(facility)
        if buckets:
            params["bucket__in"] = ",".join(str(b) for b in buckets)
    if date_from:
        params["created_at__gte"] = date_from
    if date_to:
        params["created_at__lte"] = date_to
    if query:
        params["search"] = query

    if entity_type == "assets":
        if status_codes:
            params["Status_Code__in"] = status_codes
        page_result = _fetch_pages_with_meta("/sv/assets/", params, max_results=limit)
        results = [_map_asset(r) for r in page_result["rows"]]
        return {"count": len(results), "results": results, "entity_type": "assets", "pagination": page_result["pagination"], "progress": page_result["pagination"]["progress"]}

    if entity_type == "videos":
        params["ordering"] = "-created_at"
        page_result = _fetch_pages_with_meta("/sv/videos/", params, max_results=limit)
        results = [_map_video(r) for r in page_result["rows"]]
        return {"count": len(results), "results": results, "entity_type": "videos", "pagination": page_result["pagination"], "progress": page_result["pagination"]["progress"]}

    if entity_type == "projects":
        page_result = _fetch_pages_with_meta("/sv/project/", params, max_results=limit)
        return {"count": len(page_result["rows"]), "results": page_result["rows"], "entity_type": "projects", "pagination": page_result["pagination"], "progress": page_result["pagination"]["progress"]}

    if entity_type == "metrics":
        page_result = _fetch_pages_with_meta("/sv/assets/metrics/", params, max_results=limit)
        results = [_map_metric(r) for r in page_result["rows"]]
        return {"count": len(results), "results": results, "entity_type": "metrics", "pagination": page_result["pagination"], "progress": page_result["pagination"]["progress"]}

    return {"count": 0, "results": [], "entity_type": entity_type}


def get_timeline_with_videos(container_id: str, limit: int = 20) -> list[dict]:
    """Power tool: full detection timeline enriched with video playback URLs."""
    timeline = get_asset_timeline(container_id)
    results = []
    for det in timeline[:limit]:
        vid = det.get("video_name")
        if isinstance(vid, dict):
            vid = vid.get("id") or vid.get("name")
        enriched = dict(det)
        if vid:
            try:
                enriched["video_url"] = get_video_url(vid)
            except Exception:
                enriched["video_url"] = None
        results.append(enriched)
    return results


def facility_overview(
    facility: str,
    date_from: str | None = None,
    date_to: str | None = None,
    days: int | None = None,
) -> dict:
    """Power tool: holistic facility snapshot using real endpoints only.
    Combines asset metrics, project metrics, recent activity, and last scan.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    if not date_from and days:
        date_from = _iso_z(now - datetime.timedelta(days=days))
    if not date_to and days:
        date_to = _iso_z(now)

    buckets = resolve_buckets(facility)
    bucket_param = ",".join(str(b) for b in buckets) if buckets else None
    base_params = {"page": 1}
    if date_from:
        base_params["created_at__gte"] = date_from
    if date_to:
        base_params["created_at__lte"] = date_to
    if bucket_param:
        base_params["bucket__in"] = bucket_param

    # Asset metrics
    try:
        metrics_data = _request("/sv/assets/metrics/", dict(base_params), timeout=_FACILITY_TIMEOUT)
        metrics = metrics_data.get("results", [metrics_data]) if isinstance(metrics_data, dict) else []
    except Exception:
        metrics = []

    # Project metrics
    try:
        pm_data = _request("/sv/assets/project_metrics/", dict(base_params), timeout=_FACILITY_TIMEOUT)
        project_metrics = pm_data.get("results", [pm_data]) if isinstance(pm_data, dict) else []
    except Exception:
        project_metrics = []

    # Recent activity
    try:
        recent = get_facility_recent(facility, date_from=date_from, date_to=date_to)[:10]
    except Exception:
        recent = []

    # Last scan
    try:
        last = get_facility_last_scan(facility)
    except Exception:
        last = None

    # Video metrics
    try:
        vm_data = get_video_metrics(facility=facility, date_from=date_from, date_to=date_to)
        video_metrics = vm_data.get("results", [vm_data]) if isinstance(vm_data, dict) else []
    except Exception:
        video_metrics = []

    # Volume from metrics
    total_scans = 0
    if metrics and isinstance(metrics[0], dict):
        total_scans = metrics[0].get("total_containers", 0) or metrics[0].get("count", 0) or 0

    return {
        "facility": facility,
        "date_from": date_from,
        "date_to": date_to,
        "api_filters": {
            **({"created_at__gte": date_from} if date_from else {}),
            **({"created_at__lte": date_to} if date_to else {}),
        },
        "metrics": metrics,
        "project_metrics": project_metrics,
        "recent_activity": recent,
        "last_scan": last,
        "video_metrics": video_metrics,
        "summary": {
            "total_scans": total_scans,
            "recent_scans": len(recent),
            "has_data": bool(metrics or recent or last),
        }
    }
