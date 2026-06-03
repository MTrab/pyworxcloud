"""Constants used by Landroid Cloud."""

from __future__ import annotations

API_BASE = "https://{}/api/v2"
API_REFRESH_TIME_MIN = 5
API_REFRESH_TIME_MAX = 10
DEFAULT_COMMAND_TIMEOUT = 30.0
DEFAULT_MQTT_CONNECT_TIMEOUT = 8.0
MQTT_RECONNECT_RETRY_SECONDS = 15 * 60
PAHO_MQTT_RECONNECT_MIN_DELAY_SECONDS = 60
PAHO_MQTT_RECONNECT_MAX_DELAY_SECONDS = 30 * 60
VISION_BORDER_DISTANCE_MM_VALUES = (50, 100, 150, 200)

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
