"""In-memory rule store with evaluation and opportunity capture."""

import uuid
import datetime
from dataclasses import dataclass, field
from typing import Any

from .templates import TemplateName


@dataclass
class Rule:
    id: str
    template_name: TemplateName
    params: dict[str, Any]
    created_at: str
    last_evaluated_at: str | None = None
    evaluation_count: int = 0
    last_fired_at: str | None = None
    last_seen: str | None = None


@dataclass
class Opportunity:
    id: str
    user_request: str
    reason: str
    category: str
    created_at: str


class RuleStore:
    """In-memory store for monitoring rules and opportunities."""

    def __init__(self):
        self._rules: dict[str, Rule] = {}
        self._opportunities: list[Opportunity] = []
        self._fired_alerts: list[dict] = []
        self._max_fired_alerts = 200

    def create_rule(self, template_name: TemplateName, params: dict[str, Any]) -> Rule:
        rule = Rule(
            id=str(uuid.uuid4())[:8],
            template_name=template_name,
            params=params,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        self._rules[rule.id] = rule
        return rule

    def find_duplicate_rule(self, template_name: TemplateName, params: dict[str, Any]) -> Rule | None:
        for rule in self._rules.values():
            if rule.template_name == template_name and rule.params == params:
                return rule
        return None

    def get_rule(self, rule_id: str) -> Rule | None:
        return self._rules.get(rule_id)

    def get_all_rules(self) -> list[Rule]:
        return list(self._rules.values())

    def delete_rule(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def record_evaluation(self, rule_id: str):
        rule = self._rules.get(rule_id)
        if rule:
            rule.last_evaluated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            rule.evaluation_count += 1

    def mark_fired(self, rule_id: str, when: str, seen: str | None = None):
        rule = self._rules.get(rule_id)
        if rule:
            rule.last_fired_at = when
            if seen is not None:
                rule.last_seen = seen
        self._fired_alerts.append({
            "rule_id": rule_id,
            "timestamp": when,
            "seen": seen,
        })
        if len(self._fired_alerts) > self._max_fired_alerts:
            self._fired_alerts = self._fired_alerts[-self._max_fired_alerts:]

    # --- Opportunity capture (the differentiator) ---

    def log_opportunity(self, user_request: str, reason: str, category: str) -> Opportunity:
        opp = Opportunity(
            id=str(uuid.uuid4())[:8],
            user_request=user_request,
            reason=reason,
            category=category,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        self._opportunities.append(opp)
        return opp

    def get_opportunities(self) -> list[Opportunity]:
        return list(self._opportunities)

    def delete_opportunity(self, opportunity_id: str) -> bool:
        before = len(self._opportunities)
        self._opportunities = [opp for opp in self._opportunities if opp.id != opportunity_id]
        return len(self._opportunities) != before

    def get_fired_alerts(self, hours_back: int = 168) -> list[dict]:
        """Return fired alerts within the time window, newest first."""
        if not hours_back or hours_back <= 0:
            return list(reversed(self._fired_alerts))
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_back)
        filtered = []
        for alert in reversed(self._fired_alerts):
            try:
                ts = datetime.datetime.fromisoformat(alert.get("timestamp", ""))
                if ts >= cutoff:
                    filtered.append(alert)
            except (ValueError, TypeError):
                continue
        return filtered
