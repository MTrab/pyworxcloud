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
    "mac_address",
    "serial_number",
    "setup_location",
    "product_id",
    "created_at",
    "app_settings",
    "iot_registered",
    "pending_radio_link_validation",
    "purchased_at",
    "push_notifications",
    "push_notifications_level",
    "warranty_expires_at",
    "warranty_registered",
    "updated_at",
    "test",
    "sim",
    "messages_in",
    "messages_out",
    "raw_messages_in",
    "raw_messages_out",
    "mqtt_registered",
    "mqtt_endpoint",
    "features",
    "accessories",
]
