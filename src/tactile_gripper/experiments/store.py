"""Trial storage: metadata JSON, events/frames JSONL, CSV and crash recovery.

Recordings are written below exactly one source-specific directory:
``data/real/trials`` for LIVE and ``data/simulated/trials`` for SIMULATION.
REPLAY is read-only and cannot create a recording.

S2-B additions are additive:
- ``schema_version`` (new trials are v3; v1/v2 files without it still load)
- ``git_commit`` / ``write_error`` in metadata
- recording lock file with PID + heartbeat for interrupted-trial recovery
- integrity counters (invalid channels, dropped/duplicate frames, restarts)
"""

from __future__ import annotations

import csv
import json
import os
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..constants import TRIAL_LOCK_FILENAME, TRIAL_LOCK_STALE_S, TRIAL_SCHEMA_VERSION
from ..errors import TrialWriteError
from ..models import (
    ControlEvent,
    TactileFrame,
    TrialEvent,
    TrialMetadata,
    utc_now_iso,
)
from ..paths import PROJECT_ROOT
from ..sources import DataSource, trial_parent

# Trial statuses used by the recorder/store.
STATUS_CREATED = "CREATED"
STATUS_RECORDING = "RECORDING"
STATUS_COMPLETED = "COMPLETED"
STATUS_ABORTED = "ABORTED"
STATUS_INTERRUPTED = "INTERRUPTED"
STATUS_ERROR = "ERROR"


@dataclass
class StoredTrial:
    metadata: TrialMetadata
    directory: Path

    @property
    def source(self) -> DataSource:
        return self.metadata.source


@dataclass
class TrialRecord:
    metadata: TrialMetadata
    directory: Path
    events: list[dict[str, Any]] = field(default_factory=list)
    frames: list[dict[str, Any]] = field(default_factory=list)
    read_errors: list[str] = field(default_factory=list)
    truncated_tail: bool = False


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_jsonl_meta(path: Path) -> tuple[list[dict[str, Any]], list[str], bool]:
    """Read JSONL, tolerating an incomplete final line written by a crash.

    A final line without a trailing newline is reported as ``truncated_tail``
    and never treated as a valid event/frame.  Earlier complete lines are kept.
    """
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.is_file():
        return rows, errors, False
    try:
        data = path.read_bytes()
    except OSError as exc:
        return rows, [f"{path.name}: unreadable ({exc})"], False
    truncated = bool(data) and not data.endswith(b"\n")
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    for number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        try:
            line = raw_line.decode("utf-8")
            value = json.loads(line)
        except (UnicodeError, ValueError) as exc:
            if truncated and number == len(lines):
                errors.append(f"{path.name}:{number}: incomplete final line ignored")
            else:
                errors.append(f"{path.name}:{number}: invalid JSON ({exc})")
            continue
        if not isinstance(value, dict):
            errors.append(f"{path.name}:{number}: root is not an object")
            continue
        rows.append(value)
    return rows, errors, truncated


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows, errors, _ = _read_jsonl_meta(path)
    return rows, errors


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_recording_lock(directory: Path) -> dict[str, Any] | None:
    path = directory / TRIAL_LOCK_FILENAME
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _lock_is_active(lock: dict[str, Any] | None, *, stale_after_s: float = TRIAL_LOCK_STALE_S) -> bool:
    if not lock:
        return False
    if lock.get("host") != socket.gethostname():
        return False
    try:
        pid = int(lock.get("pid"))
    except (TypeError, ValueError):
        return False
    if not _pid_alive(pid):
        return False
    try:
        heartbeat_ns = int(lock.get("heartbeat_ns"))
    except (TypeError, ValueError):
        return False
    return (time.monotonic_ns() - heartbeat_ns) <= int(stale_after_s * 1_000_000_000)


def trial_integrity(record: TrialRecord) -> dict[str, Any]:
    """Compute integrity counters from the saved frames/events."""
    last_boot: str | None = None
    last_seq: int | None = None
    dropped = 0
    duplicate = 0
    restarts = 0
    invalid_channel_samples = 0
    frames_with_invalid = 0
    boot_switch = 0
    for frame in record.frames:
        boot = frame.get("boot_id")
        seq = frame.get("frame_seq")
        if last_boot is None:
            pass
        elif boot != last_boot:
            restarts += 1
            last_seq = None
        elif isinstance(seq, int) and isinstance(last_seq, int):
            if seq == last_seq:
                duplicate += 1
            elif seq < last_seq:
                restarts += 1
                last_seq = None
            elif seq > last_seq + 1:
                dropped += seq - last_seq - 1
        mask = frame.get("valid_mask") or []
        invalid = sum(1 for flag in mask if not flag)
        if invalid:
            frames_with_invalid += 1
            invalid_channel_samples += invalid
        if boot != last_boot and last_boot is not None:
            boot_switch += 1
        last_boot = boot if isinstance(boot, str) else last_boot
        if isinstance(seq, int):
            last_seq = seq
    control_events = [item for item in record.events if item.get("record_type") == "CONTROL_EVENT"]
    failed_control = [
        item
        for item in control_events
        if item.get("stage") in ("FAILED", "REJECTED", "UNSUPPORTED", "TIMEOUT")
    ]
    ack_events = [item for item in control_events if item.get("device_ack")]
    anomaly_events = [
        item
        for item in record.events
        if (item.get("record_type") == "TRIAL_EVENT" and item.get("event_type") in ("ANOMALY", "SENSOR_ERROR", "FRAME_ANOMALY", "FAULT", "TRIAL_INTERRUPTED", "TRIAL_WRITE_ERROR"))
        or (item.get("record_type") == "CONTROL_EVENT" and item.get("stage") in ("INVALID_DATA", "OFFLINE", "DEVICE_ERROR"))
    ]
    return {
        "schema_version": record.metadata.schema_version,
        "trial_id": record.metadata.trial_id,
        "status": record.metadata.status,
        "source": record.metadata.source.value,
        "frames": len(record.frames),
        "events": len(record.events),
        "control_events": len(control_events),
        "ack_events": len(ack_events),
        "failed_control_events": len(failed_control),
        "anomaly_events": len(anomaly_events),
        "invalid_channel_samples": invalid_channel_samples,
        "frames_with_invalid_channels": frames_with_invalid,
        "dropped_frames": dropped,
        "duplicate_frames": duplicate,
        "restarts": restarts,
        "boot_switches": boot_switch,
        "read_errors": list(record.read_errors),
        "write_error": record.metadata.write_error,
        "truncated_tail": record.truncated_tail,
        "complete": record.metadata.status in (STATUS_COMPLETED, STATUS_ABORTED),
        "interrupted": record.metadata.status == STATUS_INTERRUPTED,
        "error": record.metadata.status == STATUS_ERROR,
        "recording_lock_present": (record.directory / TRIAL_LOCK_FILENAME).is_file(),
    }


class TrialRecorder:
    """Write one trial.  A recorder never changes its source after creation."""

    def __init__(self, metadata: TrialMetadata, directory: Path):
        self.metadata = metadata
        self.directory = Path(directory)
        self.events_path = self.directory / "events.jsonl"
        self.frames_path = self.directory / "frames.jsonl"
        self.metadata_path = self.directory / "metadata.json"
        self.csv_path = self.directory / "frames.csv"
        self.lock_path = self.directory / TRIAL_LOCK_FILENAME
        self._lock = threading.RLock()
        self._event_file = None
        self._frame_file = None
        self.frame_count = int(metadata.counts.get("frames", 0))
        self.event_count = int(metadata.counts.get("events", 0))
        self.invalid_channel_samples = int(metadata.counts.get("invalid_channel_samples", 0))
        self.frames_with_invalid = int(metadata.counts.get("frames_with_invalid_channels", 0))
        self.dropped_frames = int(metadata.counts.get("dropped_frames", 0))
        self.duplicate_frames = int(metadata.counts.get("duplicate_frames", 0))
        self.restarts = int(metadata.counts.get("restarts", 0))
        self._last_boot: str | None = None
        self._last_seq: int | None = None
        self._last_lock_touch = 0.0
        self.write_error: str | None = metadata.write_error

    @property
    def recording(self) -> bool:
        return self.metadata.status == STATUS_RECORDING

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> TrialMetadata:
        with self._lock:
            if self.metadata.status != STATUS_CREATED:
                raise RuntimeError(f"cannot start trial in status {self.metadata.status}")
            if self.lock_path.exists():
                lock = _read_recording_lock(self.directory)
                if _lock_is_active(lock):
                    raise TrialWriteError(
                        f"trial is already being recorded by pid {lock.get('pid')} on {lock.get('host')}"
                    )
                try:
                    self.lock_path.unlink(missing_ok=True)
                except OSError:
                    pass
            self.metadata.schema_version = TRIAL_SCHEMA_VERSION
            self.metadata.status = STATUS_RECORDING
            self.metadata.started_at = utc_now_iso()
            self.metadata.write_error = None
            self.write_error = None
            try:
                self._write_lock(force=True)
                self._write_metadata()
                self._append_event(
                    TrialEvent("TRIAL_START", "recording started", {"mode": self.metadata.mode})
                )
            except (OSError, TrialWriteError) as exc:
                self._fail_write(exc)
                raise TrialWriteError(f"could not start recording: {exc}") from exc
            return self.metadata

    def stop(
        self,
        reason: str = "manual",
        *,
        aborted: bool = False,
        interrupted: bool = False,
    ) -> TrialMetadata:
        with self._lock:
            if self.metadata.status != STATUS_RECORDING:
                raise RuntimeError(f"trial is not recording (status {self.metadata.status})")
            if aborted and interrupted:
                raise ValueError("trial cannot be both aborted and interrupted")
            if self.write_error:
                raise TrialWriteError(f"trial has a write error: {self.write_error}")
            try:
                event_type = "TRIAL_INTERRUPTED" if interrupted else "TRIAL_STOP"
                self._append_event(
                    TrialEvent(
                        event_type,
                        reason,
                        {"aborted": aborted, "interrupted": interrupted},
                    )
                )
                self.metadata.status = (
                    STATUS_INTERRUPTED
                    if interrupted
                    else STATUS_ABORTED
                    if aborted
                    else STATUS_COMPLETED
                )
                self.metadata.ended_at = utc_now_iso()
                self._close_files()
                self._write_metadata()
                self._remove_lock()
                self.export_csv()
            except (OSError, TrialWriteError) as exc:
                self._fail_write(exc)
                raise TrialWriteError(f"could not stop recording cleanly: {exc}") from exc
            return self.metadata

    def heartbeat(self) -> None:
        with self._lock:
            if not self.recording:
                return
            try:
                self._write_lock(force=False)
            except OSError as exc:
                self._fail_write(exc)
                raise TrialWriteError(f"recording heartbeat failed: {exc}") from exc

    def _close_files(self) -> None:
        for handle in (self._event_file, self._frame_file):
            if handle is not None:
                try:
                    handle.flush()
                    handle.close()
                except OSError:
                    pass
        self._event_file = None
        self._frame_file = None

    def close(self) -> None:
        with self._lock:
            self._close_files()

    # -- recording ---------------------------------------------------------

    def record_control(self, event: ControlEvent) -> None:
        with self._lock:
            if not self.recording:
                return
            if event.source is not self.metadata.source:
                raise ValueError(
                    f"control source {event.source.value} does not match trial source {self.metadata.source.value}"
                )
            self._append_event(
                {
                    "record_type": "CONTROL_EVENT",
                    "trial_id": self.metadata.trial_id,
                    **event.to_dict(),
                }
            )
            self._touch_lock()

    def record_frame(
        self,
        frame: TactileFrame,
        *,
        sensor_identity: dict | None = None,
        assessment: dict | None = None,
        sensor_profile: str | None = None,
        control_context: dict | None = None,
    ) -> None:
        with self._lock:
            if not self.recording:
                return
            if frame.source is not self.metadata.source:
                raise ValueError(
                    f"frame source {frame.source.value} does not match trial source {self.metadata.source.value}"
                )
            if self._frame_file is None:
                self._open_frame_file()
            payload = {
                "record_type": "SENSOR_FRAME",
                "trial_id": self.metadata.trial_id,
                "schema_version": TRIAL_SCHEMA_VERSION,
                "sensor_identity": sensor_identity,
                "sensor_profile": sensor_profile,
                "contact_assessment": assessment,
                "pwm_command_id": (control_context or {}).get("command_id"),
                "pwm_target_us": (control_context or {}).get("target_pwm_us"),
                "pwm_ack": (control_context or {}).get("acknowledged"),
                **frame.to_dict(include_wire=True),
            }
            try:
                self._frame_file.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
                self._frame_file.flush()
            except OSError as exc:
                self._fail_write(exc)
                raise TrialWriteError(f"frame write failed: {exc}") from exc
            self.frame_count += 1
            invalid = frame.channel_count - frame.valid_channel_count
            if invalid:
                self.frames_with_invalid += 1
                self.invalid_channel_samples += invalid
            if self._last_boot is None:
                pass
            elif frame.boot_id != self._last_boot:
                self.restarts += 1
                self._last_seq = None
            elif self._last_seq is not None:
                if frame.frame_seq == self._last_seq:
                    self.duplicate_frames += 1
                elif frame.frame_seq < self._last_seq:
                    self.restarts += 1
                    self._last_seq = None
                elif frame.frame_seq > self._last_seq + 1:
                    self.dropped_frames += frame.frame_seq - self._last_seq - 1
            self._last_boot = frame.boot_id
            self._last_seq = frame.frame_seq
            self._update_counts()
            self._touch_lock()

    def set_video_path(self, path: str | Path | None) -> TrialMetadata:
        with self._lock:
            self.metadata.video_path = str(path) if path else None
            self._write_metadata()
            self._touch_lock()
            return self.metadata

    def add_event(self, event_type: str, message: str, data: dict | None = None) -> TrialEvent:
        event = TrialEvent(event_type, message, data or {})
        with self._lock:
            self._append_event(event)
            self._touch_lock()
        return event

    # -- low-level writers -------------------------------------------------

    def _open_event_file(self) -> None:
        if self._event_file is None:
            self._event_file = open(self.events_path, "a", encoding="utf-8")

    def _open_frame_file(self) -> None:
        if self._frame_file is None:
            self._frame_file = open(self.frames_path, "a", encoding="utf-8")

    def _append_event(self, event: TrialEvent | dict[str, Any]) -> None:
        try:
            self._open_event_file()
            payload = event if isinstance(event, dict) else event.to_dict()
            payload.setdefault("record_type", "TRIAL_EVENT")
            payload.setdefault("trial_id", self.metadata.trial_id)
            self._event_file.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
            self._event_file.flush()
        except OSError as exc:
            self._fail_write(exc)
            raise TrialWriteError(f"event write failed: {exc}") from exc
        self.event_count += 1
        self._update_counts()

    def _update_counts(self) -> None:
        self.metadata.counts = {
            "frames": self.frame_count,
            "events": self.event_count,
            "invalid_channel_samples": self.invalid_channel_samples,
            "frames_with_invalid_channels": self.frames_with_invalid,
            "dropped_frames": self.dropped_frames,
            "duplicate_frames": self.duplicate_frames,
            "restarts": self.restarts,
        }

    def _write_metadata(self) -> None:
        self.metadata.files = {
            "metadata": "metadata.json",
            "events": "events.jsonl",
            "frames": "frames.jsonl",
            "csv": "frames.csv",
            "recording_lock": TRIAL_LOCK_FILENAME,
        }
        self.metadata.schema_version = TRIAL_SCHEMA_VERSION
        self.metadata.write_error = self.write_error
        self._update_counts()
        _atomic_json(self.metadata_path, self.metadata.to_dict())

    def _touch_lock(self) -> None:
        if not self.recording:
            return
        try:
            self._write_lock(force=False)
        except OSError as exc:
            self._fail_write(exc)
            raise TrialWriteError(f"recording lock write failed: {exc}") from exc

    def _write_lock(self, *, force: bool) -> None:
        now = time.monotonic()
        if not force and now - self._last_lock_touch < 1.0:
            return
        lock = {
            "trial_id": self.metadata.trial_id,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "started_at": self.metadata.started_at,
            "heartbeat_utc": utc_now_iso(),
            "heartbeat_ns": time.monotonic_ns(),
            "source": self.metadata.source.value,
        }
        _atomic_json(self.lock_path, lock)
        self._last_lock_touch = now

    def _remove_lock(self) -> None:
        try:
            self.lock_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _fail_write(self, exc: BaseException) -> None:
        self.write_error = str(exc)
        self.metadata.write_error = self.write_error
        self.metadata.status = STATUS_ERROR
        self._close_files()
        try:
            self._write_metadata()
        except OSError:
            pass
        self._remove_lock()

    # -- export ------------------------------------------------------------

    def export_csv(self) -> Path:
        frames, _ = _read_jsonl(self.frames_path)
        channel_ids: list[int] = []
        for row in frames:
            ids = row.get("channel_ids")
            if ids is None:
                ids = list(range(int(row.get("channel_count", 0))))
            for channel_id in ids:
                if channel_id not in channel_ids:
                    channel_ids.append(int(channel_id))
        base = [
            "frame_seq",
            "boot_id",
            "mcu_time_us",
            "host_received_ns",
            "host_received_utc",
            "source",
            "contact_score",
            "channel_count",
            "valid_count",
            "device_id",
            "sensor_profile",
            "contact_state",
            "contact_quality",
            "pwm_command_id",
            "pwm_target_us",
            "pwm_ack",
        ]
        header = base + [item for channel_id in channel_ids for item in (f"ch_{channel_id}", f"valid_{channel_id}")]
        tmp = self.csv_path.with_suffix(".csv.tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for row in frames:
                channels = row.get("channels") or []
                mask = row.get("valid_mask") or []
                ids = row.get("channel_ids")
                if ids is None:
                    ids = list(range(len(channels)))
                by_id = {
                    int(channel_id): (channels[index], mask[index])
                    for index, channel_id in enumerate(ids)
                    if index < len(channels) and index < len(mask)
                }
                values = [
                    row.get("frame_seq"),
                    row.get("boot_id"),
                    row.get("mcu_time_us"),
                    row.get("host_received_ns"),
                    row.get("host_received_utc"),
                    row.get("source"),
                    row.get("contact_score"),
                    row.get("channel_count"),
                    sum(1 for flag in mask if flag),
                    row.get("device_id", ""),
                    row.get("sensor_profile") or "",
                    (row.get("contact_assessment") or {}).get("state", ""),
                    (row.get("contact_assessment") or {}).get("quality", ""),
                    row.get("pwm_command_id", ""),
                    row.get("pwm_target_us", ""),
                    row.get("pwm_ack", ""),
                ]
                for channel_id in channel_ids:
                    value, valid = by_id.get(channel_id, (None, False))
                    values.extend(["" if value is None else value, "true" if valid else "false"])
                writer.writerow(values)
        tmp.replace(self.csv_path)
        return self.csv_path


class TrialStore:
    def __init__(self, root: Path | str = PROJECT_ROOT, source: DataSource = DataSource.SIMULATION):
        self.root = Path(root)
        self.source = DataSource(source)

    @property
    def parent(self) -> Path:
        return trial_parent(self.root, self.source)

    def create_trial(
        self,
        name: str,
        *,
        mode: str,
        conditions: dict | None = None,
        parameters: dict | None = None,
        notes: str = "",
        git_commit: str | None = None,
        video_path: str | None = None,
        operator: str | None = None,
        tags: list[str] | None = None,
    ) -> TrialRecorder:
        if self.source is DataSource.REPLAY:
            raise PermissionError("REPLAY is read-only")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("trial name is required")
        parent = self.parent
        parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        for _ in range(20):
            trial_id = f"T-{timestamp}-{uuid.uuid4().hex[:8]}"
            directory = parent / trial_id
            try:
                directory.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError("could not allocate a unique trial id")
        metadata = TrialMetadata(
            trial_id=trial_id,
            name=name.strip(),
            source=self.source,
            mode=mode,
            conditions=dict(conditions or {}),
            parameters=dict(parameters or {}),
            notes=notes,
            schema_version=TRIAL_SCHEMA_VERSION,
            git_commit=git_commit,
            video_path=video_path,
            operator=operator,
            tags=list(tags or []),
            files={
                "metadata": "metadata.json",
                "events": "events.jsonl",
                "frames": "frames.jsonl",
                "csv": "frames.csv",
                "recording_lock": TRIAL_LOCK_FILENAME,
            },
            counts={"frames": 0, "events": 0},
        )
        recorder = TrialRecorder(metadata, directory)
        recorder._write_metadata()
        return recorder

    def _scan_trials(self, *, include_real: bool = True, include_simulated: bool = True) -> list[StoredTrial]:
        result: list[StoredTrial] = []
        sources = []
        if include_real:
            sources.append(DataSource.LIVE)
        if include_simulated:
            sources.append(DataSource.SIMULATION)
        for source in sources:
            parent = trial_parent(self.root, source)
            if not parent.is_dir():
                continue
            for directory in parent.iterdir():
                if not directory.is_dir():
                    continue
                metadata_path = directory / "metadata.json"
                if not metadata_path.is_file():
                    continue
                try:
                    metadata = TrialMetadata.from_dict(json.loads(metadata_path.read_text(encoding="utf-8")))
                except (ValueError, OSError):
                    continue
                result.append(StoredTrial(metadata=metadata, directory=directory))
        result.sort(key=lambda item: item.metadata.created_at, reverse=True)
        return result

    def list_trials(
        self,
        *,
        include_real: bool = True,
        include_simulated: bool = True,
        recover_interrupted: bool = False,
    ) -> list[StoredTrial]:
        if recover_interrupted:
            self.recover_interrupted()
        return self._scan_trials(include_real=include_real, include_simulated=include_simulated)

    def recover_interrupted(self, *, stale_after_s: float = TRIAL_LOCK_STALE_S) -> list[str]:
        """Mark RECORDING trials whose process is gone as INTERRUPTED.

        Data files are kept untouched.  The metadata gains ``status=INTERRUPTED``,
        ``ended_at`` and a ``TRIAL_INTERRUPTED`` event so it can never be mistaken
        for a normally completed trial.
        """
        recovered: list[str] = []
        for stored in self._scan_trials():
            if stored.metadata.status != STATUS_RECORDING:
                continue
            lock = _read_recording_lock(stored.directory)
            if _lock_is_active(lock, stale_after_s=stale_after_s):
                continue
            metadata = stored.metadata
            reason = "process terminated before normal stop" if lock else "recording lock missing"
            try:
                events, _, event_tail = _read_jsonl_meta(stored.directory / "events.jsonl")
                frames, _, frame_tail = _read_jsonl_meta(stored.directory / "frames.jsonl")
                record = TrialRecord(
                    metadata=metadata,
                    directory=stored.directory,
                    events=events,
                    frames=frames,
                    truncated_tail=event_tail or frame_tail,
                )
                integrity = trial_integrity(record)
                metadata.status = STATUS_INTERRUPTED
                metadata.ended_at = utc_now_iso()
                metadata.counts = {
                    "frames": integrity["frames"],
                    "events": integrity["events"] + 1,
                    "invalid_channel_samples": integrity["invalid_channel_samples"],
                    "frames_with_invalid_channels": integrity["frames_with_invalid_channels"],
                    "dropped_frames": integrity["dropped_frames"],
                    "duplicate_frames": integrity["duplicate_frames"],
                    "restarts": integrity["restarts"],
                    "truncated_tail": 1 if integrity["truncated_tail"] else 0,
                }
                event = TrialEvent(
                    "TRIAL_INTERRUPTED",
                    reason,
                    {
                        "recovered_at": utc_now_iso(),
                        "lock": lock,
                        "last_known_status": STATUS_RECORDING,
                    },
                ).to_dict()
                event.setdefault("record_type", "TRIAL_EVENT")
                event.setdefault("trial_id", metadata.trial_id)
                with open(stored.directory / "events.jsonl", "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
                _atomic_json(stored.directory / "metadata.json", metadata.to_dict())
                try:
                    TrialRecorder(metadata, stored.directory).export_csv()
                except OSError:
                    pass
                try:
                    (stored.directory / TRIAL_LOCK_FILENAME).unlink(missing_ok=True)
                except OSError:
                    pass
                recovered.append(metadata.trial_id)
            except OSError:
                # Keep the trial in RECORDING; a later attempt can retry.  Never
                # silently mark it completed.
                continue
        return recovered

    def find(self, trial_id: str) -> StoredTrial | None:
        if not trial_id or "/" in trial_id or "\\" in trial_id or trial_id in (".", ".."):
            return None
        for item in self._scan_trials():
            if item.metadata.trial_id == trial_id:
                return item
        return None

    def load(self, trial_id: str) -> TrialRecord:
        stored = self.find(trial_id)
        if stored is None:
            raise FileNotFoundError(f"trial not found: {trial_id}")
        events, event_errors, event_tail = _read_jsonl_meta(stored.directory / "events.jsonl")
        frames, frame_errors, frame_tail = _read_jsonl_meta(stored.directory / "frames.jsonl")
        return TrialRecord(
            metadata=stored.metadata,
            directory=stored.directory,
            events=events,
            frames=frames,
            read_errors=event_errors + frame_errors,
            truncated_tail=event_tail or frame_tail,
        )

    def export_csv(self, trial_id: str) -> Path:
        stored = self.find(trial_id)
        if stored is None:
            raise FileNotFoundError(f"trial not found: {trial_id}")
        recorder = TrialRecorder(stored.metadata, stored.directory)
        return recorder.export_csv()

    def export_replay_jsonl(self, trial_id: str) -> Path:
        """Rebuild a HELLO + SAMPLE wire file from a recorded trial.

        The raw SAMPLE payload is preferred.  Old trials that predate raw-wire
        persistence are reconstructed from the validated frame fields, so the
        read-only REPLAY path remains usable without touching hardware.
        """
        from ..models import ChannelConfiguration
        from ..protocol import PROTOCOL_VERSION, encode_hello

        stored = self.find(trial_id)
        if stored is None:
            raise FileNotFoundError(f"trial not found: {trial_id}")
        frames, errors, _ = _read_jsonl_meta(stored.directory / "frames.jsonl")
        if errors and not frames:
            raise ValueError("trial frames are unreadable: " + "; ".join(errors))
        params = stored.metadata.parameters or {}
        config_payload = params.get("sensor_config")
        config = ChannelConfiguration.from_dict(config_payload) if config_payload else None
        identities = params.get("device_identities") or {}
        sensor_identity = identities.get("sensor") or {}
        first = frames[0] if frames else {}
        device_id = first.get("device_id") or sensor_identity.get("device_id") or "sensor-replay"
        boot_id = first.get("boot_id") or sensor_identity.get("boot_id") or "replay-boot"
        path = stored.directory / "replay.jsonl"
        with open(path, "w", encoding="utf-8") as handle:
            if config is not None:
                handle.write(
                    encode_hello(
                        device_id,
                        boot_id,
                        config,
                        firmware_version=str(sensor_identity.get("firmware_version") or "trial-replay"),
                    ).decode("utf-8")
                )
            for row in frames:
                if row.get("record_type") != "SENSOR_FRAME":
                    continue
                raw = row.get("raw")
                if isinstance(raw, dict) and raw.get("type") == "SAMPLE":
                    payload = raw
                else:
                    payload = {
                        "protocol_version": PROTOCOL_VERSION,
                        "type": "SAMPLE",
                        "device_id": row.get("device_id", device_id),
                        "boot_id": row.get("boot_id", boot_id),
                        "frame_seq": row.get("frame_seq"),
                        "mcu_time_us": row.get("mcu_time_us"),
                        "channel_ids": row.get("channel_ids"),
                        "channels": row.get("channels"),
                        "valid_mask": row.get("valid_mask"),
                    }
                    if row.get("contact_score") is not None:
                        payload["contact_score"] = row["contact_score"]
                handle.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
        stored.metadata.files["replay"] = path.name
        _atomic_json(stored.directory / "metadata.json", stored.metadata.to_dict())
        return path


def summarize_trial(record: TrialRecord) -> dict[str, Any]:
    integrity = trial_integrity(record)
    return {
        "trial_id": record.metadata.trial_id,
        "name": record.metadata.name,
        "source": record.metadata.source.value,
        "mode": record.metadata.mode,
        "status": record.metadata.status,
        "created_at": record.metadata.created_at,
        "started_at": record.metadata.started_at,
        "ended_at": record.metadata.ended_at,
        "schema_version": record.metadata.schema_version,
        "git_commit": record.metadata.git_commit,
        "video_path": record.metadata.video_path,
        "operator": record.metadata.operator,
        "tags": list(record.metadata.tags),
        "frames": integrity["frames"],
        "events": integrity["events"],
        "control_events": integrity["control_events"],
        "ack_events": integrity["ack_events"],
        "failed_control_events": integrity["failed_control_events"],
        "anomalies": integrity["anomaly_events"],
        "integrity": integrity,
        "read_errors": record.read_errors,
    }


def comparison_summary(record: TrialRecord | dict[str, Any]) -> dict[str, Any]:
    """Small read-only row used by the Analysis multi-trial comparison."""
    if isinstance(record, dict):
        metadata = TrialMetadata.from_dict(record["metadata"])
        record = TrialRecord(
            metadata=metadata,
            directory=Path(record.get("directory", ".")),
            events=list(record.get("events") or []),
            frames=list(record.get("frames") or []),
            read_errors=list(record.get("read_errors") or []),
        )
    summary = summarize_trial(record)
    integrity = summary["integrity"]
    metadata = record.metadata
    return {
        "trial": f"{metadata.trial_id} · {metadata.name}",
        "trial_id": metadata.trial_id,
        "source": metadata.source.value,
        "status": metadata.status,
        "frames": summary["frames"],
        "control": summary["control_events"],
        "ack": summary["ack_events"],
        "dropped": integrity["dropped_frames"],
        "invalid": integrity["invalid_channel_samples"],
        "video": metadata.video_path,
    }
