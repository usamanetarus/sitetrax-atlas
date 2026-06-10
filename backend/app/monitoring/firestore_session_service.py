import os
import asyncio
import datetime
import uuid
import logging
from typing import Any, Optional

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.adk.sessions.base_session_service import BaseSessionService, GetSessionConfig, ListSessionsResponse
from google.adk.sessions.session import Session
from google.adk.events.event import Event

logger = logging.getLogger("sitetrax")


class FirestoreSessionService(BaseSessionService):
    """Firestore-backed session service for serverless, stateless deployments (Cloud Run)."""

    def __init__(self):
        self._db = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT") or None)
        self._sessions_col = self._db.collection("chat_sessions")
        # Probe connectivity so a missing DB/API/permission fails fast at startup,
        # preventing Cloud Run from silently using non-durable local storage.
        next(self._sessions_col.limit(1).stream(), None)

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        if not session_id:
            session_id = str(uuid.uuid4())

        doc_ref = self._sessions_col.document(session_id)
        doc = await asyncio.to_thread(doc_ref.get)

        if doc.exists:
            data = doc.to_dict()
            return Session(
                app_name=data.get("app_name", app_name),
                user_id=data.get("user_id", user_id),
                id=session_id,
                state=data.get("state") or {},
                last_update_time=data.get("last_update_time") or datetime.datetime.now(datetime.timezone.utc).timestamp(),
            )

        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        initial_state = state or {}
        await asyncio.to_thread(
            doc_ref.set,
            {
                "app_name": app_name,
                "user_id": user_id,
                "state": initial_state,
                "last_update_time": now,
            }
        )
        return Session(
            app_name=app_name,
            user_id=user_id,
            id=session_id,
            state=initial_state,
            last_update_time=now,
        )

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        doc_ref = self._sessions_col.document(session_id)
        doc = await asyncio.to_thread(doc_ref.get)
        if not doc.exists:
            return None

        data = doc.to_dict()
        if data.get("user_id") != user_id or data.get("app_name") != app_name:
            return None

        # Fetch events ordered by timestamp
        events_ref = doc_ref.collection("events").order_by("timestamp")
        if config and config.after_timestamp:
            events_ref = events_ref.where(filter=FieldFilter("timestamp", ">=", config.after_timestamp))

        events_query = events_ref
        if config and config.num_recent_events:
            events_query = events_ref.limit_to_last(config.num_recent_events)

        events_docs = await asyncio.to_thread(events_query.get)
        events = []
        for ed in events_docs:
            event_data = ed.to_dict()
            try:
                events.append(Event.model_validate(event_data))
            except Exception as ev_err:
                logger.warning(
                    "Skipping invalid event doc %s in session %s: %s",
                    ed.id, session_id, ev_err
                )

        return Session(
            app_name=app_name,
            user_id=user_id,
            id=session_id,
            state=data.get("state") or {},
            events=events,
            last_update_time=data.get("last_update_time") or datetime.datetime.now(datetime.timezone.utc).timestamp(),
        )

    async def list_sessions(
        self, *, app_name: str, user_id: Optional[str] = None
    ) -> ListSessionsResponse:
        query = self._sessions_col.where(filter=FieldFilter("app_name", "==", app_name))
        if user_id:
            query = query.where(filter=FieldFilter("user_id", "==", user_id))

        docs = await asyncio.to_thread(query.get)
        sessions = []
        for d in docs:
            data = d.to_dict()
            sessions.append(
                Session(
                    app_name=app_name,
                    user_id=data.get("user_id", "demo_user"),
                    id=d.id,
                    state=data.get("state") or {},
                    last_update_time=data.get("last_update_time") or 0.0,
                )
            )
        return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        doc_ref = self._sessions_col.document(session_id)
        events_ref = doc_ref.collection("events")
        event_docs = await asyncio.to_thread(events_ref.get)

        batch = self._db.batch()
        for ed in event_docs:
            batch.delete(ed.reference)
        batch.delete(doc_ref)
        await asyncio.to_thread(batch.commit)

    async def append_event(self, session: Session, event: Event) -> Event:
        # First let BaseSessionService update in-memory attributes
        event = await super().append_event(session, event)

        doc_ref = self._sessions_col.document(session.id)
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()

        # Serialize event
        event_data = event.model_dump(exclude_none=True, mode="json")

        batch = self._db.batch()
        event_doc_ref = doc_ref.collection("events").document(event.id or str(uuid.uuid4()))
        batch.set(event_doc_ref, event_data)

        # Mirror event_count into state so list_sessions can surface it
        session.state["event_count"] = (session.state.get("event_count", 0) or 0) + 1
        batch.update(doc_ref, {
            "state": session.state,
            "last_update_time": now,
        })

        await asyncio.to_thread(batch.commit)
        session.last_update_time = now
        return event
