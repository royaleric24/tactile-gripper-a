"""Constants shared by the S1 protocol, adapters and application core.

The values here are either FACTs taken from existing project documents or
explicitly marked SW-PROPOSAL values.  They are not hardware measurements.
"""

from __future__ import annotations

PROTOCOL_VERSION = 1
CONTRACT_VERSION = "0.1"
SOFTWARE_VERSION = "0.3.0-p3a"

MAX_SENSOR_LINE_BYTES = 16384
DEFAULT_SENSOR_STALE_S = 2.0
MAX_TRACKED_ANOMALIES = 200

TRIAL_SCHEMA_VERSION = 3
TRIAL_LOCK_FILENAME = "recording.json"
TRIAL_LOCK_STALE_S = 30.0

SENSOR_MESSAGE_TYPES = ("HELLO", "SAMPLE", "STATUS", "ERROR")

# Software action -> firmware command actually sent by the existing S3 Bench
# protocol.  ``None`` means the action has no verified firmware command.
FIRMWARE_COMMAND_MAP = {
    "QUERY_STATUS": "GET_STATUS",
    "BEGIN_SESSION": "BEGIN_BENCH+BENCH_HOLD_MODE",
    "SET_PWM": "BENCH_HOLD",
    "STOP": "STOP",
    "DISARM": "DISARM",
    "HEARTBEAT": "HEARTBEAT",
    "STOP_UPDATES": None,
    "HOLD": None,
    "RELEASE": None,
}

SOFTWARE_ONLY_ACTIONS = ("STOP_UPDATES",)
UNSUPPORTED_FIRMWARE_ACTIONS = ("HOLD", "RELEASE")
