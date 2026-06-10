"""Rule evaluation + alert dispatch.

Shared by the manual `/simulate-event` trigger, the automatic `/tasks/evaluate` endpoint,
and the optional background poller. `_fire` records the evaluation, marks dedup state, and
dispatches a notification.
"""

import datetime
import logging

from app.data import query_assets, get_latest_scan
from app.monitoring import store
from app.monitoring.templates import TemplateName
from app.data.sitetrax_client import get_asset_timeline
from app.notifications import notify_alert

logger = logging.getLogger("sitetrax")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _fire(rule, trigger_text: str, seen: str | None = None) -> dict:
    """Record + dedup-mark + notify for a fired rule. Returns the alert dict."""
    now_iso = _now().isoformat()
    store.record_evaluation(rule.id)
    store.mark_fired(rule.id, now_iso, seen=seen)
    alert = {
        "rule_id": rule.id,
        "template": rule.template_name.value,
        "trigger": trigger_text,
        "timestamp": now_iso,
    }
    notify_alert(alert, rule.params.get("email"))
    return alert


def _parse_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def evaluate_event(
    container_id: str,
    location: str,
    dwell_hours: float | None = None,
    rule_id: str | None = None,
    hours_back: int = 24,
) -> list[dict]:
    """Evaluate an explicit detection event.

    When `rule_id` is provided, only that rule is evaluated. This keeps simulation
    scoped to the rule the UI is testing instead of fanning out into unrelated rules
    whose own data lookups can produce false positives.
    """
    now = _now()
    alerts: list[dict] = []
    rules = store.get_all_rules()
    if rule_id is not None:
        rules = [rule for rule in rules if rule.id == rule_id]

    for rule in rules:
        matched = False
        trigger_text = ""

        if rule.template_name == TemplateName.CONTAINER_ARRIVAL:
            cid = rule.params.get("container_id", "").upper()
            loc = rule.params.get("location", "")
            if container_id.upper() == cid or (cid and cid in container_id.upper()):
                if not loc or loc.lower() in location.lower():
                    matched = True
                    trigger_text = f"Container {container_id} detected at {location}"

        elif rule.template_name == TemplateName.DWELL_TIME:
            rule_cid = rule.params.get("container_id", "")
            rule_loc = rule.params.get("location", "")
            threshold = rule.params.get("threshold_hours", 0)
            check_cid = rule_cid if rule_cid else container_id
            if rule_loc.lower() not in location.lower():
                continue
            if dwell_hours is not None:
                dwell = dwell_hours
            else:
                scan = get_latest_scan(check_cid)
                if scan:
                    scan_dt = datetime.datetime.fromisoformat(scan["datetime"])
                    dwell = (now - scan_dt).total_seconds() / 3600.0
                else:
                    dwell = 0.0
            try:
                threshold = float(threshold)
            except (TypeError, ValueError):
                threshold = 0.0
            if dwell > threshold:
                matched = True
                trigger_text = (
                    f"Container {check_cid} has been at {location} for "
                    f"{dwell:.1f}h (threshold: {threshold:.1f}h)"
                )

        if matched:
            alerts.append(_fire(rule, trigger_text))

        elif rule.template_name == TemplateName.STATUS_CHANGE:
            rule_cid = rule.params.get("container_id", "")
            from_status = rule.params.get("from_status", "")
            to_status = rule.params.get("to_status", "")
            if not rule_cid:
                continue
            timeline = get_asset_timeline(rule_cid)
            if len(timeline) < 2:
                continue
            latest = timeline[0]
            previous = timeline[1]
            latest_status = latest.get("status_code", "")
            prev_status = previous.get("status_code", "")
            if latest_status == prev_status:
                continue
            if from_status and prev_status != from_status:
                continue
            if to_status and latest_status != to_status:
                continue
            matched = True
            trigger_text = (
                f"Container {rule_cid} status changed from {prev_status} to {latest_status} "
                f"at {latest.get('location', 'unknown')}"
            )
            alerts.append(_fire(rule, trigger_text, seen=latest.get("datetime")))

        elif rule.template_name == TemplateName.FACILITY_DEPARTURE:
            rule_cid = rule.params.get("container_id", "")
            loc = rule.params.get("location", "")
            threshold = rule.params.get("threshold_hours", 0)
            if not rule_cid or not loc:
                continue
            try:
                threshold = float(threshold)
            except (TypeError, ValueError):
                threshold = 0.0
            timeline = get_asset_timeline(rule_cid)
            facility_scans = [t for t in timeline if loc.lower() in (t.get("location") or "").lower()]
            if not facility_scans:
                continue
            latest = facility_scans[0]
            try:
                latest_dt = datetime.datetime.fromisoformat(latest.get("datetime", ""))
            except (ValueError, TypeError):
                continue
            hours_since = (now - latest_dt).total_seconds() / 3600.0
            if hours_since <= threshold:
                continue
            # Dedup: only alert if we haven't seen this specific scan before
            if rule.last_seen == latest.get("datetime"):
                continue
            matched = True
            trigger_text = (
                f"Container {rule_cid} not seen at {loc} for {hours_since:.1f}h "
                f"(threshold: {threshold:.1f}h). May have departed."
            )
            alerts.append(_fire(rule, trigger_text, seen=latest.get("datetime")))

        elif rule.template_name == TemplateName.LOW_CONFIDENCE:
            loc = rule.params.get("location", "")
            min_status = rule.params.get("min_status", "I1")
            scans = query_assets(location=loc or None, hours_back=hours_back)
            low_conf = [s for s in scans if (s.get("status_code") or "A0") != "A0"]
            if min_status:
                # Simple heuristic: I1-I7 are low confidence, A1 is assigned
                low_conf = [s for s in low_conf if s.get("status_code", "") >= min_status]
            if not low_conf:
                continue
            latest = max(low_conf, key=lambda a: a.get("datetime", ""))
            if rule.last_seen == latest.get("datetime"):
                continue
            matched = True
            trigger_text = (
                f"Low-confidence detection at {latest.get('location', loc)}: "
                f"{latest.get('text', 'unknown')} (status: {latest.get('status_code', 'unknown')})"
            )
            alerts.append(_fire(rule, trigger_text, seen=latest.get("datetime")))

        elif rule.template_name == TemplateName.REVIEW_QUEUE:
            loc = rule.params.get("location", "")
            threshold_percent = _parse_float(rule.params.get("threshold_percent", 0.0))
            scans = query_assets(location=loc or None, hours_back=hours_back)
            if not scans:
                continue
            total = len(scans)
            review_items = [s for s in scans if (s.get("status_code") or "A0") != "A0"]
            review_rate = (len(review_items) / total) * 100.0 if total else 0.0
            a0_rate = 100.0 - review_rate
            latest = max(scans, key=lambda a: a.get("datetime", ""))
            if a0_rate >= threshold_percent:
                continue
            if rule.last_seen == latest.get("datetime"):
                continue
            trigger_text = (
                f"A0 rate at {latest.get('location', loc)} is {a0_rate:.1f}% "
                f"(threshold: {threshold_percent:.1f}%) with review rate {review_rate:.1f}% "
                f"and {len(review_items)}/{total} detections needing review"
            )
            alerts.append(_fire(rule, trigger_text, seen=latest.get("datetime")))

        elif rule.template_name == TemplateName.CAMERA_OFFLINE:
            camera = rule.params.get("camera", "")
            threshold_hours = _parse_float(rule.params.get("threshold_hours", 0.0))
            if not camera:
                continue
            scans = query_assets(camera=camera, hours_back=0)
            if not scans:
                sentinel = f"offline:{camera}"
                if rule.last_seen != sentinel:
                    alerts.append(_fire(
                        rule,
                        f"Camera {camera} has produced no detections in the available history",
                        seen=sentinel,
                    ))
                continue
            latest = max(scans, key=lambda a: a.get("datetime", ""))
            latest_dt_raw = latest.get("datetime", "")
            try:
                latest_dt = datetime.datetime.fromisoformat(latest_dt_raw)
            except (ValueError, TypeError):
                continue
            hours_since = (now - latest_dt).total_seconds() / 3600.0
            if hours_since <= threshold_hours:
                continue
            if rule.last_seen == latest_dt_raw:
                continue
            trigger_text = (
                f"Camera {camera} has not produced detections for {hours_since:.1f}h "
                f"(threshold: {threshold_hours:.1f}h)"
            )
            alerts.append(_fire(rule, trigger_text, seen=latest_dt_raw))

    return alerts


def evaluate_recent(hours_back: int = 24) -> list[dict]:
    """Automatic pass: poll the active data source and fire new alerts (deduped via last_seen)."""
    now = _now()
    alerts: list[dict] = []
    for rule in store.get_all_rules():
        if rule.template_name == TemplateName.CONTAINER_ARRIVAL:
            cid = rule.params.get("container_id", "")
            loc = rule.params.get("location", "")
            scans = query_assets(container_id=cid or None, location=loc or None, hours_back=hours_back)
            if not scans:
                continue
            latest = max(scans, key=lambda a: a.get("datetime", ""))
            latest_dt = latest.get("datetime", "")
            if rule.last_seen and latest_dt <= rule.last_seen:  # dedup: only newer scans
                continue
            trigger = f"Container {latest.get('text', cid)} detected at {latest.get('location', loc)}"
            alerts.append(_fire(rule, trigger, seen=latest_dt))

        elif rule.template_name == TemplateName.DWELL_TIME:
            cid = rule.params.get("container_id", "")
            loc = rule.params.get("location", "")
            threshold = rule.params.get("threshold_hours", 0)
            try:
                threshold = float(threshold)
            except (TypeError, ValueError):
                threshold = 0.0
            if cid:
                scan = get_latest_scan(cid)
            else:
                scans = query_assets(location=loc or None, hours_back=hours_back)
                scan = max(scans, key=lambda a: a.get("datetime", "")) if scans else None
            if not scan:
                continue
            try:
                scan_dt = datetime.datetime.fromisoformat(scan["datetime"])
            except (ValueError, TypeError, KeyError):
                continue
            dwell = (now - scan_dt).total_seconds() / 3600.0
            if dwell <= threshold:
                continue
            if rule.last_seen == scan.get("datetime"):  # dedup: same scan already alerted
                continue
            trigger = (
                f"Container {scan.get('text', cid)} has been at {scan.get('location', loc)} for "
                f"{dwell:.1f}h (threshold: {threshold:.1f}h)"
            )
            alerts.append(_fire(rule, trigger, seen=scan.get("datetime")))

        elif rule.template_name == TemplateName.STATUS_CHANGE:
            cid = rule.params.get("container_id", "")
            from_status = rule.params.get("from_status", "")
            to_status = rule.params.get("to_status", "")
            if not cid:
                continue
            timeline = get_asset_timeline(cid)
            if len(timeline) < 2:
                continue
            latest = timeline[0]
            previous = timeline[1]
            latest_status = latest.get("status_code", "")
            prev_status = previous.get("status_code", "")
            if latest_status == prev_status:
                continue
            if from_status and prev_status != from_status:
                continue
            if to_status and latest_status != to_status:
                continue
            if rule.last_seen == latest.get("datetime"):
                continue
            trigger = (
                f"Container {cid} status changed from {prev_status} to {latest_status} "
                f"at {latest.get('location', 'unknown')}"
            )
            alerts.append(_fire(rule, trigger, seen=latest.get("datetime")))

        elif rule.template_name == TemplateName.FACILITY_DEPARTURE:
            cid = rule.params.get("container_id", "")
            loc = rule.params.get("location", "")
            threshold = rule.params.get("threshold_hours", 0)
            if not cid or not loc:
                continue
            try:
                threshold = float(threshold)
            except (TypeError, ValueError):
                threshold = 0.0
            timeline = get_asset_timeline(cid)
            facility_scans = [t for t in timeline if loc.lower() in (t.get("location") or "").lower()]
            if not facility_scans:
                continue
            latest = facility_scans[0]
            try:
                latest_dt = datetime.datetime.fromisoformat(latest.get("datetime", ""))
            except (ValueError, TypeError):
                continue
            dwell = (now - latest_dt).total_seconds() / 3600.0
            if dwell <= threshold:
                continue
            if rule.last_seen == latest.get("datetime"):
                continue
            trigger = (
                f"Container {cid} not seen at {loc} for {dwell:.1f}h "
                f"(threshold: {threshold:.1f}h). May have departed."
            )
            alerts.append(_fire(rule, trigger, seen=latest.get("datetime")))

        elif rule.template_name == TemplateName.LOW_CONFIDENCE:
            loc = rule.params.get("location", "")
            min_status = rule.params.get("min_status", "I1")
            scans = query_assets(location=loc or None, hours_back=hours_back)
            low_conf = [s for s in scans if (s.get("status_code") or "A0") != "A0"]
            if min_status:
                low_conf = [s for s in low_conf if s.get("status_code", "") >= min_status]
            if not low_conf:
                continue
            latest = max(low_conf, key=lambda a: a.get("datetime", ""))
            if rule.last_seen == latest.get("datetime"):
                continue
            trigger = (
                f"Low-confidence detection at {latest.get('location', loc)}: "
                f"{latest.get('text', 'unknown')} (status: {latest.get('status_code', 'unknown')})"
            )
            alerts.append(_fire(rule, trigger, seen=latest.get("datetime")))

        elif rule.template_name == TemplateName.REVIEW_QUEUE:
            loc = rule.params.get("location", "")
            threshold_percent = _parse_float(rule.params.get("threshold_percent", 0.0))
            scans = query_assets(location=loc or None, hours_back=hours_back)
            if not scans:
                continue
            total = len(scans)
            review_items = [s for s in scans if (s.get("status_code") or "A0") != "A0"]
            review_rate = (len(review_items) / total) * 100.0 if total else 0.0
            a0_rate = 100.0 - review_rate
            latest = max(scans, key=lambda a: a.get("datetime", ""))
            if a0_rate >= threshold_percent:
                continue
            if rule.last_seen == latest.get("datetime"):
                continue
            trigger = (
                f"A0 rate at {latest.get('location', loc)} is {a0_rate:.1f}% "
                f"(threshold: {threshold_percent:.1f}%) with review rate {review_rate:.1f}% "
                f"and {len(review_items)}/{total} detections needing review"
            )
            alerts.append(_fire(rule, trigger, seen=latest.get("datetime")))

        elif rule.template_name == TemplateName.CAMERA_OFFLINE:
            camera = rule.params.get("camera", "")
            threshold_hours = _parse_float(rule.params.get("threshold_hours", 0.0))
            if not camera:
                continue
            scans = query_assets(camera=camera, hours_back=0)
            if not scans:
                sentinel = f"offline:{camera}"
                if rule.last_seen != sentinel:
                    alerts.append(_fire(
                        rule,
                        f"Camera {camera} has produced no detections in the available history",
                        seen=sentinel,
                    ))
                continue
            latest = max(scans, key=lambda a: a.get("datetime", ""))
            latest_dt_raw = latest.get("datetime", "")
            try:
                latest_dt = datetime.datetime.fromisoformat(latest_dt_raw)
            except (ValueError, TypeError):
                continue
            hours_since = (now - latest_dt).total_seconds() / 3600.0
            if hours_since <= threshold_hours:
                continue
            if rule.last_seen == latest_dt_raw:
                continue
            trigger = (
                f"Camera {camera} has not produced detections for {hours_since:.1f}h "
                f"(threshold: {threshold_hours:.1f}h)"
            )
            alerts.append(_fire(rule, trigger, seen=latest_dt_raw))

    return alerts
