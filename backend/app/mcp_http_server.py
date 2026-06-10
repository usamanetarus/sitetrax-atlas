"""SiteTrax Remote MCP Server — HTTP transport with OAuth 2.0.

Exposes the same SiteTrax tools as mcp_server.py (stdio) but over Streamable HTTP
so it can be registered as a remote MCP server in the Anthropic connector (claude.ai)
and any other MCP-over-HTTP client.

OAuth flow (Authorization Code + PKCE, as required by the MCP spec):
  1. Client (claude.ai) registers via POST /register  (dynamic client registration)
  2. Client redirects user to GET /authorize
  3. User is sent to GET /oauth/login?session=<jwt> — an HTML passkey form
  4. User enters MCP_CLIENT_SECRET → POST /oauth/login redirects to redirect_uri?code=...
  5. Client exchanges code at POST /token → {access_token, refresh_token}
  6. Client uses Bearer <access_token> on MCP calls to POST /mcp

Required env vars:
  MCP_SERVER_URL      — public HTTPS base URL of this server
                        e.g. https://sitetrax-mcp-abc123-uc.a.run.app
  MCP_CLIENT_SECRET   — passkey users enter to obtain tokens
  MCP_TOKEN_TTL       — access token lifetime in seconds (default 3600)

Run standalone (local):
  cd backend
  MCP_SERVER_URL=http://localhost:9000 MCP_CLIENT_SECRET=secret python -m app.mcp_http_server

Deploy as Cloud Run service (see deploy.sh / Dockerfile.mcp):
  Listens on PORT (Cloud Run sets this); serve via `uvicorn app.mcp_http_server:asgi_app`
"""

from __future__ import annotations

import sys
from pathlib import Path as _Path

# ── Path bootstrap ──────────────────────────────────────────────────────────────
_backend_root = str(_Path(__file__).resolve().parents[1])
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from dotenv import load_dotenv
load_dotenv(_Path(__file__).resolve().parents[1] / ".env")

import hashlib
import html
import json
import logging
import os
import secrets
import time
from typing import Any

import jwt as _jwt

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

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

logger = logging.getLogger("sitetrax.mcp_http")

# ── Config ─────────────────────────────────────────────────────────────────────

_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:9000").rstrip("/")
_CLIENT_SECRET = os.environ.get("MCP_CLIENT_SECRET", "")
_TOKEN_TTL = int(os.environ.get("MCP_TOKEN_TTL", "3600"))

if not _CLIENT_SECRET:
    logger.warning("MCP_CLIENT_SECRET is not set — all login attempts will be rejected")


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

# ── Stateless JWT helpers ──────────────────────────────────────────────────────
# Cloud Run can route each request to a different instance, so in-memory stores
# don't work.  We encode all OAuth state in signed JWTs so every instance can
# verify tokens without shared storage.

_SIGNING_KEY = hashlib.sha256(_CLIENT_SECRET.encode()).digest() if _CLIENT_SECRET else b""
_SESSION_TTL = 600   # login sessions expire after 10 minutes
_CODE_TTL = 300      # auth codes expire after 5 minutes


def _now() -> int:
    return int(time.time())


def _encode_session(client_id: str, params: AuthorizationParams) -> str:
    """Return a signed JWT that encodes the authorization session."""
    payload = {
        "typ": "session",
        "cid": client_id,
        "uri": str(params.redirect_uri),
        "uri_ex": params.redirect_uri_provided_explicitly,
        "st": params.state,
        "cc": params.code_challenge,
        "scp": params.scopes,
        "exp": _now() + _SESSION_TTL,
    }
    return _jwt.encode(payload, _SIGNING_KEY, algorithm="HS256")


def _decode_session(token: str) -> dict[str, Any] | None:
    try:
        return _jwt.decode(token, _SIGNING_KEY, algorithms=["HS256"])
    except _jwt.ExpiredSignatureError:
        return None
    except Exception:
        return None


def _make_auth_code_jwt(
    client_id: str,
    scopes: list[str] | None,
    code_challenge: str | None,
    redirect_uri: str | None,
    redirect_uri_provided_explicitly: bool | None,
) -> str:
    """Return a JWT that IS the authorization code."""
    payload = {
        "typ": "code",
        "cid": client_id,
        "scp": scopes,
        "cc": code_challenge,
        "uri": redirect_uri,
        "uri_ex": redirect_uri_provided_explicitly,
        "exp": _now() + _CODE_TTL,
    }
    return _jwt.encode(payload, _SIGNING_KEY, algorithm="HS256")


def _decode_auth_code(code: str) -> AuthorizationCode | None:
    try:
        payload = _jwt.decode(code, _SIGNING_KEY, algorithms=["HS256"])
        if payload.get("typ") != "code":
            return None
        return AuthorizationCode(
            code=code,
            scopes=payload.get("scp") or [],
            expires_at=payload["exp"],
            client_id=payload["cid"],
            code_challenge=payload.get("cc"),
            redirect_uri=payload.get("uri"),
            redirect_uri_provided_explicitly=payload.get("uri_ex") or False,
        )
    except Exception:
        return None


def _make_access_token_jwt(client_id: str, scopes: list[str] | None) -> str:
    payload = {
        "typ": "at",
        "cid": client_id,
        "scp": scopes,
        "exp": _now() + _TOKEN_TTL,
    }
    return _jwt.encode(payload, _SIGNING_KEY, algorithm="HS256")


def _decode_access_token(token: str) -> AccessToken | None:
    try:
        payload = _jwt.decode(token, _SIGNING_KEY, algorithms=["HS256"])
        if payload.get("typ") != "at":
            return None
        return AccessToken(
            token=token,
            client_id=payload["cid"],
            scopes=payload.get("scp") or [],
            expires_at=payload["exp"],
        )
    except Exception:
        return None


def _make_refresh_token_jwt(client_id: str, scopes: list[str] | None) -> str:
    payload = {
        "typ": "rt",
        "cid": client_id,
        "scp": scopes,
        "exp": _now() + 30 * 24 * 3600,
    }
    return _jwt.encode(payload, _SIGNING_KEY, algorithm="HS256")


def _decode_refresh_token(token: str) -> RefreshToken | None:
    try:
        payload = _jwt.decode(token, _SIGNING_KEY, algorithms=["HS256"])
        if payload.get("typ") != "rt":
            return None
        return RefreshToken(
            token=token,
            client_id=payload["cid"],
            scopes=payload.get("scp") or [],
            expires_at=payload["exp"],
        )
    except Exception:
        return None


# ── OAuth provider ─────────────────────────────────────────────────────────────

class SiteTraxOAuthProvider(OAuthAuthorizationServerProvider):
    """Minimal OAuth 2.0 AS for the SiteTrax MCP server.

    All state is encoded in signed JWTs so this works across any number of
    Cloud Run instances without shared storage.
    """

    # ── Client registration ────────────────────────────────────────────────────

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        # Hard-coded fallback: Anthropic connector client (Cloud Run instances
        # don't share memory, so in-memory _clients is lost between requests).
        if client_id == "2ab75513-77bb-4c46-a1cf-39af54803b69":
            return OAuthClientInformationFull(
                client_id="2ab75513-77bb-4c46-a1cf-39af54803b69",
                client_name="SiteTrax Anthropic",
                redirect_uris=["https://claude.ai/api/mcp/auth_callback"],
                token_endpoint_auth_method="none",
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                scope="sitetrax:read",
                client_id_issued_at=0,
            )
        return None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        # Stateless — we don't store registrations.  Pre-register clients instead.
        logger.info("Registration request received for: %s", client_info.client_name)

    # ── Authorization ──────────────────────────────────────────────────────────

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        """Create a stateless session JWT and redirect to the login form."""
        session_jwt = _encode_session(client.client_id, params)
        return f"{_SERVER_URL}/oauth/login?session={session_jwt}"

    # ── Authorization code lifecycle ───────────────────────────────────────────

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        code = _decode_auth_code(authorization_code)
        if code and code.client_id == client.client_id and code.expires_at >= _now():
            return code
        return None

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        access_token = _make_access_token_jwt(client.client_id, authorization_code.scopes)
        refresh_token = _make_refresh_token_jwt(client.client_id, authorization_code.scopes)
        logger.info("Issued tokens for client: %s", client.client_id)
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=_TOKEN_TTL,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
            refresh_token=refresh_token,
        )

    # ── Refresh token lifecycle ────────────────────────────────────────────────

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        rt = _decode_refresh_token(refresh_token)
        if rt and rt.client_id == client.client_id:
            exp = rt.expires_at
            if exp is None or exp >= _now():
                return rt
        return None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        effective_scopes = scopes or refresh_token.scopes
        access_token = _make_access_token_jwt(client.client_id, effective_scopes)
        new_refresh = _make_refresh_token_jwt(client.client_id, effective_scopes)
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=_TOKEN_TTL,
            scope=" ".join(effective_scopes) if effective_scopes else None,
            refresh_token=new_refresh,
        )

    # ── Access token verification ──────────────────────────────────────────────

    async def load_access_token(self, token: str) -> AccessToken | None:
        return _decode_access_token(token)

    # ── Revocation ─────────────────────────────────────────────────────────────

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        # Stateless JWTs cannot be revoked individually.  They expire naturally.
        pass


# ── Monkey-patch MCP SDK: allow registration with only authorization_code ──────
# The Anthropic connector sends grant_types=["authorization_code"] but the MCP SDK
# hardcodes a requirement for both authorization_code AND refresh_token.
# This patch removes that restriction so the connector can register successfully.

import mcp.server.auth.handlers.register as _reg_mod

_orig_handle = _reg_mod.RegistrationHandler.handle


async def _patched_handle(self, request: Request) -> Response:
    body = await request.json()
    if isinstance(body, dict) and "grant_types" in body:
        gt = body["grant_types"]
        if isinstance(gt, list) and "authorization_code" in gt and "refresh_token" not in gt:
            body["grant_types"] = list(gt) + ["refresh_token"]
    request._json = lambda: body  # type: ignore[attr-defined]
    return await _orig_handle(self, request)


_reg_mod.RegistrationHandler.handle = _patched_handle

# ── FastMCP server ─────────────────────────────────────────────────────────────

_oauth_provider = SiteTraxOAuthProvider()

mcp = FastMCP(
    "SiteTrax",
    instructions=(
        "SiteTrax logistics platform tools. Query live container/asset data, "
        "facility scan history, daily metrics, and SiteTrax product documentation."
    ),
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "9000")),
    auth_server_provider=_oauth_provider,
    auth=AuthSettings(
        issuer_url=_SERVER_URL,           # type: ignore[arg-type]
        resource_server_url=_SERVER_URL,  # type: ignore[arg-type]
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["sitetrax:read"],
            default_scopes=["sitetrax:read"],
        ),
        revocation_options=RevocationOptions(enabled=True),
    ),
)


# ── OAuth login form (custom route — bypasses auth middleware) ─────────────────

_LOGIN_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SiteTrax MCP — Authorize</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    background:#0a0a10;color:#e2e8f0;min-height:100vh;
    display:flex;align-items:center;justify-content:center}}
  .card{{background:#13131f;border:1px solid rgba(255,255,255,.08);
    border-radius:16px;padding:40px;width:100%;max-width:400px;
    box-shadow:0 20px 60px rgba(0,0,0,.6)}}
  .logo{{font-size:13px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;
    color:#6b7280;margin-bottom:24px}}
  h1{{font-size:22px;font-weight:600;color:#f1f5f9;margin-bottom:8px}}
  p{{font-size:14px;color:#9ca3af;margin-bottom:28px;line-height:1.5}}
  label{{display:block;font-size:13px;font-weight:500;color:#cbd5e1;margin-bottom:6px}}
  input[type=password]{{width:100%;padding:10px 14px;background:#1e1e2e;
    border:1px solid rgba(255,255,255,.12);border-radius:8px;
    color:#f1f5f9;font-size:15px;outline:none;transition:border .2s}}
  input[type=password]:focus{{border-color:#6366f1}}
  .btn{{margin-top:20px;width:100%;padding:11px;background:#6366f1;
    border:none;border-radius:8px;color:#fff;font-size:15px;
    font-weight:600;cursor:pointer;transition:background .2s}}
  .btn:hover{{background:#4f46e5}}
  .err{{margin-top:14px;padding:10px 14px;background:rgba(239,68,68,.15);
    border:1px solid rgba(239,68,68,.3);border-radius:8px;
    font-size:13px;color:#fca5a5}}
</style>
</head>
<body>
<div class="card">
  <div class="logo">SiteTrax.io Atlas Agent</div>
  <h1>Connect to MCP</h1>
  <p>Enter your SiteTrax MCP access secret to authorize this connection.</p>
  <form method="POST">
    <label for="secret">Access secret</label>
    <input id="secret" name="secret" type="password"
           placeholder="••••••••••••" autocomplete="current-password" required>
    {error}
    <button class="btn" type="submit">Authorize</button>
  </form>
</div>
</body>
</html>
"""


@mcp.custom_route("/oauth/login", methods=["GET"])
async def oauth_login_get(request: Request) -> Response:
    """Show the passkey login form."""
    session_id = request.query_params.get("session", "")
    session = _decode_session(session_id)
    if not session:
        return HTMLResponse("<h2>Invalid or expired authorization session.</h2>", status_code=400)
    return HTMLResponse(_LOGIN_HTML.format(error=""))


@mcp.custom_route("/oauth/login", methods=["POST"])
async def oauth_login_post(request: Request) -> Response:
    """Validate passkey; on success, generate auth code and redirect."""
    session_id = request.query_params.get("session", "")
    session = _decode_session(session_id)
    if not session:
        return HTMLResponse("<h2>Invalid or expired authorization session.</h2>", status_code=400)

    form = await request.form()
    entered = str(form.get("secret", ""))

    secret_ok = (
        _CLIENT_SECRET
        and secrets.compare_digest(
            hashlib.sha256(entered.encode()).digest(),
            hashlib.sha256(_CLIENT_SECRET.encode()).digest(),
        )
    )

    if not secret_ok:
        error_html = '<div class="err">Incorrect secret. Please try again.</div>'
        return HTMLResponse(
            _LOGIN_HTML.format(error=error_html),
            status_code=401,
        )

    code_jwt = _make_auth_code_jwt(
        client_id=session["cid"],
        scopes=session.get("scp") or ["sitetrax:read"],
        code_challenge=session.get("cc"),
        redirect_uri=session.get("uri"),
        redirect_uri_provided_explicitly=session.get("uri_ex"),
    )

    redirect = construct_redirect_uri(
        session["uri"],
        code=code_jwt,
        state=session.get("st"),
    )
    return RedirectResponse(redirect, status_code=302)


# ── MCP tools (identical to mcp_server.py) ────────────────────────────────────

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


# ── Health / readiness ─────────────────────────────────────────────────────────

@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(request: Request) -> Response:
    """Cloud Run health check."""
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "ok", "server": _SERVER_URL})


@mcp.custom_route("/", methods=["GET"])
async def root(request: Request) -> Response:
    """Root — show metadata."""
    from starlette.responses import JSONResponse
    return JSONResponse({
        "name": "SiteTrax MCP",
        "version": "1.0.0",
        "endpoints": {
            "mcp": f"{_SERVER_URL}/mcp",
            "oauth_metadata": f"{_SERVER_URL}/.well-known/oauth-authorization-server",
            "register": f"{_SERVER_URL}/register",
            "authorize": f"{_SERVER_URL}/authorize",
            "token": f"{_SERVER_URL}/token",
            "login": f"{_SERVER_URL}/oauth/login",
        },
    })


# ── ASGI app (for `uvicorn app.mcp_http_server:asgi_app`) ─────────────────────

class _RootMcpDispatcher:
    """Wrap the Starlette MCP app so POST / is handled as POST /mcp.

    Some MCP clients (including the Anthropic connector) send messages to /
    instead of /mcp.  This dispatcher transparently rewrites the path before
    the request reaches the Starlette router.
    """
    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("method") == "POST" and scope.get("path") == "/":
            scope["path"] = "/mcp"
            scope["raw_path"] = b"/mcp"
        await self._app(scope, receive, send)


logger.info("Building streamable HTTP app with %d custom routes...", len(mcp._custom_starlette_routes))
asgi_app = _RootMcpDispatcher(mcp.streamable_http_app())
logger.info("ASGI app ready — serving on %s", _SERVER_URL)

# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "9000"))
    logger.info("SiteTrax MCP HTTP server → %s  (port %d)", _SERVER_URL, port)
    uvicorn.run(asgi_app, host="0.0.0.0", port=port)
