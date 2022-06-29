"""Constants used by Landroid Cloud."""
from __future__ import annotations

API_BASE = "https://{}/api/v2"

UNWANTED_ATTRIBS = [
    "distance_covered",
    "blade_work_time",
    "blade_work_time_reset",
    "blade_work_time_reset_at",
    "battery_charge_cycles",
    "battery_charge_cycles_reset",
    "battery_charge_cycles_reset_at",
    "app_settings",
    "features",
    "iot_registered",
    "pending_radio_link_validation",
    "purchased_at",
    "push_notifications",
    "push_notifications_level",
    "created_at",
    "test",
    "updated_at",
    "warranty_registered",
    "warranty_expires_at",
    "user_id",
    "firmware_auto_upgrade",
    "firmware_version",
    "auto_schedule",
    "auto_schedule_settings",
    "lawn_perimeter",
    "lawn_size",
    "mqtt_topics",
    "mqtt_endpoint",
    "messages_in",
    "messages_out",
    "raw_messages_in",
    "raw_messages_out",
]

CONST_UNKNOWN = "unknown"
