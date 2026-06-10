"""Firestore-backed artifact service for durable structured reports and downloads."""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Any, Optional

from google.cloud import firestore
from google.genai import types
from pydantic import BaseModel
from typing_extensions import override

from google.adk.artifacts.base_artifact_service import (
    ArtifactVersion,
    BaseArtifactService,
    ensure_part,
)

logger = logging.getLogger("sitetrax")
DEFAULT_COLLECTION = "artifacts"


class FirestoreArtifactService(BaseArtifactService, BaseModel):
    """Artifact service backed by Firestore for durable, queryable artifacts."""

    collection: str = DEFAULT_COLLECTION
    _db: firestore.Client | None = None

    def model_post_init(self, __context: Any) -> None:
        if self._db is None:
            self._db = firestore.Client(
                project=os.environ.get("GOOGLE_CLOUD_PROJECT") or None
            )

    def _doc_path(
        self, app_name: str, user_id: str, filename: str, session_id: Optional[str]
    ) -> str:
        ns = f"{app_name}/{user_id}"
        if session_id:
            ns += f"/{session_id}"
        return f"{self.collection}/{ns}/files/{filename}"

    @override
    async def save_artifact(
        self, *, app_name: str, user_id: str, filename: str,
        artifact: types.Part | dict[str, Any], session_id: Optional[str] = None,
        version: Optional[int] = None,
    ) -> ArtifactVersion:
        part = ensure_part(artifact)
        doc_path = self._doc_path(app_name, user_id, filename, session_id)
        doc_ref = self._db.document(doc_path)
        doc = await asyncio.to_thread(doc_ref.get)
        current_version = 0
        if doc.exists:
            current_version = doc.to_dict().get("latest_version", 0)
        new_version = version if version is not None else current_version + 1
        payload: dict[str, Any] = {
            "app_name": app_name, "user_id": user_id, "session_id": session_id,
            "filename": filename, "version": new_version,
            "latest_version": new_version,
            "mime_type": part.mime_type or "application/json",
            "created_at": firestore.SERVER_TIMESTAMP,
        }
        if part.text:
            payload["text"] = part.text
        elif part.inline_data:
            payload["data_b64"] = base64.b64encode(part.inline_data.data).decode()
            payload["mime_type"] = part.inline_data.mime_type or payload["mime_type"]
        await asyncio.to_thread(doc_ref.set, payload, merge=True)
        return ArtifactVersion(
            version=new_version, canonical_uri=doc_path, mime_type=payload["mime_type"],
        )

    @override
    async def load_artifact(
        self, *, app_name: str, user_id: str, filename: str,
        session_id: Optional[str] = None, version: Optional[int] = None,
    ) -> Optional[types.Part]:
        doc_path = self._doc_path(app_name, user_id, filename, session_id)
        doc_ref = self._db.document(doc_path)
        doc = await asyncio.to_thread(doc_ref.get)
        if not doc.exists:
            return None
        data = doc.to_dict()
        if "text" in data:
            return types.Part.from_text(text=data["text"])
        if "data_b64" in data:
            return types.Part.from_bytes(
                data=base64.b64decode(data["data_b64"]),
                mime_type=data.get("mime_type", "application/octet-stream"),
            )
        return None

    @override
    async def list_artifact_keys(
        self, *, app_name: str, user_id: str, session_id: Optional[str] = None
    ) -> list[str]:
        ns = f"{self.collection}/{app_name}/{user_id}"
        if session_id:
            ns += f"/{session_id}"
        files_col = self._db.collection(f"{ns}/files")
        docs = await asyncio.to_thread(files_col.get)
        return [d.id for d in docs]

    @override
    async def delete_artifact(
        self, *, app_name: str, user_id: str, filename: str,
        session_id: Optional[str] = None,
    ) -> None:
        doc_path = self._doc_path(app_name, user_id, filename, session_id)
        doc_ref = self._db.document(doc_path)
        await asyncio.to_thread(doc_ref.delete)

    @override
    async def get_artifact_version(
        self, *, app_name: str, user_id: str, filename: str,
        session_id: Optional[str] = None, version: int = 0,
    ) -> Optional[ArtifactVersion]:
        doc_path = self._doc_path(app_name, user_id, filename, session_id)
        doc_ref = self._db.document(doc_path)
        doc = await asyncio.to_thread(doc_ref.get)
        if not doc.exists:
            return None
        data = doc.to_dict()
        return ArtifactVersion(
            version=data.get("version", 1),
            canonical_uri=doc_path,
            mime_type=data.get("mime_type"),
        )

    @override
    async def list_artifact_versions(
        self, *, app_name: str, user_id: str, filename: str,
        session_id: Optional[str] = None,
    ) -> list[ArtifactVersion]:
        return await self.list_versions(
            app_name=app_name, user_id=user_id, filename=filename, session_id=session_id
        )

    @override
    async def list_versions(
        self, *, app_name: str, user_id: str, filename: str,
        session_id: Optional[str] = None,
    ) -> list[ArtifactVersion]:
        doc_path = self._doc_path(app_name, user_id, filename, session_id)
        doc_ref = self._db.document(doc_path)
        doc = await asyncio.to_thread(doc_ref.get)
        if not doc.exists:
            return []
        data = doc.to_dict()
        return [ArtifactVersion(
            version=data.get("version", 1), canonical_uri=doc_path,
            mime_type=data.get("mime_type"),
        )]
