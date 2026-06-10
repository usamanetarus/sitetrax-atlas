"""Optional Cloud Scheduler cleanup for rule-specific jobs."""

from __future__ import annotations

import os
from typing import Any

from .rule_store import Rule


def _candidate_job_names(rule: Rule) -> list[str]:
    params = rule.params or {}
    candidates: list[str] = []
    for key in (
        "scheduler_job_name",
        "scheduler_job",
        "cloud_scheduler_job_name",
        "cloud_scheduler_job",
    ):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())

    prefix = os.environ.get("CLOUD_SCHEDULER_RULE_JOB_PREFIX", "").strip()
    if prefix:
        candidates.append(f"{prefix}-{rule.id}")

    seen: set[str] = set()
    return [name for name in candidates if not (name in seen or seen.add(name))]


def delete_rule_scheduler_jobs(rule: Rule) -> dict[str, Any]:
    """Delete per-rule Cloud Scheduler jobs when rule metadata names them.

    The production deploy currently creates one global scheduler job for
    `/tasks/evaluate`; that job must stay alive while any rules exist. This helper
    only deletes rule-specific jobs if future rule creation stores a job name, or
    if a per-rule naming prefix is configured.
    """

    job_names = _candidate_job_names(rule)
    if not job_names:
        return {
            "attempted": False,
            "deleted": [],
            "missing": [],
            "errors": [],
            "detail": "No rule-specific Cloud Scheduler job metadata found.",
        }

    try:
        from google.api_core.exceptions import NotFound
        from google.cloud import scheduler_v1
    except Exception as exc:
        return {
            "attempted": True,
            "deleted": [],
            "missing": [],
            "errors": [f"Cloud Scheduler client unavailable: {exc}"],
            "detail": "Install google-cloud-scheduler and configure ADC to delete scheduler jobs.",
        }

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    location = (
        os.environ.get("CLOUD_SCHEDULER_LOCATION")
        or os.environ.get("CLOUD_RUN_REGION")
        or os.environ.get("REGION")
    )
    if not project or not location:
        return {
            "attempted": True,
            "deleted": [],
            "missing": [],
            "errors": ["GOOGLE_CLOUD_PROJECT and CLOUD_SCHEDULER_LOCATION/REGION are required."],
            "detail": "Cloud Scheduler cleanup is configured incompletely.",
        }

    client = scheduler_v1.CloudSchedulerClient()
    deleted: list[str] = []
    missing: list[str] = []
    errors: list[str] = []

    for job_name in job_names:
        full_name = job_name if job_name.startswith("projects/") else client.job_path(project, location, job_name)
        try:
            client.delete_job(name=full_name)
            deleted.append(full_name)
        except NotFound:
            missing.append(full_name)
        except Exception as exc:
            errors.append(f"{full_name}: {exc}")

    return {
        "attempted": True,
        "deleted": deleted,
        "missing": missing,
        "errors": errors,
        "detail": "Rule-specific Cloud Scheduler cleanup completed." if not errors else "Cloud Scheduler cleanup failed.",
    }
