"""Read-only LIVE monitoring of the two JSONL logs written by existing tools.

The S3 console (``scripts/pwm_console.py``) owns the control serial port and the
FSR capture (``scripts/capture_fsr_live.py``) owns the sensor serial port.  The
Dashboard must never open either port while they run, otherwise macOS gives a
second reader interleaved bytes and a second writer could command PWM.

This module adds a *file* data path instead:

* :class:`JsonlTail` incrementally follows a JSONL file, tolerating partial
  lines, truncation and rotation.
* :class:`LogFollowGripper` parses the console ``transport.jsonl`` and exposes
  the same read-only surface the Dashboard uses for ``GripperAdapter``.  Every
  command keeps its own ``sent`` / ``acked`` / ``failed`` state; a missing ACK
  is never reported as success.  ``execute()`` always raises.
* :class:`LogFollowSensorAdapter` feeds recorded FSR lines through the existing
  strict V2 parser, so channel validation, frame sequence checks and channel
  flags stay identical to a direct serial read.

Nothing here imports pyserial or opens a device.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..errors import ControlDenied, SensorOffline
from ..models import ControlEvent, DeviceStatus
from ..sources import DataSource
from .sensor import SensorAdapter

PROJECT_ROOT = Path(__file__).resolve().parents[3]

#: Firmware commands that command a PWM output.
PWM_COMMANDS = ("BENCH_HOLD", "BENCH_PULSE")
#: Firmware commands that end the output; after their ACK no old target is live.
STOP_COMMANDS = ("STOP", "DISARM")
#: Console events that mean a response was lost/corrupted.
COMM_ERROR_REASONS = ("corrupt_response", "oversize_response", "envelope_or_id")
#: Sensor message types the FSR log may contain.
SENSOR_TYPES = ("HELLO", "SAMPLE", "STATUS", "ERROR")

DEFAULT_LOG_STALE_S = 3.0
DEFAULT_FSR_STALE_S = 3.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_to_epoch(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(str(stamp)).timestamp()
    except (TypeError, ValueError):
        return None


class JsonlTail:
    """Incremental follower for a JSONL file written by another process.

    The reader keeps its byte offset, not a line index, so it can resume after
    a partial write.  A file that shrinks is treated as truncated and re-read
    from the start; a file whose inode changed is treated as rotated.  Both
    counters are surfaced so the UI can explain a restart instead of mixing
    two sessions silently.
    """

    def __init__(
        self,
        path: Path | str,
        *,
        max_line_bytes: int = 65536,
        max_initial_bytes: int = 4_000_000,
        clock=time.monotonic,
    ):
        self.path = Path(path)
        self.max_line_bytes = int(max_line_bytes)
        self.max_initial_bytes = int(max_initial_bytes)
        self._clock = clock
        self._lock = threading.RLock()
        self._fh = None
        self._offset = 0
        self._partial = b""
        self._skip_partial = False
        self._identity: tuple[int, int] | None = None
        self.lines_read = 0
        self.overlong_lines = 0
        self.truncations = 0
        self.rotations = 0
        self.missing = not self.path.is_file()
        self.last_line_ns: int | None = None
        self.last_read_ns: int | None = None

    # -- lifecycle ---------------------------------------------------------

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    def connect(self) -> None:
        if not self.exists:
            raise FileNotFoundError(f"log file not found: {self.path}")
        with self._lock:
            if self._fh is None:
                self._open_at(0)

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                except OSError:
                    pass
            self._fh = None
            self._offset = 0
            self._partial = b""
            self._identity = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _open_at(self, offset: int) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
        self._fh = open(self.path, "rb")
        self._fh.seek(offset)
        self._offset = offset
        stat = os.stat(self.path)
        self._identity = (stat.st_dev, stat.st_ino)

    # -- reading -----------------------------------------------------------

    def read_new(self) -> list[str]:
        """Return new, complete lines.  A trailing partial line is retained."""

        with self._lock:
            try:
                stat = os.stat(self.path)
            except OSError:
                self.missing = True
                self.close()
                return []
            self.missing = False
            if self._fh is None:
                start = 0
                if stat.st_size > self.max_initial_bytes:
                    # Keep the most recent window of a very large file.
                    start = max(0, stat.st_size - self.max_initial_bytes)
                self._open_at(start)
                self._skip_partial = start > 0
            elif (stat.st_dev, stat.st_ino) != self._identity:
                self.rotations += 1
                self._open_at(0)
                self._partial = b""
                self._skip_partial = False
            elif stat.st_size < self._offset:
                self.truncations += 1
                self._fh.seek(0)
                self._offset = 0
                self._partial = b""
                self._skip_partial = False

            self._fh.seek(self._offset)
            chunk = self._fh.read(max(0, stat.st_size - self._offset))
            self._offset += len(chunk)
            data = self._partial + chunk
            self._partial = b""
            if self._skip_partial:
                cut = data.find(b"\n")
                data = b"" if cut < 0 else data[cut + 1 :]
                self._skip_partial = False

            lines: list[str] = []
            while True:
                cut = data.find(b"\n")
                if cut < 0:
                    break
                raw = data[:cut]
                data = data[cut + 1 :]
                if raw.endswith(b"\r"):
                    raw = raw[:-1]
                if not raw.strip():
                    continue
                if len(raw) > self.max_line_bytes:
                    self.overlong_lines += 1
                    continue
                lines.append(raw.decode("utf-8", "replace"))
            if data:
                if len(data) > self.max_line_bytes:
                    # A single unterminated line beyond the limit: drop until
                    # the next newline instead of growing the buffer forever.
                    self.overlong_lines += 1
                    self._skip_partial = True
                else:
                    self._partial = data
            if lines:
                self.lines_read += len(lines)
                self.last_line_ns = time.monotonic_ns()
                self.last_read_ns = self._clock() * 1e9
            return lines

    # -- introspection -----------------------------------------------------

    def file_age_s(self) -> float | None:
        try:
            return max(0.0, time.time() - os.stat(self.path).st_mtime)
        except OSError:
            return None

    def describe(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "exists": self.exists,
            "age_s": self.file_age_s(),
            "lines_read": self.lines_read,
            "partial_bytes": len(self._partial),
            "overlong_lines": self.overlong_lines,
            "truncations": self.truncations,
            "rotations": self.rotations,
        }


class LogFollowGripper:
    """Read-only ``GripperAdapter`` substitute backed by the console log.

    It intentionally has no transport and no write path.  ``execute`` raises so
    a UI bug cannot turn the monitor into a second PWM writer.
    """

    read_only = True

    def __init__(
        self,
        log_path: Path | str,
        *,
        config_path: Path | str | None = None,
        source: DataSource = DataSource.LIVE,
        clock=time.monotonic,
        stale_after_s: float = DEFAULT_LOG_STALE_S,
    ):
        self.log_path = Path(log_path)
        self.source = DataSource(source)
        if self.source is not DataSource.LIVE:
            raise ControlDenied("log-follow monitor is a LIVE-source read-only view")
        self.clock = clock
        self.stale_after_s = max(0.1, float(stale_after_s))
        path = Path(config_path) if config_path else PROJECT_ROOT / "config" / "gripper_s3.json"
        try:
            self.config = json.loads(path.read_text(encoding="utf-8"))
            self.config_path = str(path)
        except (OSError, ValueError):
            self.config = {}
            self.config_path = None
        self.firmware_version = str(self.config.get("firmware_version") or "UNKNOWN")
        low = self.config.get("bench_min_us", 500)
        high = self.config.get("bench_max_us", 2500)
        if type(low) is not int or type(high) is not int or not 0 < low < high:
            low, high = 500, 2500
        self.pwm_min_us = low
        self.pwm_max_us = high
        initial = self.config.get("bench_initial_us")
        self.pwm_initial_us = initial if type(initial) is int and low <= initial <= high else None
        self.timeout_s = float(
            (self.config.get("serial") or {}).get("request_timeout_s", 3.0)
        )
        self.tail = JsonlTail(self.log_path, max_line_bytes=16384, clock=clock)
        self._lock = threading.RLock()
        self._events: deque[ControlEvent] = deque(maxlen=256)
        self._commands: deque[dict[str, Any]] = deque(maxlen=200)
        self._pending: dict[str, dict[str, Any]] = {}
        self._comm_errors: deque[dict[str, Any]] = deque(maxlen=40)
        self._pwm_events: deque[dict[str, Any]] = deque(maxlen=80)
        self._attach_utc = _utc_now()
        self.connected = False
        self.session_active = False
        self.state = "OFFLINE"
        self.last_status: dict[str, Any] | None = None
        self.last_error: str | None = None
        self.last_pwm_us: int | None = None
        self.current_target_us: int | None = None
        self.current_command_id: str | None = None
        self.target_status = "NO_PWM"
        self.target_age_s: float | None = None
        self.device_state: str | None = None
        self.output_state: str | None = None
        self.fault_reason: str | None = None
        self.boot_id: str | None = None
        self.last_response: dict[str, Any] | None = None
        self.last_event_utc: str | None = None
        self.last_event_ns: int | None = None
        self.last_response_utc: str | None = None
        self.last_response_ns: int | None = None
        self.closed = False
        self.session_restarts = 0
        self.closed_at_utc: str | None = None
        self.final_output_state: str | None = None
        self.session_mode: str | None = None
        self.counts = {
            "commands": 0,
            "pwm_commands": 0,
            "acked": 0,
            "failed": 0,
            "unconfirmed": 0,
            "corrupt_responses": 0,
            "timeouts": 0,
            "nul_bytes": 0,
            "bad_lines": 0,
        }

    # -- configuration -----------------------------------------------------

    @property
    def pwm_limits(self) -> dict[str, Any]:
        return {
            "min_us": self.pwm_min_us,
            "max_us": self.pwm_max_us,
            "initial_us": self.pwm_initial_us,
            "source": (self.config_path or "config/gripper_s3.json") + ":bench_min_us..bench_max_us",
            "note": "Bench config range; NOT a verified mechanical safety limit.",
        }

    @property
    def pwm_range_source(self) -> str:
        return str(self.pwm_limits["source"])

    # -- lifecycle ---------------------------------------------------------

    def connect(self, port: str | None = None) -> dict[str, Any]:
        del port  # a log has no port; accepted for interface compatibility
        with self._lock:
            if self.connected:
                raise ControlDenied("already_connected")
            if not self.tail.exists:
                self.state = "OFFLINE"
                self.last_error = f"PWM log not found: {self.log_path}"
                raise FileNotFoundError(str(self.log_path))
            self._ingest()
            self.connected = True
            self.session_active = not self.closed
            self.state = self._derived_state()
            self.last_error = None
            return {"monitor": "LOG_FOLLOW", "log_path": str(self.log_path)}

    def close(self, *, disarm: bool = True) -> None:
        del disarm
        with self._lock:
            self.tail.close()
            self.connected = False
            self.session_active = False
            self.state = "OFFLINE"

    def poll(self) -> None:
        with self._lock:
            if not self.connected:
                return
            self._ingest()
            self._expire_pending()
            self.state = self._derived_state()

    def stop_updates(self) -> None:
        """Host-side no-op: the console owns the real stop."""
        return None

    def execute(self, command, *, mode: str = "UNKNOWN") -> ControlEvent:
        raise ControlDenied(
            "LOG-FOLLOW monitor is read-only; PWM can only be sent by the "
            "pwm_console that owns the serial port"
        )

    def hold(self) -> None:
        raise ControlDenied("LOG-FOLLOW monitor is read-only")

    def release(self) -> None:
        raise ControlDenied("LOG-FOLLOW monitor is read-only")

    # -- ingestion ---------------------------------------------------------

    def drain_control_events(self) -> list[ControlEvent]:
        with self._lock:
            items = list(self._events)
            self._events.clear()
            return items

    def _ingest(self) -> None:
        for text in self.tail.read_new():
            try:
                record = json.loads(text)
            except ValueError:
                self.counts["bad_lines"] += 1
                continue
            if not isinstance(record, dict):
                self.counts["bad_lines"] += 1
                continue
            try:
                self._handle(record)
            except (TypeError, ValueError):
                self.counts["bad_lines"] += 1

    def _handle(self, record: dict[str, Any]) -> None:
        event = record.get("event")
        if not isinstance(event, str):
            return
        ts_utc = record.get("timestamp_utc") or record.get("host_time_utc")
        ts_ns = record.get("monotonic_ns") or record.get("host_monotonic_ns")
        if ts_utc:
            self.last_event_utc = str(ts_utc)
        if type(ts_ns) is int:
            self.last_event_ns = ts_ns

        if event == "COMMAND":
            self._on_command(record, ts_utc, ts_ns)
        elif event in ("MATCHED", "RESPONSE"):
            self._on_response(record, ts_utc, ts_ns, matched=event == "MATCHED")
        elif event == "IGNORED":
            self._on_ignored(record, ts_utc, ts_ns)
        elif event == "COMMUNICATION_ERROR":
            self._on_communication_error(record, ts_utc, ts_ns)
        elif event == "BENCH_ACTION":
            self._on_bench_action(record)
        elif event == "BENCH_MODE":
            self.session_mode = record.get("mode")
        elif event in ("CONNECTED", "STARTUP_READY"):
            if self.closed:
                self._start_new_session()
            self.connected = True
            self.closed = False
        elif event == "STARTUP_WAIT":
            self.connected = True
        elif event in ("CLOSED", "CONTROLLER_CLOSED"):
            self.closed = True
            self.closed_at_utc = ts_utc
            self.session_active = False
            if isinstance(record.get("output_state"), str):
                self.final_output_state = record["output_state"]
                self.output_state = self.final_output_state
            if event == "CLOSED":
                self.connected = False
            self._expire_pending(force=True)

    def _start_new_session(self) -> None:
        """A rotated/reconnected log starts a fresh display session.

        Keeping the previous session's ACKed target would present a stale
        value as the current output, which is exactly what this monitor must
        not do.  Command rows from the old session are dropped from the live
        table; the old file remains on disk untouched.
        """
        with self._lock:
            self.session_restarts += 1
            self._commands.clear()
            self._pending.clear()
            self._pwm_events.clear()
            self._comm_errors.clear()
            self.current_target_us = None
            self.last_pwm_us = None
            self.current_command_id = None
            self.target_status = "NO_PWM"
            self.target_age_s = None
            self.device_state = None
            self.output_state = None
            self.fault_reason = None
            self.closed_at_utc = None
            self.final_output_state = None
            self.counts = {key: 0 for key in self.counts}

    def _on_command(self, record: dict[str, Any], ts_utc, ts_ns) -> None:
        request = record.get("request") or {}
        if not isinstance(request, dict):
            return
        command = request.get("command")
        request_id = request.get("request_id")
        if not isinstance(command, str) or not isinstance(request_id, str):
            return
        row = {
            "seq": request.get("sequence"),
            "command": command,
            "request_id": request_id,
            "pulse_us": request.get("pulse_us"),
            "sent_utc": ts_utc,
            "sent_ns": ts_ns,
            "ack": None,
            "ack_type": None,
            "ack_utc": None,
            "ack_ns": None,
            "result": "SENT",
            "state": None,
            "output_state": None,
            "fault_reason": None,
            "error": None,
            "nul_count": 0,
            "_emitted": False,
        }
        self._commands.append(row)
        self._pending[request_id] = row
        self.counts["commands"] += 1
        if command in PWM_COMMANDS:
            self.counts["pwm_commands"] += 1

    def _find_row(self, request_id: str | None) -> dict[str, Any] | None:
        if not request_id:
            return None
        row = self._pending.get(request_id)
        if row is not None:
            return row
        for item in reversed(self._commands):
            if item["request_id"] == request_id:
                return item
        return None

    def _on_response(self, record: dict[str, Any], ts_utc, ts_ns, *, matched: bool) -> None:
        response = record.get("response") or {}
        if not isinstance(response, dict):
            return
        rid = response.get("request_id")
        row = self._find_row(rid if isinstance(rid, str) else None)
        self.last_response = response
        self.last_response_utc = ts_utc
        self.last_response_ns = ts_ns
        if row is not None and row["ack"] is None:
            row["ack"] = True
            row["ack_type"] = response.get("type")
            row["ack_utc"] = ts_utc
            row["ack_ns"] = ts_ns
            row["state"] = response.get("state")
            row["output_state"] = response.get("output_state")
            row["fault_reason"] = response.get("fault_reason")
            if response.get("type") == "ACK":
                row["result"] = "ACKED"
                self.counts["acked"] += 1
            elif response.get("type") == "ERROR":
                row["result"] = "FAILED"
                row["error"] = response.get("error") or response.get("message")
                self.counts["failed"] += 1
            else:
                row["result"] = str(response.get("type") or "RESPONSE")
            self._pending.pop(row["request_id"], None)
        # The last response is also the freshest firmware state, even for an
        # unsolicited STATUS or a duplicate MATCHED/RESPONSE pair.
        for key, attr in (
            ("state", "device_state"),
            ("output_state", "output_state"),
            ("fault_reason", "fault_reason"),
            ("boot_id", "boot_id"),
        ):
            value = response.get(key)
            if isinstance(value, str):
                setattr(self, attr, value)
        version = response.get("firmware_version")
        if isinstance(version, str) and version:
            self.firmware_version = version
        if response.get("bench_active") is False:
            self.session_active = False
        elif response.get("bench_active") is True:
            self.session_active = True
        self.last_status = response
        self.state = self._derived_state()
        self._refresh_target()
        if row is not None and matched and not row["_emitted"]:
            self._emit_outcome(row)

    def _on_ignored(self, record: dict[str, Any], ts_utc, ts_ns) -> None:
        reason = str(record.get("reason") or "unknown")
        nul = record.get("nul_count")
        nul_bytes = int(nul) if type(nul) is int else 0
        self.counts["nul_bytes"] += nul_bytes
        if reason not in COMM_ERROR_REASONS:
            return
        self.counts["corrupt_responses"] += 1
        entry = {
            "utc": ts_utc,
            "reason": reason,
            "nul_count": nul_bytes,
            "length": record.get("length"),
        }
        self._comm_errors.append(entry)
        for row in list(self._pending.values()):
            if row["ack"] is None:
                row["result"] = "CORRUPT_RESPONSE"
                row["error"] = reason
                row["nul_count"] = nul_bytes

    def _on_communication_error(self, record: dict[str, Any], ts_utc, ts_ns) -> None:
        error = str(record.get("error") or "communication error")
        self.last_error = error
        self._comm_errors.append({"utc": ts_utc, "reason": "COMMUNICATION_ERROR", "error": error, "nul_count": 0})
        if "timeout" in error:
            self.counts["timeouts"] += 1
        for row in list(self._pending.values()):
            if row["ack"] is None:
                row["result"] = "TIMEOUT" if "timeout" in error else "FAILED"
                row["error"] = error
                if not row["_emitted"]:
                    self._emit_outcome(row)
        self._pending.clear()
        self.session_active = False
        self.state = "FAULT" if self.device_state == "FAULT" else self._derived_state()
        self._refresh_target()

    def _on_bench_action(self, record: dict[str, Any]) -> None:
        ack = record.get("ack")
        if not isinstance(ack, dict):
            return
        row = self._find_row(ack.get("request_id"))
        if row is not None and row["ack"] is None and row["result"] == "SENT":
            # Defensive: a BENCH_ACTION implies the ACK was accepted.
            row["ack"] = True
            row["ack_type"] = ack.get("type")
            row["ack_utc"] = record.get("timestamp_utc")
            row["ack_ns"] = record.get("monotonic_ns")
            row["state"] = ack.get("state")
            row["output_state"] = ack.get("output_state")
            row["result"] = "ACKED"
            self.counts["acked"] += 1
            self._pending.pop(row["request_id"], None)
            self._emit_outcome(row)

    def _expire_pending(self, *, force: bool = False) -> None:
        now_ns = self.clock() * 1e9
        for row in list(self._pending.values()):
            sent_ns = row.get("sent_ns")
            if type(sent_ns) is not int:
                continue
            age_s = max(0.0, (now_ns - sent_ns) / 1e9)
            if force or age_s > self.timeout_s:
                row["result"] = "TIMEOUT"
                row["error"] = "no matched response before host timeout"
                self.counts["timeouts"] += 1
                self._pending.pop(row["request_id"], None)
                if not row["_emitted"]:
                    self._emit_outcome(row)

    def _emit_outcome(self, row: dict[str, Any]) -> None:
        row["_emitted"] = True
        command = row["command"]
        if command not in PWM_COMMANDS + STOP_COMMANDS + ("BEGIN_BENCH",):
            return
        stage = "DEVICE_ACK" if row["result"] == "ACKED" else "FAILED"
        detail = {
            "ACKED": "pwm_console ACK; target is not measured position",
            "TIMEOUT": "no matched ACK before the console timeout; output not confirmed",
            "CORRUPT_RESPONSE": "response corrupted (NUL/parse); ACK not confirmed",
        }.get(row["result"], row.get("error") or "command outcome unknown")
        action = {
            "BENCH_HOLD": "SET_PWM",
            "BENCH_PULSE": "SET_PWM",
            "STOP": "STOP",
            "DISARM": "DISARM",
            "BEGIN_BENCH": "BEGIN_SESSION",
        }[command]
        event = ControlEvent(
            action=action,
            stage=stage,
            source=self.source,
            mode="MANUAL" if action == "SET_PWM" else "STANDBY",
            command_id=row["request_id"],
            firmware_command=command,
            timestamp_ns=row.get("ack_ns") or row.get("sent_ns") or 0,
            timestamp_utc=row.get("ack_utc") or row.get("sent_utc") or _utc_now(),
            commanded_pwm_us=row.get("pulse_us") if action == "SET_PWM" else None,
            serial_write_ok=True,
            device_ack=row["result"] == "ACKED",
            detail=f"pwm_console log · {detail}",
            response=self.last_response if row["result"] == "ACKED" else None,
            firmware_state=row.get("state"),
        )
        self._events.append(event)
        if command not in PWM_COMMANDS:
            return
        self._pwm_events.append(
            {
                "seq": row.get("seq"),
                "command": command,
                "pulse_us": row.get("pulse_us"),
                "sent_utc": row.get("sent_utc"),
                "sent_ns": row.get("sent_ns"),
                "ack_utc": row.get("ack_utc"),
                "ack_ns": row.get("ack_ns"),
                "ack": row["result"] == "ACKED",
                "result": row["result"],
                "state": row.get("state"),
                "output_state": row.get("output_state"),
            }
        )

    # -- derived state -----------------------------------------------------

    def _derived_state(self) -> str:
        if self.closed:
            return "OFFLINE"
        if self.device_state:
            return str(self.device_state)
        return "LOG_WAITING"

    def _refresh_target(self) -> None:
        """Compute the freshest commanded target without inventing output."""
        last = None
        for row in reversed(self._commands):
            if row["command"] in PWM_COMMANDS + STOP_COMMANDS:
                last = row
                break
        self.current_target_us = None
        self.current_command_id = None
        self.last_pwm_us = None
        self.target_status = "NO_PWM"
        self.target_age_s = None
        if last is None:
            return
        self.current_command_id = last.get("request_id")
        if last["command"] in STOP_COMMANDS:
            self.target_status = "OUTPUT_OFF" if last["ack"] else "STOP_UNCONFIRMED"
            return
        self.current_target_us = last.get("pulse_us")
        age_s = None
        if type(last.get("sent_ns")) is int:
            age_s = max(0.0, (self.clock() * 1e9 - last["sent_ns"]) / 1e9)
        self.target_age_s = None if age_s is None else round(age_s, 3)
        if last["result"] == "ACKED" and last.get("ack_type") == "ACK":
            if last.get("state") == "FAULT":
                self.target_status = "FAILED"
                return
            if last.get("output_state") in (None, "PWM_COMMANDED_UNMEASURED", "SIMULATED_UNMEASURED"):
                self.target_status = "ACKED"
            else:
                self.target_status = "ACKED_UNKNOWN_OUTPUT"
            self.last_pwm_us = self.current_target_us
            if age_s is not None and self.closed:
                self.target_status = "OFFLINE"
                self.last_pwm_us = None
            elif age_s is not None and age_s > self.stale_after_s:
                # The record is ACKed but the stream is no longer proving it.
                self.target_status = "ACK_STALE"
                self.last_pwm_us = None
            return
        if last["result"] in ("TIMEOUT", "CORRUPT_RESPONSE"):
            self.target_status = "TIMEOUT" if last["result"] == "TIMEOUT" else "UNCONFIRMED"
        elif last["result"] == "FAILED":
            self.target_status = "FAILED"
        else:
            self.target_status = "SENT_UNACKED"

    def pwm_context_at(self, host_ns: int) -> dict[str, Any] | None:
        """Return the PWM target live at ``host_ns`` (recorded context only).

        Frames and PWM commands share the host monotonic clock, so a
        back-filled frame is attributed to the command that preceded it.
        """
        with self._lock:
            best = None
            for row in self._commands:
                sent = row.get("sent_ns")
                if type(sent) is not int or sent > host_ns:
                    continue
                if row["command"] in STOP_COMMANDS:
                    best = None
                elif row["command"] in PWM_COMMANDS:
                    best = row
            if best is None:
                return None
            acked = best["result"] == "ACKED"
            return {
                "command_id": best["request_id"],
                "target_pwm_us": best.get("pulse_us"),
                "acknowledged": acked,
                "stage": "DEVICE_ACK" if acked else "SENT_UNACKED",
                "source": "PWM_CONSOLE_LOG",
            }

    def refresh(self) -> None:
        """Recompute time-dependent state for display (no file read)."""
        with self._lock:
            self._refresh_target()

    # -- introspection -----------------------------------------------------

    def _last_target_row(self) -> dict[str, Any]:
        for row in reversed(self._commands):
            if row["command"] in PWM_COMMANDS + STOP_COMMANDS:
                return row
        return {}

    def _data_stale(self) -> bool:
        age = self.tail.file_age_s()
        return bool(age is not None and age > self.stale_after_s and not self.closed)

    def monitor_snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_target()
            recent = []
            for row in list(self._commands)[-30:]:
                recent.append(
                    {
                        "seq": row.get("seq"),
                        "command": row.get("command"),
                        "pulse_us": row.get("pulse_us"),
                        "sent_utc": row.get("sent_utc"),
                        "ack_utc": row.get("ack_utc"),
                        "ack": row["result"] == "ACKED",
                        "result": row["result"],
                        "ack_type": row.get("ack_type"),
                        "state": row.get("state"),
                        "output_state": row.get("output_state"),
                        "error": row.get("error"),
                        "nul_count": row.get("nul_count", 0),
                    }
                )
            return {
                "mode": "LOG_FOLLOW",
                "read_only": True,
                "pwm_log": str(self.log_path),
                "pwm_log_age_s": self.tail.file_age_s(),
                "pwm_log_closed": self.closed,
                "session_restarts": self.session_restarts,
                "closed_at_utc": self.closed_at_utc,
                "final_output_state": self.final_output_state,
                "session_active": self.session_active,
                "session_mode": self.session_mode,
                "device_state": self.device_state,
                "output_state": self.output_state,
                "fault_reason": self.fault_reason,
                "firmware_version": self.firmware_version,
                "boot_id": self.boot_id,
                "data_stale": self._data_stale(),
                "last_event_utc": self.last_event_utc,
                "last_response_utc": self.last_response_utc,
                "last_response": self.last_response,
                "current_target_us": self.current_target_us,
                "current_target": (
                    {
                        "command_id": self.current_command_id,
                        "pulse_us": self.current_target_us,
                        "status": self.target_status,
                        "sent_utc": self._last_target_row().get("sent_utc"),
                        "ack_utc": self._last_target_row().get("ack_utc"),
                    }
                    if self.current_target_us is not None
                    else None
                ),
                "target_status": self.target_status,
                "target_age_s": self.target_age_s,
                "counts": dict(self.counts),
                "comm_errors": list(self._comm_errors)[-8:],
                "commands": recent,
                "pwm_events": list(self._pwm_events)[-60:],
                "tail": self.tail.describe(),
                "sync_note": (
                    "时间对齐：console 与 FSR 采集在同一主机写入 host UTC + monotonic_ns；"
                    "Dashboard 只读这些时间戳，不重新打时间。"
                ),
            }

    def status(self) -> DeviceStatus:
        with self._lock:
            self._refresh_target()
            stale = self._data_stale()
            state = self._derived_state()
            if stale and state not in ("FAULT", "OFFLINE"):
                state = "STALE"
            detail = {
                "monitor": "LOG_FOLLOW",
                "read_only": True,
                "log_path": str(self.log_path),
                "log_state": "CLOSED" if self.closed else ("STALE" if stale else "FOLLOWING"),
                "log_age_s": self.tail.file_age_s(),
                "session_active": self.session_active,
                "session_mode": self.session_mode,
                "output_state": self.output_state,
                "firmware_state": self.device_state,
                "fault_reason": self.fault_reason,
                "last_pwm_us": self.last_pwm_us,
                "current_target_us": self.current_target_us,
                "current_target": (
                    {
                        "command_id": self.current_command_id,
                        "pulse_us": self.current_target_us,
                        "status": self.target_status,
                        "sent_utc": self._last_target_row().get("sent_utc"),
                        "ack_utc": self._last_target_row().get("ack_utc"),
                    }
                    if self.current_target_us is not None
                    else None
                ),
                "target_status": self.target_status,
                "target_age_s": self.target_age_s,
                "pwm_limits": self.pwm_limits,
                "counts": dict(self.counts),
                "comm_errors": list(self._comm_errors)[-8:],
                "last_response": self.last_response,
                "last_response_utc": self.last_response_utc,
                "actual_pwm_us": None,
                "actual_position_known": False,
                "config_path": self.config_path,
                "tail": self.tail.describe(),
            }
            return DeviceStatus(
                device_id="s3-controller (pwm_console log)",
                kind="GRIPPER",
                source=self.source,
                connected=self.connected and not self.closed,
                state=state,
                protocol_version=1,
                firmware_version=self.firmware_version,
                boot_id=self.boot_id,
                last_error=self.last_error,
                detail=detail,
            )


class LogFollowSensorTransport:
    """Line transport over the FSR capture JSONL.

    Each record may be the capture wrapper
    ``{host_time_utc, host_monotonic_ns, direction, raw, message}`` or a bare
    wire message.  The wrapper timestamp is handed to the adapter so recorded
    frames keep their real host time instead of the dashboard's read time.
    """

    def __init__(self, path: Path | str, *, clock=time.monotonic):
        self.path = Path(path)
        self.tail = JsonlTail(path, max_line_bytes=65536, clock=clock)
        self.connected = False
        self._pending: deque[tuple[bytes, int | None, str | None]] = deque()
        self._bootstrap: tuple[bytes, int | None, str | None] | None = None
        self._timestamp: tuple[int | None, str | None] = (None, None)
        self.bad_lines = 0
        self.frames_without_host_time = 0
        self.last_line_utc: str | None = None
        self.last_line_ns: int | None = None
        self.port = None
        self.baudrate = None

    def connect(self) -> None:
        if not self.path.is_file():
            raise SensorOffline(f"FSR log not found: {self.path}")
        # A late attach may start in the middle of a large file (JsonlTail keeps
        # only a recent window).  The channel config lives in the first HELLO, so
        # read it from the file head and hand it to the parser before any SAMPLE.
        self._bootstrap = self._read_hello_prefix()
        self.connected = True

    def _read_hello_prefix(self, max_bytes: int = 1_000_000) -> tuple[bytes, int | None, str | None] | None:
        try:
            with self.path.open("rb") as handle:
                data = handle.read(max_bytes)
        except OSError:
            return None
        for raw in data.split(b"\n"):
            if not raw.strip():
                continue
            try:
                record = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            message = record.get("message") if isinstance(record.get("message"), dict) else record
            if not isinstance(message, dict) or message.get("type") != "HELLO":
                continue
            host_ns = record.get("host_monotonic_ns")
            host_utc = record.get("host_time_utc")
            payload = (json.dumps(message, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
            return (
                payload,
                host_ns if type(host_ns) is int else None,
                host_utc if isinstance(host_utc, str) else None,
            )
        return None

    def close(self) -> None:
        self.connected = False
        self.tail.close()

    @property
    def at_end(self) -> bool:
        # A live tail is never "at end"; staleness is reported by the adapter.
        return False

    def has_pending(self) -> bool:
        return bool(self._pending)

    def last_line_timestamp(self) -> tuple[int | None, str | None]:
        return self._timestamp

    def readline(self, timeout_s: float) -> bytes | None:
        if not self.connected:
            raise SensorOffline("FSR log is not connected")
        deadline = time.monotonic() + max(0.0, timeout_s)
        while True:
            if self._pending:
                line, host_ns, host_utc = self._pending.popleft()
                self._timestamp = (host_ns, host_utc)
                self.last_line_ns = host_ns
                self.last_line_utc = host_utc
                return line
            for text in self.tail.read_new():
                item = self._parse(text)
                if item is not None:
                    self._pending.append(item)
            if self._pending:
                continue
            if time.monotonic() >= deadline:
                return None
            time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))

    def _parse(self, text: str) -> tuple[bytes, int | None, str | None] | None:
        raw = text.strip()
        if not raw:
            return None
        try:
            record = json.loads(raw)
        except ValueError:
            self.bad_lines += 1
            return None
        if not isinstance(record, dict):
            self.bad_lines += 1
            return None
        host_ns: int | None = None
        host_utc: str | None = None
        message: dict[str, Any] | None = None
        if isinstance(record.get("message"), dict):
            if record.get("direction") not in (None, "RX"):
                return None
            message = record["message"]
            if type(record.get("host_monotonic_ns")) is int:
                host_ns = record["host_monotonic_ns"]
            if isinstance(record.get("host_time_utc"), str):
                host_utc = record["host_time_utc"]
        elif record.get("type") in SENSOR_TYPES:
            message = record
        elif record.get("record_type") == "SENSOR_FRAME":
            message = self._sample_from_trial_row(record)
            if type(record.get("host_received_ns")) is int:
                host_ns = record["host_received_ns"]
            if isinstance(record.get("host_received_utc"), str):
                host_utc = record["host_received_utc"]
        if message is None or message.get("type") not in SENSOR_TYPES:
            return None
        if host_ns is None or host_utc is None:
            self.frames_without_host_time += 1
            host_ns = time.monotonic_ns()
            host_utc = _utc_now()
        payload = (json.dumps(message, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        return payload, host_ns, host_utc

    @staticmethod
    def _sample_from_trial_row(record: dict[str, Any]) -> dict[str, Any] | None:
        """Rebuild a SAMPLE for a Trial ``frames.jsonl`` row (no HELLO here)."""

        raw = record.get("raw")
        if isinstance(raw, dict) and raw.get("type") == "SAMPLE":
            return raw
        if not isinstance(record.get("channels"), list):
            return None
        return {
            "protocol_version": 1,
            "type": "SAMPLE",
            "device_id": record.get("device_id"),
            "boot_id": record.get("boot_id"),
            "frame_seq": record.get("frame_seq"),
            "mcu_time_us": record.get("mcu_time_us"),
            "channel_ids": record.get("channel_ids"),
            "channels": record.get("channels"),
            "valid_mask": record.get("valid_mask"),
        }

    def describe(self) -> dict[str, Any]:
        return {
            **self.tail.describe(),
            "bad_lines": self.bad_lines,
            "frames_without_host_time": self.frames_without_host_time,
            "last_line_utc": self.last_line_utc,
        }


class LogFollowSensorAdapter(SensorAdapter):
    """Strict V2 sensor adapter that reads the FSR capture log."""

    def __init__(
        self,
        path: Path | str,
        *,
        stale_after_s: float = DEFAULT_FSR_STALE_S,
        clock_ns=time.monotonic_ns,
    ):
        self.log_transport = LogFollowSensorTransport(path, clock=time.monotonic)
        super().__init__(
            self.log_transport,
            None,
            source=DataSource.LIVE,
            device_id="sensor-fsr-log",
            clock_ns=clock_ns,
            stale_after_s=stale_after_s,
            max_line_bytes=16384,
            strict_v2=True,
            request_hello_on_connect=False,
        )

    def connect(self) -> DeviceStatus:
        status = super().connect()
        # Feed the HELLO found at the file head without consuming a SAMPLE, so
        # the first page render has the channel map and no frame is lost.
        bootstrap = getattr(self.log_transport, "_bootstrap", None)
        if bootstrap is not None:
            self.log_transport._bootstrap = None
            try:
                self._handle_line(bootstrap[0])
            except Exception:
                pass
        return self.status()

    def status(self) -> DeviceStatus:
        status = super().status()
        stale_age = None
        if self.tracker.last_host_received_ns is not None:
            stale_age = max(0.0, (self.clock_ns() - self.tracker.last_host_received_ns) / 1e9)
        status.detail["monitor"] = "LOG_FOLLOW"
        status.detail["log"] = self.log_transport.describe()
        status.detail["log_age_s"] = stale_age
        status.detail["records_without_host_time"] = (
            self.log_transport.frames_without_host_time
        )
        return status


def build_log_follow_core_adapters(
    *,
    pwm_log: Path | str | None,
    fsr_log: Path | str | None,
    config_path: Path | str | None = None,
):
    """Return ``(gripper, sensor)`` for the Dashboard, each optional."""

    gripper = LogFollowGripper(pwm_log, config_path=config_path) if pwm_log else None
    sensor = LogFollowSensorAdapter(fsr_log) if fsr_log else None
    return gripper, sensor
