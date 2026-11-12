"""Trial storage: metadata JSON, events/frames JSONL and CSV export.

Recordings are written below exactly one source-specific directory:
``data/real/trials`` for LIVE and ``data/simulated/trials`` for SIMULATION.
REPLAY is read-only and cannot create a recording.
"""

from __future__ import annotations

import csv
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..models import (
    ControlEvent,
    TactileFrame,
    TrialEvent,
    TrialMetadata,
    utc_now_iso,
)
from ..sources import DataSource, trial_parent
from ..paths import PROJECT_ROOT


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


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.is_file():
        return rows, errors
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError as exc:
            errors.append(f"{path.name}:{number}: invalid JSON ({exc})")
            continue
        if not isinstance(value, dict):
            errors.append(f"{path.name}:{number}: root is not an object")
            continue
        rows.append(value)
    return rows, errors


class TrialRecorder:
    """Write one trial.  A recorder never changes its source after creation."""

    def __init__(self, metadata: TrialMetadata, directory: Path):
        self.metadata = metadata
        self.directory = Path(directory)
        self.events_path = self.directory / "events.jsonl"
        self.frames_path = self.directory / "frames.jsonl"
        self.metadata_path = self.directory / "metadata.json"
        self.csv_path = self.directory / "frames.csv"
        self._lock = threading.RLock()
        self._event_file = None
        self._frame_file = None
        self.frame_count = int(metadata.counts.get("frames", 0))
        self.event_count = int(metadata.counts.get("events", 0))

    @property
    def recording(self) -> bool:
        return self.metadata.status == "RECORDING"

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> TrialMetadata:
        with self._lock:
            if self.metadata.status not in ("CREATED", "STOPPED", "COMPLETED", "ABORTED"):
                raise RuntimeError(f"cannot start trial in status {self.metadata.status}")
            if self._event_file is None:
                self._event_file = open(self.events_path, "a", encoding="utf-8")
            if self._frame_file is None:
                self._frame_file = open(self.frames_path, "a", encoding="utf-8")
            self.metadata.status = "RECORDING"
            self.metadata.started_at = self.metadata.started_at or utc_now_iso()
            self._write_metadata()
            self._append_event(
                TrialEvent("TRIAL_START", "recording started", {"mode": self.metadata.mode})
            )
            return self.metadata

    def stop(self, reason: str = "manual", *, aborted: bool = False) -> TrialMetadata:
        with self._lock:
            if self.metadata.status != "RECORDING":
                raise RuntimeError(f"trial is not recording (status {self.metadata.status})")
            self._append_event(
                TrialEvent("TRIAL_STOP", reason, {"aborted": aborted})
            )
            self.metadata.status = "ABORTED" if aborted else "COMPLETED"
            self.metadata.ended_at = utc_now_iso()
            self._close_files()
            self._write_metadata()
            self.export_csv()
            return self.metadata

    def _close_files(self) -> None:
        for handle in (self._event_file, self._frame_file):
            if handle is not None:
                handle.flush()
                handle.close()
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

    def record_frame(self, frame: TactileFrame) -> None:
        with self._lock:
            if not self.recording:
                return
            if frame.source is not self.metadata.source:
                raise ValueError(
                    f"frame source {frame.source.value} does not match trial source {self.metadata.source.value}"
                )
            if self._frame_file is None:
                self._frame_file = open(self.frames_path, "a", encoding="utf-8")
            payload = {
                "record_type": "SENSOR_FRAME",
                "trial_id": self.metadata.trial_id,
                **frame.to_dict(include_wire=False),
            }
            self._frame_file.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
            self._frame_file.flush()
            self.frame_count += 1
            self.metadata.counts["frames"] = self.frame_count

    def add_event(self, event_type: str, message: str, data: dict | None = None) -> TrialEvent:
        event = TrialEvent(event_type, message, data or {})
        with self._lock:
            self._append_event(event)
        return event

    def _append_event(self, event: TrialEvent | dict[str, Any]) -> None:
        if self._event_file is None:
            self._event_file = open(self.events_path, "a", encoding="utf-8")
        payload = event if isinstance(event, dict) else event.to_dict()
        payload.setdefault("record_type", "TRIAL_EVENT")
        payload.setdefault("trial_id", self.metadata.trial_id)
        self._event_file.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
        self._event_file.flush()
        self.event_count += 1
        self.metadata.counts["events"] = self.event_count

    def _write_metadata(self) -> None:
        self.metadata.files = {
            "metadata": "metadata.json",
            "events": "events.jsonl",
            "frames": "frames.jsonl",
            "csv": "frames.csv",
        }
        self.metadata.counts = {"frames": self.frame_count, "events": self.event_count}
        _atomic_json(self.metadata_path, self.metadata.to_dict())

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
    ) -> TrialRecorder:
        if self.source is DataSource.REPLAY:
            raise PermissionError("REPLAY is read-only")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("trial name is required")
        parent = self.parent
        parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        trial_id = f"T-{timestamp}-{uuid.uuid4().hex[:6]}"
        directory = parent / trial_id
        directory.mkdir(parents=True, exist_ok=False)
        metadata = TrialMetadata(
            trial_id=trial_id,
            name=name.strip(),
            source=self.source,
            mode=mode,
            conditions=dict(conditions or {}),
            parameters=dict(parameters or {}),
            notes=notes,
            files={
                "metadata": "metadata.json",
                "events": "events.jsonl",
                "frames": "frames.jsonl",
                "csv": "frames.csv",
            },
            counts={"frames": 0, "events": 0},
        )
        recorder = TrialRecorder(metadata, directory)
        recorder._write_metadata()
        return recorder

    def list_trials(self, *, include_real: bool = True, include_simulated: bool = True) -> list[StoredTrial]:
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

    def find(self, trial_id: str) -> StoredTrial | None:
        if not trial_id or "/" in trial_id or "\\" in trial_id or trial_id in (".", ".."):
            return None
        for item in self.list_trials():
            if item.metadata.trial_id == trial_id:
                return item
        return None

    def load(self, trial_id: str) -> TrialRecord:
        stored = self.find(trial_id)
        if stored is None:
            raise FileNotFoundError(f"trial not found: {trial_id}")
        events, event_errors = _read_jsonl(stored.directory / "events.jsonl")
        frames, frame_errors = _read_jsonl(stored.directory / "frames.jsonl")
        return TrialRecord(
            metadata=stored.metadata,
            directory=stored.directory,
            events=events,
            frames=frames,
            read_errors=event_errors + frame_errors,
        )

    def export_csv(self, trial_id: str) -> Path:
        stored = self.find(trial_id)
        if stored is None:
            raise FileNotFoundError(f"trial not found: {trial_id}")
        recorder = TrialRecorder(stored.metadata, stored.directory)
        return recorder.export_csv()


def summarize_trial(record: TrialRecord) -> dict[str, Any]:
    control_events = [item for item in record.events if item.get("record_type") == "CONTROL_EVENT"]
    anomalies = [
        item
        for item in record.events
        if item.get("record_type") == "TRIAL_EVENT"
        and (item.get("event_type") in ("ANOMALY", "SENSOR_ERROR", "FRAME_ANOMALY", "FAULT"))
    ]
    return {
        "trial_id": record.metadata.trial_id,
        "name": record.metadata.name,
        "source": record.metadata.source.value,
        "mode": record.metadata.mode,
        "status": record.metadata.status,
        "created_at": record.metadata.created_at,
        "started_at": record.metadata.started_at,
        "ended_at": record.metadata.ended_at,
        "frames": len(record.frames),
        "events": len(record.events),
        "control_events": len(control_events),
        "anomalies": len(anomalies),
        "read_errors": record.read_errors,
    }
