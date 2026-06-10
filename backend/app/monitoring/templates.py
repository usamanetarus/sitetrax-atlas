"""Template definitions for monitoring agent types."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TemplateName(str, Enum):
    CONTAINER_ARRIVAL = "container_arrival"
    DWELL_TIME = "dwell_time"
    STATUS_CHANGE = "status_change"
    FACILITY_DEPARTURE = "facility_departure"
    LOW_CONFIDENCE = "low_confidence"
    REVIEW_QUEUE = "review_queue"
    CAMERA_OFFLINE = "camera_offline"


@dataclass
class TemplateParam:
    name: str
    description: str
    param_type: str  # "string", "number", "location"
    required: bool = True


@dataclass
class Template:
    name: TemplateName
    display_name: str
    description: str
    params: list[TemplateParam]
    trigger_description: str
    action_description: str


TEMPLATES: dict[TemplateName, Template] = {
    TemplateName.CONTAINER_ARRIVAL: Template(
        name=TemplateName.CONTAINER_ARRIVAL,
        display_name="Container Arrival Monitor",
        description="Notifies you when a specific container is detected arriving at a yard or gate.",
        params=[
            TemplateParam(
                name="container_id",
                description="The container ID to watch for (e.g. TRBU5341840)",
                param_type="string",
                required=True,
            ),
            TemplateParam(
                name="location",
                description="The yard or gate location to monitor (e.g. Utah Intermodal Ramp)",
                param_type="string",
                required=False,
            ),
        ],
        trigger_description="Container ID detected at the specified location",
        action_description="Send notification with container details, timestamp, and GPS coordinates",
    ),
    TemplateName.DWELL_TIME: Template(
        name=TemplateName.DWELL_TIME,
        display_name="Dwell-Time Exception Monitor",
        description="Alerts you when an asset stays at a location longer than a specified threshold.",
        params=[
            TemplateParam(
                name="container_id",
                description="The container ID to monitor (optional — leave empty to watch all)",
                param_type="string",
                required=False,
            ),
            TemplateParam(
                name="location",
                description="The yard or gate location to monitor",
                param_type="string",
                required=True,
            ),
            TemplateParam(
                name="threshold_hours",
                description="Alert if asset dwells longer than this many hours",
                param_type="number",
                required=True,
            ),
        ],
        trigger_description="Asset dwell time exceeds threshold at the location",
        action_description="Send alert with dwell duration, asset details, and location",
    ),
    TemplateName.STATUS_CHANGE: Template(
        name=TemplateName.STATUS_CHANGE,
        display_name="Status Change Monitor",
        description="Alerts you when a container's SiteTrax status code changes (e.g. from A0 to A1).",
        params=[
            TemplateParam(
                name="container_id",
                description="The container ID to monitor",
                param_type="string",
                required=True,
            ),
            TemplateParam(
                name="from_status",
                description="Original status code to watch for changes from (e.g. A0). Leave empty to alert on any change.",
                param_type="string",
                required=False,
            ),
            TemplateParam(
                name="to_status",
                description="New status code to watch for changes to (e.g. A1). Leave empty to alert on any change.",
                param_type="string",
                required=False,
            ),
        ],
        trigger_description="Container status code changes",
        action_description="Send alert with old status, new status, and detection details",
    ),
    TemplateName.FACILITY_DEPARTURE: Template(
        name=TemplateName.FACILITY_DEPARTURE,
        display_name="Facility Departure Monitor",
        description="Alerts you when a container is no longer detected at a facility (suggesting departure).",
        params=[
            TemplateParam(
                name="container_id",
                description="The container ID to monitor",
                param_type="string",
                required=True,
            ),
            TemplateParam(
                name="location",
                description="The facility/yard to monitor",
                param_type="string",
                required=True,
            ),
            TemplateParam(
                name="threshold_hours",
                description="Alert if container has not been seen for this many hours (suggesting departure)",
                param_type="number",
                required=True,
            ),
        ],
        trigger_description="Container not detected at facility for longer than threshold",
        action_description="Send alert suggesting the container may have departed",
    ),
    TemplateName.LOW_CONFIDENCE: Template(
        name=TemplateName.LOW_CONFIDENCE,
        display_name="Low-Confidence Detection Monitor",
        description="Alerts you when a low-confidence or partial read is detected at a facility.",
        params=[
            TemplateParam(
                name="location",
                description="The facility/yard to monitor (leave empty for all facilities)",
                param_type="string",
                required=False,
            ),
            TemplateParam(
                name="min_status",
                description="Minimum status code threshold (e.g. I1 — alerts on I1 and higher status codes)",
                param_type="string",
                required=False,
            ),
        ],
        trigger_description="Low-confidence or partial detection occurs",
        action_description="Send alert with detection details for manual review",
    ),

    TemplateName.REVIEW_QUEUE: Template(
        name=TemplateName.REVIEW_QUEUE,
        display_name="Review Queue Monitor",
        description="Alerts when the A0 confidence rate at a facility drops below a threshold.",
        params=[
            TemplateParam(
                name="location",
                description="The facility/yard to monitor",
                param_type="string",
                required=True,
            ),
            TemplateParam(
                name="threshold_percent",
                description="Alert if A0 rate drops below this percentage (e.g. 90 for 90 percent)",
                param_type="number",
                required=True,
            ),
        ],
        trigger_description="A0 rate at facility drops below threshold",
        action_description="Send alert with A0 rate, review rate, and sample detections needing review",
    ),
    TemplateName.CAMERA_OFFLINE: Template(
        name=TemplateName.CAMERA_OFFLINE,
        display_name="Camera Offline Monitor",
        description="Alerts when a camera has not produced detections for a specified period.",
        params=[
            TemplateParam(
                name="camera",
                description="The camera name/serial to monitor",
                param_type="string",
                required=True,
            ),
            TemplateParam(
                name="threshold_hours",
                description="Alert if no detections for this many hours",
                param_type="number",
                required=True,
            ),
        ],
        trigger_description="Camera has not produced detections within threshold hours",
        action_description="Send alert suggesting camera may be offline or malfunctioning",
    ),}


TEMPLATE_DESCRIPTIONS_FOR_PROMPT = "\\n".join([
    f"- {t.display_name} (id: {t.name.value}): {t.description} "
    f"Params: {', '.join(p.name for p in t.params)}"
    for t in TEMPLATES.values()
])
