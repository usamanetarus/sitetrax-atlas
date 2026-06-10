"""FastAPI server — REST API for the SiteTrax.io Atlas Agent.

Uses ADK 2.x API: Runner + a configured session service + types.Content.
"""

import json
import asyncio
import os
import datetime
import logging
import contextlib
import queue
import threading
import uuid
import re

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv(override=True)  # before app.* imports so .env drives the USE_REAL_API / USE_FIRESTORE selectors
if os.environ.get("K_SERVICE") and "USE_FIRESTORE" not in os.environ:
    os.environ["USE_FIRESTORE"] = "true"

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import create_builder_agent, BUILDER_PROMPT
from app.monitoring import store
from app.monitoring.cloud_scheduler import delete_rule_scheduler_jobs
from app.monitoring.evaluator import evaluate_event, evaluate_recent
from app.data import query_assets, get_latest_scan, DATA_SOURCE
from app.data.sitetrax_client import SiteTraxAuthError, list_projects, get_auth_status, get_video_detail, get_asset_detail, get_auth_self
from app.monitoring.templates import TEMPLATES, TemplateName

logger = logging.getLogger("sitetrax")


def _coerce_tool_response_to_string(response) -> str:
    """Normalize ADK FunctionTool and MCP response wrappers into the actual result text."""
    if isinstance(response, dict):
        if set(response.keys()) == {"result"}:
            return _coerce_tool_response_to_string(response["result"])
        content = response.get("content")
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
                elif hasattr(item, "text") and isinstance(item.text, str):
                    text_parts.append(item.text)
            if text_parts:
                return "\n".join(text_parts)
        if isinstance(response.get("text"), str) and len(response) <= 2:
            return response["text"]
    return response if isinstance(response, str) else json.dumps(response, default=str)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Optional background poller (ENABLE_POLLER=true) — runs an evaluation pass every
    EVAL_INTERVAL_SECONDS. Off by default; on Cloud Run use Cloud Scheduler → /tasks/evaluate.
    """
    task = None
    if os.environ.get("ENABLE_POLLER", "false").lower() == "true":
        interval = int(os.environ.get("EVAL_INTERVAL_SECONDS", "300"))

        async def _loop():
            while True:
                try:
                    fired = await asyncio.to_thread(evaluate_recent)
                    if fired:
                        logger.info("poller fired %d alert(s)", len(fired))
                except Exception as e:
                    logger.warning("poller error: %s", e)
                await asyncio.sleep(interval)

        task = asyncio.create_task(_loop())
        logger.info("Alert poller enabled (every %ss)", interval)
    yield
    if task:
        task.cancel()


app = FastAPI(title="SiteTrax.io Atlas Agent", lifespan=lifespan)

_raw_origins = os.environ.get("ALLOW_ORIGINS", "*")
_allow_origins = ["*"] if _raw_origins == "*" else [o.strip() for o in _raw_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── ADK 2.x setup ───────────────────────────────────────────

builder_agent = create_builder_agent()

if os.environ.get("USE_FIRESTORE", "false").lower() == "true":
    try:
        from app.monitoring.firestore_session_service import FirestoreSessionService
        session_service = FirestoreSessionService()
        SESSION_STORE = "firestore"
        logger.info("Using FirestoreSessionService for serverless, durable sessions")
    except Exception as e:
        raise RuntimeError(
            "USE_FIRESTORE=true but FirestoreSessionService could not initialize. "
            "For Cloud Run/stateless deployments, fix Firestore/API/IAM configuration "
            f"instead of falling back to local storage. Cause: {e}"
        ) from e
else:
    session_service = InMemorySessionService()
    SESSION_STORE = "memory"
    logger.info("Using InMemorySessionService for local non-durable sessions")

# Memory service for cross-session context.
# Instantiate lazily so Firestore's async client is created while the event loop is alive.
memory_service = None


def get_memory_service():
    global memory_service
    if os.environ.get("USE_MEMORY_SERVICE", "true").lower() in {"0", "false", "no"}:
        from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
        return InMemoryMemoryService()
    if os.environ.get("USE_FIRESTORE", "false").lower() == "true" or os.environ.get("K_SERVICE"):
        try:
            from google.adk.integrations.firestore.firestore_memory_service import FirestoreMemoryService
            logger.info("Using FirestoreMemoryService for persistent cross-session memory")
            return FirestoreMemoryService()
        except Exception as e:
            from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
            logger.warning("FirestoreMemoryService unavailable, falling back to InMemoryMemoryService: %s", e)
            return InMemoryMemoryService()
    if memory_service is not None:
        return memory_service
    try:
        from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
        memory_service = InMemoryMemoryService()
        logger.info("Using InMemoryMemoryService for local cross-session memory")
    except Exception as e:
        logger.warning("Memory service unavailable: %s", e)
        raise
    return memory_service

# Artifact service for structured reports/downloads
try:
    from app.monitoring.firestore_artifact_service import FirestoreArtifactService
    artifact_service = FirestoreArtifactService()
    logger.info("Using FirestoreArtifactService for durable artifacts")
except Exception as e:
    from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
    artifact_service = InMemoryArtifactService()
    logger.warning("FirestoreArtifactService unavailable, falling back to InMemoryArtifactService: %s", e)


def create_runner() -> Runner:
    """Create a Runner for each request. Uses the configured shared session service.
    auto_create_session=True handles get-or-create semantics — if the session
    already exists for the given session_id, it is reused. No "session already
    exists" error is raised.
    """
    return Runner(
        app_name="sitetrax_coordinator",
        agent=builder_agent,
        session_service=session_service,
        memory_service=get_memory_service(),
        artifact_service=artifact_service,
        auto_create_session=True,
    )


# ── Request / Response models ──────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str = "default"
    history: list[dict] | None = None


class ChatResponse(BaseModel):
    text: str
    session_id: str
    tool_results: list[dict] | None = None


class SimulateEventRequest(BaseModel):
    container_id: str = Field(..., min_length=1, max_length=20)
    location: str = Field(..., min_length=1, max_length=200)
    dwell_hours: float | None = Field(default=None, ge=0)
    rule_id: str | None = Field(default=None)


# ── Endpoints ───────────────────────────────────────────────

@app.get("/health")
async def health():
    # Auth is Vertex AI via Application Default Credentials (ADC).
    return {
        "status": "ok",
        "agent": builder_agent.name,
        "backend": "vertex",
        "data_source": DATA_SOURCE,
        "session_store": SESSION_STORE,
        "session_persistent": SESSION_STORE == "firestore",
        "gemini_configured": bool(os.environ.get("GOOGLE_CLOUD_PROJECT")),
    }


def _account_summary() -> dict | None:
    """Non-sensitive identity of the authenticated SiteTrax account (GET /auth/self/).
    Best-effort: returns None if the call fails so it never breaks the health check."""
    try:
        s = get_auth_self()
    except Exception:
        return None
    if not s:
        return None
    name = " ".join(p for p in (s.get("first_name"), s.get("last_name")) if p) or s.get("name")
    return {
        "id": s.get("id"),
        "email": s.get("email"),
        "name": name or None,
        "is_staff": s.get("is_staff"),
    }


@app.get("/health/data")
async def data_health():
    """Check whether the configured SiteTrax data source is reachable."""
    if DATA_SOURCE != "real_api":
        return {"status": "ok", "data_source": DATA_SOURCE, "reachable": True}
    auth_status = get_auth_status()
    try:
        projects = await asyncio.to_thread(list_projects)
        account = await asyncio.to_thread(_account_summary)
    except SiteTraxAuthError as e:
        return {
            "status": "auth_error",
            "data_source": DATA_SOURCE,
            "reachable": False,
            "auth": auth_status,
            "detail": str(e),
        }
    except Exception as e:
        return {
            "status": "error",
            "data_source": DATA_SOURCE,
            "reachable": False,
            "auth": auth_status,
            "detail": str(e),
        }
    return {
        "status": "ok",
        "data_source": DATA_SOURCE,
        "reachable": True,
        "auth": get_auth_status(),
        "account": account,
        "facilities": len(projects),
    }


@app.get("/video/{video_id}")
async def video_detail(video_id: str):
    """Expose a single video record for UI hydration (thumbnail, metadata, etc.)."""
    try:
        detail = await asyncio.to_thread(get_video_detail, video_id)
    except SiteTraxAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unable to load video {video_id}") from e
    if not detail:
        raise HTTPException(status_code=404, detail="Video not found")
    return detail


@app.get("/asset/{asset_id}")
async def asset_detail(asset_id: str):
    """Expose a single asset record for UI hydration (asset image, metadata, etc.)."""
    try:
        detail = await asyncio.to_thread(get_asset_detail, asset_id)
    except SiteTraxAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unable to load asset {asset_id}") from e
    if not detail:
        raise HTTPException(status_code=404, detail="Asset not found")
    return detail


_AUTH_ERR_HINTS = (
    "reauthentication is needed",
    "application-default login",
    "default credentials were not found",
    "could not automatically determine credentials",
    "invalid_grant",
)


def _is_auth_error(exc: Exception) -> bool:
    """True if the exception looks like an expired/missing ADC credential."""
    msg = str(exc).lower()
    return any(hint in msg for hint in _AUTH_ERR_HINTS)


_CONTAINER_RE = re.compile(r"\b[A-Z]{4}\d{7}\b", re.IGNORECASE)
_FALLBACK_FACILITY_ALIASES = {
    "Utah Intermodal Ramp": "Utah Intermodal Ramp",
    "Utah": "Utah Intermodal Ramp",
}


def _normalize_container(value: str | None) -> str | None:
    match = _CONTAINER_RE.search(value or "")
    return match.group(0).upper() if match else None


def _known_facility_names() -> list[str]:
    try:
        projects = list_projects()
    except Exception:
        return list(dict.fromkeys(_FALLBACK_FACILITY_ALIASES.values()))
    names = [
        str(project.get("name")).strip()
        for project in projects
        if isinstance(project, dict) and project.get("name")
    ]
    return list(dict.fromkeys(name for name in names if name))


def _facility_aliases() -> dict[str, str]:
    names = _known_facility_names()
    aliases = {name.lower(): name for name in names}
    prefix_candidates: dict[str, list[str]] = {}
    for name in names:
        words = re.findall(r"[A-Za-z0-9]+", name)
        for size in range(1, min(3, len(words)) + 1):
            alias = " ".join(words[:size])
            if len(alias) >= 3:
                prefix_candidates.setdefault(alias.lower(), []).append(name)
    for alias, matches in prefix_candidates.items():
        unique = list(dict.fromkeys(matches))
        if len(unique) == 1:
            aliases[alias] = unique[0]
    if not aliases:
        aliases.update({alias.lower(): canonical for alias, canonical in _FALLBACK_FACILITY_ALIASES.items()})
    return aliases


def _canonicalize_facility_candidate(candidate: str | None) -> str | None:
    if not candidate:
        return None
    cleaned = str(candidate).strip()
    aliases = _facility_aliases()
    lowered = cleaned.lower()
    if lowered in aliases:
        return aliases[lowered]
    matches = [canonical for alias, canonical in aliases.items() if canonical.lower().startswith(lowered)]
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else cleaned


def _known_facility_re() -> re.Pattern | None:
    aliases = _facility_aliases()
    if not aliases:
        return None
    pattern = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    return re.compile(rf"\b({pattern})\b", re.IGNORECASE)


def _normalize_facility(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    known_re = _known_facility_re()
    known = known_re.search(text) if known_re else None
    if known:
        return _canonicalize_facility_candidate(known.group(1))
    at_match = re.search(r"\bat\s+([A-Za-z0-9][A-Za-z0-9 ._-]{1,60})", text, re.IGNORECASE)
    if at_match:
        candidate = re.split(r"[,.;\n]| with | on | and | for ", at_match.group(1), maxsplit=1)[0].strip()
        return _canonicalize_facility_candidate(candidate)
    return None


def _extract_reference_context(history: list[dict] | None, current_message: str) -> dict[str, object]:
    """Deterministically recover the last container/facility from visible history.

    This avoids relying solely on the model to infer "same container/facility" from
    raw transcript prose, which is brittle under streaming and session restarts.
    """
    context: dict[str, object] = {}
    known_facilities = _known_facility_names()
    if known_facilities:
        context["known_facilities"] = known_facilities[:50]
    for item in history or []:
        text = str(item.get("text") or "")
        cid = _normalize_container(text)
        if cid:
            context["previous_container_id"] = cid
        facility = _normalize_facility(text)
        if facility:
            context["previous_facility"] = facility

        cards = item.get("cards") if isinstance(item.get("cards"), list) else []
        for card in cards:
            data = card.get("data") if isinstance(card, dict) else None
            if not isinstance(data, dict):
                continue
            cid = _normalize_container(str(data.get("container_id") or data.get("last_container") or ""))
            if cid:
                context["previous_container_id"] = cid
            for key in ("facility", "location", "last_seen_location"):
                facility = _normalize_facility(str(data.get(key) or ""))
                if facility:
                    context["previous_facility"] = facility

    current_facility = _normalize_facility(current_message)
    if current_facility:
        context["current_message_facility"] = current_facility
    current_container = _normalize_container(current_message)
    if current_container:
        context["current_message_container_id"] = current_container
    return context


def _summarize_history(history: list[dict] | None, current_message: str = "") -> str:
    """Compact visible chat context sent by the frontend. Keeps backend restarts from erasing context."""
    refs = _extract_reference_context(history, current_message)
    if not history:
        if not refs:
            return ""
        return (
            "Resolved chat references from the current message/history: "
            f"{json.dumps(refs, sort_keys=True)}.\n"
            "Use these values for pronouns and phrases like 'same container', "
            "'same facility', 'it', and 'as before'.\n\nCurrent user message: "
        )
    lines = []
    for item in history[-8:]:
        role = "User" if item.get("role") == "user" else "Assistant"
        text = str(item.get("text") or "").strip()
        cards = item.get("cards") if isinstance(item.get("cards"), list) else []
        card_bits = []
        for card in cards[:2]:
            data = card.get("data") if isinstance(card, dict) else None
            if not isinstance(data, dict):
                continue
            for key in (
                "container_id", "last_seen_location", "facility", "location",
                "last_seen_time", "detection_count", "by_facility",
                "rule_id", "opportunity_id",
            ):
                if key in data:
                    card_bits.append(f"{key}={data[key]}")
        if card_bits:
            text = f"{text} [{' ; '.join(card_bits)}]".strip()
        if text:
            lines.append(f"{role}: {text[:1000]}")
    if not lines:
        if not refs:
            return ""
        return (
            "Resolved chat references from the current message/history: "
            f"{json.dumps(refs, sort_keys=True)}.\n\nCurrent user message: "
        )
    refs_line = (
        "Resolved chat references from the current message/history: "
        f"{json.dumps(refs, sort_keys=True)}.\n"
        if refs else ""
    )
    return (
        refs_line +
        "Visible chat context from the user's browser. Use this to resolve references like "
        "'same container', 'same facility', 'it', or 'as before'.\n"
        + "\n".join(lines)
        + "\n\nCurrent user message: "
    )


@app.post("/chat")
async def chat(req: ChatRequest):
    """Send a message to the Builder Agent and stream the response via SSE.

    Runs the ADK agent in a background thread and pushes chunks through a queue
    so the uvicorn event loop stays unblocked.
    """
    # Ensure session exists with a title if it's new
    try:
        session = await session_service.get_session(
            app_name="sitetrax_coordinator",
            user_id="demo_user",
            session_id=req.session_id
        )
        if not session:
            title = req.message[:40] + ("..." if len(req.message) > 40 else "")
            await session_service.create_session(
                app_name="sitetrax_coordinator",
                user_id="demo_user",
                session_id=req.session_id,
                state={"title": title}
            )
    except Exception as e:
        logger.warning("Failed to get/create session: %s", e)
        if SESSION_STORE == "firestore":
            raise HTTPException(
                status_code=503,
                detail="Firestore session persistence is unavailable. Check Firestore API, database, and IAM configuration.",
            ) from e

    q: queue.Queue = queue.Queue()

    def _run_agent():
        context_prefix = _summarize_history(req.history, req.message)
        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=f"{context_prefix}{req.message}")],
        )
        collected = {"text_parts": [], "tool_results": []}

        async def _collect():
            runner = create_runner()
            async for event in runner.run_async(
                user_id="demo_user",
                session_id=req.session_id,
                new_message=user_content,
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            q.put(("text", part.text))
                            collected["text_parts"].append(part.text)
                        if part.function_call:
                            tc = {
                                "name": part.function_call.name,
                                "args": dict(part.function_call.args),
                            }
                            collected["tool_results"].append(tc)
                            q.put(("tool_call", tc))
                        if part.function_response:
                            result_str = _coerce_tool_response_to_string(part.function_response.response)
                            try:
                                parsed_result = json.loads(result_str)
                            except Exception:
                                parsed_result = None
                            progress_event = None
                            if isinstance(parsed_result, dict):
                                progress = parsed_result.get("progress")
                                pagination = parsed_result.get("pagination")
                                if isinstance(progress, dict) or isinstance(pagination, dict):
                                    progress_event = {
                                        "name": part.function_response.name,
                                        "label": (progress or {}).get("label") if isinstance(progress, dict) else None,
                                        "progress": progress,
                                        "pagination": pagination,
                                    }
                            for tr in reversed(collected["tool_results"]):
                                if tr["name"] == part.function_response.name and "result" not in tr:
                                    tr["result"] = result_str
                                    break
                            q.put(("tool_result", {
                                "name": part.function_response.name,
                                "result": result_str,
                            }))
                            if progress_event:
                                q.put(("tool_progress", progress_event))

            final_text = "".join(collected["text_parts"]).strip()
            if not final_text and collected["tool_results"]:
                final_text = "I processed your request. Check the results above."
            q.put(("done", {
                "text": final_text,
                "session_id": req.session_id,
                "tool_results": collected["tool_results"],
            }))

        try:
            asyncio.run(_collect())
        except Exception as e:
            logger.exception("Chat stream failed in thread")
            q.put(("error", {"detail": str(e)}))

    thread = threading.Thread(target=_run_agent, daemon=True)
    thread.start()

    async def event_generator():
        while True:
            try:
                kind, data = await asyncio.to_thread(q.get, timeout=0.1)
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue

            if kind == "done":
                yield f"event: done\ndata: {json.dumps(data)}\n\n"
                break
            if kind == "error":
                yield f"event: error\ndata: {json.dumps(data)}\n\n"
                break
            yield f"event: {kind}\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@app.get("/chat/sessions")
async def list_chat_sessions():
    """List all past chat sessions with their metadata."""
    try:
        res = await session_service.list_sessions(app_name="sitetrax_coordinator", user_id="demo_user")
        # Sort sessions by last_update_time descending
        sorted_sessions = sorted(res.sessions, key=lambda s: s.last_update_time or 0.0, reverse=True)
        
        sessions_list = []
        for s in sorted_sessions:
            event_count = s.state.get("event_count", 0)
            if event_count <= 0:
                continue
            dt = datetime.datetime.fromtimestamp(s.last_update_time or 0.0, datetime.timezone.utc)
            title = s.state.get("title") or f"Session {s.id[:8]}"
            sessions_list.append({
                "id": s.id,
                "title": title,
                "last_update_time": dt.isoformat(),
                "message_count": event_count,
            })
        return {"sessions": sessions_list}
    except Exception as e:
        logger.exception("Failed to list sessions")
        raise HTTPException(status_code=500, detail="Failed to retrieve sessions.")


@app.get("/chat/history/{session_id}")
async def get_chat_history(session_id: str):
    """Retrieve and reconstruct the chat history for a given session ID."""
    try:
        session = await session_service.get_session(
            app_name="sitetrax_coordinator",
            user_id="demo_user",
            session_id=session_id
        )
        if not session:
            return {"session_id": session_id, "messages": [], "event_count": 0}

        messages = []
        current_agent_msg = None

        for event in session.events:
            dt = datetime.datetime.fromtimestamp(event.timestamp, datetime.timezone.utc)
            timestamp_str = dt.isoformat()

            if event.author == "user":
                if current_agent_msg:
                    messages.append(current_agent_msg)
                    current_agent_msg = None

                text = ""
                if event.content and event.content.parts:
                    text = "".join(p.text for p in event.content.parts if p.text)
                    if "\nCurrent user message: " in text:
                        text = text.split("\nCurrent user message: ")[-1]
                
                messages.append({
                    "id": event.id or str(uuid.uuid4()),
                    "role": "user",
                    "text": text,
                    "cards": [],
                    "timestamp": timestamp_str
                })
            else:
                if not current_agent_msg:
                    current_agent_msg = {
                        "id": event.id or str(uuid.uuid4()),
                        "role": "agent",
                        "text": "",
                        "cards": [],
                        "timestamp": timestamp_str,
                        "_tool_results": []
                    }
                
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text and not event.partial:
                            current_agent_msg["text"] += part.text
                        if part.function_call:
                            current_agent_msg["_tool_results"].append({
                                "name": part.function_call.name,
                                "args": dict(part.function_call.args),
                            })
                        if part.function_response:
                            result_str = _coerce_tool_response_to_string(part.function_response.response)
                            for tr in reversed(current_agent_msg["_tool_results"]):
                                if tr["name"] == part.function_response.name:
                                    tr["result"] = result_str
                                    break

        if current_agent_msg:
            messages.append(current_agent_msg)

        def _asset_columns_for_rows(rows):
            preferred = [
                ("text", "Container"),
                ("container_id", "Container"),
                ("facility", "Facility"),
                ("location", "Location"),
                ("status_code", "Status"),
                ("heading", "Heading"),
                ("created_at", "Detected at"),
                ("datetime", "Detected at"),
                ("asset_id", "Asset ID"),
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

        def _asset_visualization_card(title, dataset_name, rows, answer, visualizations, extra=None):
            payload = {
                "title": title,
                "answer": answer,
                "datasets": [{
                    "name": dataset_name,
                    "label": title,
                    "entity_type": "asset",
                    "columns": _asset_columns_for_rows(rows),
                    "rows": rows,
                    "count": len(rows),
                }],
                "visualizations": visualizations,
                "provenance": {
                    "resource": dataset_name,
                    "returned": len(rows),
                },
            }
            if extra:
                payload.update(extra)
            return {"type": "generic_visualization", "data": payload}

        def _timeline_card(parsed):
            rows = parsed.get("timeline") if isinstance(parsed, dict) else None
            if not isinstance(rows, list) or not rows:
                return None
            first = rows[0] if isinstance(rows[0], dict) else {}
            container_id = parsed.get("container_id") or first.get("container_id") or first.get("text") or "container"
            return _asset_visualization_card(
                title=f"Timeline for {container_id}",
                dataset_name="asset_timeline",
                rows=rows,
                answer=parsed.get("answer") or f"Found {len(rows)} timeline record(s).",
                visualizations=[
                    {"type": "timeline", "dataset": "asset_timeline", "title": "Detection timeline"},
                    {"type": "image_gallery", "dataset": "asset_timeline", "title": "Detection images"},
                    {"type": "video_gallery", "dataset": "asset_timeline", "title": "Related videos"},
                    {"type": "table", "dataset": "asset_timeline", "title": "Timeline records"},
                ],
                extra={"container_id": parsed.get("container_id"), "count": len(rows), "timeline": rows},
            )

        def _asset_array_card(parsed):
            rows = [row for row in parsed if isinstance(row, dict)]
            if not rows:
                return None
            return _asset_visualization_card(
                title="Asset records",
                dataset_name="assets",
                rows=rows,
                answer=f"Found {len(rows)} asset record(s).",
                visualizations=[
                    {"type": "table", "dataset": "assets", "title": "Asset records"},
                    {"type": "image_gallery", "dataset": "assets", "title": "Asset images"},
                ],
            )

        def _parse_nested_tool_result(value, depth=0):
            if depth > 4 or value is None:
                return None
            if isinstance(value, str):
                try:
                    return _parse_nested_tool_result(json.loads(value), depth + 1)
                except Exception:
                    return None
            if isinstance(value, list):
                return value
            if not isinstance(value, dict):
                return None
            if "result" in value:
                return _parse_nested_tool_result(value.get("result"), depth + 1)
            content = value.get("content")
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        text_parts.append(item["text"])
                if text_parts:
                    return _parse_nested_tool_result("\n".join(text_parts), depth + 1)
            if isinstance(value.get("text"), str) and len(value) <= 2:
                return _parse_nested_tool_result(value["text"], depth + 1)
            return value

        def _parse_tool_result_to_card(result_str):
            parsed = _parse_nested_tool_result(result_str)
            if parsed is None:
                return None
            if isinstance(parsed, list):
                return _asset_array_card(parsed)
            if not isinstance(parsed, dict):
                return None
            if isinstance(parsed.get("timeline"), list):
                return _timeline_card(parsed)
            if isinstance(parsed.get("datasets"), list) and isinstance(parsed.get("visualizations"), list):
                return {"type": "generic_visualization", "data": parsed}
            if "resources" in parsed or "schema" in parsed:
                return {"type": "sitetrax_schema", "data": parsed}
            # Rule / opportunity / approval
            if parsed.get("status") == "needs_confirmation" or parsed.get("action") == "create_monitoring_rule":
                return {"type": "approval_request", "data": parsed}
            if parsed.get("status") == "created" or "rule_id" in parsed:
                return {"type": "rule_created", "data": parsed}
            if parsed.get("status") == "logged" or "opportunity_id" in parsed:
                return {"type": "opportunity_logged", "data": parsed}
            # Container history
            if "last_seen_location" in parsed:
                return {"type": "last_seen", "data": parsed}
            if "detection_count" in parsed:
                return {"type": "facility_activity", "data": parsed}
            if "time_since_last_seen" in parsed:
                return {"type": "dwell", "data": parsed}
            if "journey" in parsed and isinstance(parsed.get("journey"), list):
                return {"type": "asset_journey", "data": parsed}
            # Facility last scan
            if "last_container" in parsed and "scanned_ago" in parsed:
                return {"type": "facility_last_scan", "data": {**parsed, "container_id": parsed.get("last_container"), "last_seen_location": parsed.get("facility"), "last_seen_time": parsed.get("scanned_at"), "last_seen_ago": parsed.get("scanned_ago")}}
            # Yard / inventory
            if "facility" in parsed and "assets" in parsed and isinstance(parsed.get("assets"), list):
                return {"type": "yard_inventory", "data": parsed}
            if "by_status" in parsed and isinstance(parsed.get("by_status"), dict):
                return {"type": "status_distribution", "data": parsed}
            if "containers" in parsed and isinstance(parsed.get("containers"), list):
                return {"type": "detention_list", "data": parsed}
            if "inbound_count" in parsed and "outbound_count" in parsed:
                return {"type": "inbound_outbound", "data": parsed}
            # Company
            if "company_prefix" in parsed:
                return {"type": "container_company", "data": parsed}
            if "company" in parsed and "total_scans" in parsed:
                return {"type": "company_activity", "data": {**parsed, "company_prefix": parsed.get("company")}}
            # Facility summaries
            if "summary" in parsed and isinstance(parsed.get("summary"), dict) and "total_containers_7d" in parsed.get("summary", {}):
                return {"type": "facility_summary", "data": parsed}
            if parsed.get("status") == "health_check" and parsed.get("report"):
                return {"type": "health_check", "data": parsed}
            # Comparison
            if "facility_a" in parsed and "facility_b" in parsed:
                return {"type": "compare_facilities", "data": parsed}
            # Video
            if ("image_url" in parsed or "asset_image" in parsed) and (
                "asset_id" in parsed or "id" in parsed or "container_id" in parsed
            ):
                return {"type": "image", "data": parsed}
            if "images" in parsed and isinstance(parsed.get("images"), list) and len(parsed.get("images", [])) > 1:
                return {"type": "image_gallery", "data": parsed}
            if "url" in parsed and "video_id" in parsed:
                return {"type": "video", "data": parsed}
            if "videos" in parsed and isinstance(parsed.get("videos"), list) and len(parsed.get("videos", [])) > 1:
                return {"type": "video_gallery", "data": parsed}
            if "facility" in parsed and "summary" in parsed and isinstance(parsed.get("summary"), dict):
                return {"type": "overview", "data": parsed}
            if "images" in parsed and isinstance(parsed.get("images"), list):
                return {"type": "image_list", "data": parsed}
            if "videos" in parsed and isinstance(parsed.get("videos"), list):
                return {"type": "video_list", "data": parsed}
            # Rules / review
            if "alerts" in parsed and isinstance(parsed.get("alerts"), list):
                return {"type": "rule_history", "data": parsed}
            if "needs_review_count" in parsed:
                return {"type": "review_queue", "data": parsed}
            # Exception lists
            if "containers_with_turnaround" in parsed:
                return {"type": "turnaround_time", "data": parsed}
            if "missing_count" in parsed:
                return {"type": "missing_containers", "data": parsed}
            if "camera_count" in parsed:
                return {"type": "camera_health", "data": parsed}
            if "duplicate_count" in parsed:
                return {"type": "duplicate_scans", "data": parsed}
            if "chassis" in parsed and isinstance(parsed.get("chassis"), list):
                return {"type": "chassis_activity", "data": parsed}
            # Reports / export
            if parsed.get("status") == "generated" and parsed.get("report"):
                return {"type": "facility_report", "data": parsed}
            if parsed.get("status") == "exported" and parsed.get("csv_data"):
                return {"type": "csv_export", "data": parsed}
            # Metrics
            if "by_day" in parsed and "total_containers" in parsed:
                return {"type": "metrics", "data": parsed}
            # Search results
            if "query" in parsed and "assets" in parsed and isinstance(parsed.get("assets"), list):
                return {"type": "search_results", "data": parsed}
            # Facilities list
            if "facilities" in parsed and isinstance(parsed.get("facilities"), list):
                return {"type": "facilities_list", "data": parsed}
            # Reference
            if "matches" in parsed and isinstance(parsed.get("matches"), list):
                return {"type": "reference", "data": parsed}
            # Preferences
            if parsed.get("status") == "saved" and "preferences" in parsed:
                return {"type": "preferences", "data": parsed}
            if "preferences" in parsed and "session_id" in parsed:
                return {"type": "preferences", "data": parsed}
            return None

        final_messages = []
        for msg in messages:
            if msg["role"] == "agent":
                tool_results = msg.pop("_tool_results", [])
                cards = []
                for tr in tool_results:
                    if tr.get("result"):
                        card = _parse_tool_result_to_card(tr["result"])
                        if card:
                            cards.append(card)
                msg["cards"] = cards
                if not msg["text"] and cards:
                    msg["text"] = "I processed your request. Check the results above."
            final_messages.append(msg)

        return {
            "session_id": session_id,
            "messages": final_messages,
            "event_count": len(session.events) if session else 0,
        }
    except Exception as e:
        logger.exception("Failed to get session history")
        raise HTTPException(status_code=500, detail="Failed to retrieve chat history.")


@app.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str):
    """Delete a past chat session."""
    try:
        await session_service.delete_session(
            app_name="sitetrax_coordinator",
            user_id="demo_user",
            session_id=session_id
        )
        return {"status": "deleted", "session_id": session_id}
    except Exception as e:
        logger.exception("Failed to delete session")
        raise HTTPException(status_code=500, detail="Failed to delete session.")


@app.get("/chat/debug/sessions")
async def debug_sessions():
    """Diagnostic: list sessions with event counts for troubleshooting."""
    try:
        res = await session_service.list_sessions(app_name="sitetrax_coordinator", user_id="demo_user")
        sessions = []
        for s in res.sessions:
            session = await session_service.get_session(
                app_name="sitetrax_coordinator",
                user_id="demo_user",
                session_id=s.id,
            )
            event_count = len(session.events) if session else 0
            if event_count <= 0:
                continue
            sessions.append({
                "id": s.id,
                "title": s.state.get("title", ""),
                "last_update_time": s.last_update_time,
                "event_count": event_count,
                "state_keys": list(s.state.keys()) if s.state else [],
            })
        return {
            "session_store": SESSION_STORE,
            "session_count": len(sessions),
            "sessions": sessions,
        }
    except Exception as e:
        logger.exception("Debug sessions failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/simulate-event")
async def simulate_event(req: SimulateEventRequest):
    """Simulate a container detection event and evaluate the targeted rule set.

    When `rule_id` is supplied, the evaluator stays scoped to that rule so a
    dwell simulation for one container does not fire unrelated status-change or
    low-confidence rules for other containers.
    """
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        alerts = await asyncio.to_thread(
            evaluate_event, req.container_id, req.location, req.dwell_hours, req.rule_id
        )
    except Exception:
        logger.exception("Simulate event failed")
        raise HTTPException(status_code=500, detail="Event evaluation failed.")

    return {
        "event": {
            "container_id": req.container_id,
            "location": req.location,
            "timestamp": now.isoformat(),
        },
        "alerts_fired": len(alerts),
        "alerts": alerts,
    }


@app.post("/tasks/evaluate")
async def tasks_evaluate(x_tasks_token: str | None = Header(default=None)):
    """Automatic evaluation pass (Cloud Scheduler / poller). Polls the data source and fires
    new alerts (deduped). Protected by X-Tasks-Token when TASKS_TOKEN is set.
    """
    expected = os.environ.get("TASKS_TOKEN")
    if expected and x_tasks_token != expected:
        raise HTTPException(status_code=403, detail="Invalid task token")
    try:
        alerts = await asyncio.to_thread(evaluate_recent)
    except Exception:
        logger.exception("Task evaluation failed")
        raise HTTPException(status_code=500, detail="Evaluation failed.")
    return {"evaluated": True, "fired": len(alerts), "alerts": alerts}


@app.get("/rules")
async def list_rules():
    """List all active monitoring rules."""
    rules = store.get_all_rules()
    return {
        "count": len(rules),
        "rules": [
            {
                "id": r.id,
                "template": r.template_name.value,
                "display_name": TEMPLATES[r.template_name].display_name,
                "description": TEMPLATES[r.template_name].description,
                "trigger_description": TEMPLATES[r.template_name].trigger_description,
                "action_description": TEMPLATES[r.template_name].action_description,
                "params": r.params,
                "recipient_email": r.params.get("email") or os.environ.get("ALERT_EMAIL_TO", ""),
                "created_at": r.created_at,
                "evaluation_count": r.evaluation_count,
            }
            for r in rules
        ],
    }


@app.get("/rules/templates")
async def list_rule_templates():
    """List the available monitoring rule templates and how they trigger."""
    return {
        "count": len(TEMPLATES),
        "templates": [
            {
                "id": template.name.value,
                "display_name": template.display_name,
                "description": template.description,
                "trigger_description": template.trigger_description,
                "action_description": template.action_description,
                "params": [
                    {
                        "name": param.name,
                        "description": param.description,
                        "required": param.required,
                        "type": param.param_type,
                    }
                    for param in template.params
                ],
            }
            for template in TEMPLATES.values()
        ],
    }


@app.get("/rules/history")
async def rules_history(hours_back: int = 168):
    """Get recently fired rule alerts with their timestamps."""
    alerts = store.get_fired_alerts(hours_back=hours_back)
    rules = {r.id: r for r in store.get_all_rules()}
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
    return {
        "count": len(enriched),
        "hours_back": hours_back,
        "alerts": enriched,
    }


@app.get("/artifacts")
async def list_artifacts(session_id: str = "default"):
    """List artifacts for the current user/session."""
    try:
        keys = await artifact_service.list_artifact_keys(
            app_name="sitetrax_coordinator", user_id="demo_user", session_id=session_id
        )
        return {"session_id": session_id, "artifacts": keys}
    except Exception as e:
        logger.exception("Failed to list artifacts")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/artifacts/{filename}")
async def get_artifact(filename: str, session_id: str = "default"):
    """Download an artifact by filename."""
    try:
        artifact = await artifact_service.load_artifact(
            app_name="sitetrax_coordinator",
            user_id="demo_user",
            filename=filename,
            session_id=session_id,
        )
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        from fastapi.responses import Response
        if artifact.text:
            return Response(
                content=artifact.text,
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
        if artifact.inline_data:
            return Response(
                content=artifact.inline_data.data,
                media_type=artifact.inline_data.mime_type or "application/octet-stream",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
        return {"error": "Empty artifact"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to load artifact")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """Delete a monitoring rule and any rule-specific scheduler job."""
    rule = store.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    scheduler_cleanup = delete_rule_scheduler_jobs(rule)
    if scheduler_cleanup.get("attempted") and scheduler_cleanup.get("errors"):
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Rule was not deleted because Cloud Scheduler cleanup failed.",
                "scheduler": scheduler_cleanup,
            },
        )

    if store.delete_rule(rule_id):
        return {"status": "deleted", "rule_id": rule_id, "scheduler": scheduler_cleanup}
    raise HTTPException(status_code=404, detail="Rule not found")


@app.get("/opportunities")
async def list_opportunities():
    """List all logged automation opportunities."""
    opps = store.get_opportunities()
    return {
        "count": len(opps),
        "opportunities": [
            {
                "id": o.id,
                "user_request": o.user_request,
                "reason": o.reason,
                "category": o.category,
                "created_at": o.created_at,
            }
            for o in opps
        ],
    }


@app.delete("/opportunities/{opportunity_id}")
async def delete_opportunity(opportunity_id: str):
    """Delete a logged automation opportunity."""
    if getattr(store, "delete_opportunity", None) and store.delete_opportunity(opportunity_id):
        return {"status": "deleted", "opportunity_id": opportunity_id}
    raise HTTPException(status_code=404, detail="Opportunity not found")


@app.get("/assets")
async def list_assets(
    container_id: str | None = None,
    location: str | None = None,
    status_code: str | None = None,
    hours_back: int = 24,
):
    """Query SiteTrax.io asset records (real API or mock, depending on USE_REAL_API)."""
    results = query_assets(
        container_id=container_id,
        location=location,
        status_code=status_code,
        hours_back=hours_back,
    )
    return {"count": len(results), "assets": results}


@app.get("/assets/{container_id}")
async def get_asset(container_id: str):
    """Get the latest scan for a container."""
    scan = get_latest_scan(container_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Container not found")
    return scan


@app.post("/approval-response")
async def approval_response(req: dict):
    """Receive user approval/denial for pending actions.
    This is a lightweight passthrough — the actual handling happens
    via the chat loop when the user sends a follow-up confirmation message.
    """
    return {"status": "acknowledged", "action": req.get("action"), "approved": req.get("approved")}


# ── Startup ──────────────────────────────────────────────────

# Warn if /tasks/evaluate is unprotected in production-like configs.
if not os.environ.get("TASKS_TOKEN") and os.environ.get("K_SERVICE"):
    logger.warning("TASKS_TOKEN not set — /tasks/evaluate is unprotected on Cloud Run")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
