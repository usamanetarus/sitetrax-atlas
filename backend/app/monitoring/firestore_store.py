"""Firestore-backed store — a durable, Cloud Run-safe drop-in for RuleStore.

Same interface as `RuleStore` (rule_store.py); selected via the `USE_FIRESTORE` flag
in this package's `__init__`. Authenticates with Application Default Credentials —
the same ADC already used for Vertex AI.
"""

import os
import uuid
import datetime
from typing import Any

from google.cloud import firestore

from .rule_store import Rule, Opportunity
from .templates import TemplateName

_RULES = "rules"
_FIRED_ALERTS = "fired_alerts"
_OPPORTUNITIES = "opportunities"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class FirestoreRuleStore:
    """Firestore-backed store for monitoring rules and opportunities."""

    def __init__(self):
        self._db = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT") or None)
        self._rules = self._db.collection(_RULES)
        self._opps = self._db.collection(_OPPORTUNITIES)
        self._fired = self._db.collection(_FIRED_ALERTS)
        # Probe connectivity so a missing DB/API/permission fails fast at startup,
        # preventing Cloud Run from silently using non-durable local state.
        next(self._rules.limit(1).stream(), None)

    # --- Rules ---

    def create_rule(self, template_name: TemplateName, params: dict[str, Any]) -> Rule:
        rule = Rule(
            id=str(uuid.uuid4())[:8],
            template_name=template_name,
            params=params,
            created_at=_now(),
        )
        self._rules.document(rule.id).set({
            "template_name": template_name.value,
            "params": params,
            "created_at": rule.created_at,
            "last_evaluated_at": None,
            "evaluation_count": 0,
            "last_fired_at": None,
            "last_seen": None,
        })
        return rule

    def get_rule(self, rule_id: str) -> Rule | None:
        doc = self._rules.document(rule_id).get()
        return self._to_rule(doc) if doc.exists else None

    def find_duplicate_rule(self, template_name: TemplateName, params: dict[str, Any]) -> Rule | None:
        for doc in self._rules.stream():
            d = doc.to_dict() or {}
            if d.get("template_name") == template_name.value and d.get("params") == params:
                return self._to_rule(doc)
        return None

    def get_all_rules(self) -> list[Rule]:
        return [self._to_rule(d) for d in self._rules.stream()]

    def delete_rule(self, rule_id: str) -> bool:
        ref = self._rules.document(rule_id)
        if ref.get().exists:
            ref.delete()
            return True
        return False

    def record_evaluation(self, rule_id: str):
        ref = self._rules.document(rule_id)
        if ref.get().exists:  # no-op if missing, matching RuleStore
            ref.update({
                "last_evaluated_at": _now(),
                "evaluation_count": firestore.Increment(1),
            })

    def mark_fired(self, rule_id: str, when: str, seen: str | None = None):
        ref = self._rules.document(rule_id)
        if ref.get().exists:
            update = {"last_fired_at": when}
            if seen is not None:
                update["last_seen"] = seen
            ref.update(update)
        # Also record in fired_alerts collection for history
        self._fired.document().set({
            "rule_id": rule_id,
            "timestamp": when,
            "seen": seen,
        })

    # --- Opportunity capture ---

    def log_opportunity(self, user_request: str, reason: str, category: str) -> Opportunity:
        opp = Opportunity(
            id=str(uuid.uuid4())[:8],
            user_request=user_request,
            reason=reason,
            category=category,
            created_at=_now(),
        )
        self._opps.document(opp.id).set({
            "user_request": user_request,
            "reason": reason,
            "category": category,
            "created_at": opp.created_at,
        })
        return opp

    def get_opportunities(self) -> list[Opportunity]:
        return [self._to_opportunity(d) for d in self._opps.stream()]

    def delete_opportunity(self, opportunity_id: str) -> bool:
        ref = self._opps.document(opportunity_id)
        if ref.get().exists:
            ref.delete()
            return True
        return False

    # --- Firestore doc <-> dataclass mappers ---

    def get_fired_alerts(self, hours_back: int = 168) -> list[dict]:
        """Return fired alerts within the time window, newest first."""
        if not hours_back or hours_back <= 0:
            docs = self._fired.order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
            return [{"rule_id": d.to_dict().get("rule_id"), "timestamp": d.to_dict().get("timestamp"), "seen": d.to_dict().get("seen")} for d in docs]
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_back)
        docs = self._fired.where(
            filter=firestore.FieldFilter("timestamp", ">=", cutoff.isoformat())
        ).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
        return [{"rule_id": d.to_dict().get("rule_id"), "timestamp": d.to_dict().get("timestamp"), "seen": d.to_dict().get("seen")} for d in docs]

    @staticmethod
    def _to_rule(doc) -> Rule:
        d = doc.to_dict() or {}
        return Rule(
            id=doc.id,
            template_name=TemplateName(d.get("template_name")),
            params=d.get("params") or {},
            created_at=d.get("created_at", ""),
            last_evaluated_at=d.get("last_evaluated_at"),
            evaluation_count=d.get("evaluation_count", 0),
            last_fired_at=d.get("last_fired_at"),
            last_seen=d.get("last_seen"),
        )

    @staticmethod
    def _to_opportunity(doc) -> Opportunity:
        d = doc.to_dict() or {}
        return Opportunity(
            id=doc.id,
            user_request=d.get("user_request", ""),
            reason=d.get("reason", ""),
            category=d.get("category", ""),
            created_at=d.get("created_at", ""),
        )
