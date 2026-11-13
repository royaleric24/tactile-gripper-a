"""Continuous raw-data recorder with CSV samples and JSONL events."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .protocol import CSV_COLUMNS, ErrorMessage, HelloMessage, PongMessage, SampleFrame, StatusMessage
from .stats import RunStats

SOFTWARE_VERSION = "tactile-acq-0.1.0"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RunRecorder:
    def __init__(
        self,
        root: Path,
        port: str,
        baud: int,
        identity: Any,
        runtime_config: Dict[str, Any],
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.port = port
        self.baud = baud
        self.identity = identity
        self.runtime_config = runtime_config
        self.started_utc = utc_now_iso()
        self.started_monotonic = time.monotonic()
        self.stats = RunStats()

        self.raw_path = self.root / "raw_frames.jsonl"
        self.csv_path = self.root / "samples.csv"
        self.events_path = self.root / "events.jsonl"
        self.meta_path = self.root / "meta.json"
        self.run_path = self.root / "run.json"

        self._raw_handle = open(self.raw_path, "ab", buffering=0)
        self._csv_handle = open(self.csv_path, "w", newline="", encoding="utf-8")
        self._events_handle = open(self.events_path, "a", encoding="utf-8")
        self._csv_writer = csv.DictWriter(self._csv_handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        self._csv_writer.writeheader()
        self._last_flush = time.monotonic()
        self._last_fsync = time.monotonic()
        self._lines = 0
        self._closed = False

        meta = {
            "software_version": SOFTWARE_VERSION,
            "started_utc": self.started_utc,
            "port": self.port,
            "baud": self.baud,
            "identity": self.identity.__dict__ if hasattr(self.identity, "__dict__") else str(self.identity),
            "runtime_config": self.runtime_config,
            "data_kind": "REAL_HARDWARE_SERIAL",
            "channel_order": [
                "ADC1_AIN0", "ADC1_AIN1", "ADC1_AIN2", "ADC1_AIN3",
                "ADC2_AIN0", "ADC2_AIN1", "ADC2_AIN2", "ADC2_AIN3",
                "ADC3_AIN0", "ADC3_AIN1", "ADC3_AIN2", "ADC3_AIN3",
            ],
        }
        self.meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    def record_line(self, raw_line: bytes, parsed: Any) -> None:
        host_ns = time.time_ns()
        host_mono = time.monotonic_ns()
        host_iso = utc_now_iso()
        self._lines += 1
        self._raw_handle.write(raw_line.rstrip(b"\r\n") + b"\n")

        if isinstance(parsed, SampleFrame):
            frame = replace(
                parsed,
                host_received_ns=host_ns,
                host_received_utc=host_iso,
                host_monotonic_ns=host_mono,
            )
            self.stats.add_sample(frame)
            self._csv_writer.writerow(frame.to_csv_row())
        else:
            self.stats.note_event()
            event: Dict[str, Any] = {
                "host_received_unix_ns": host_ns,
                "host_received_iso": host_iso,
                "host_monotonic_ns": host_mono,
            }
            if isinstance(parsed, (HelloMessage, StatusMessage, ErrorMessage, PongMessage)):
                event["kind"] = type(parsed).__name__.replace("Message", "").upper()
                event["message"] = parsed.raw
            else:
                event["kind"] = "MALFORMED"
                event["error"] = str(parsed)
                event["raw"] = raw_line.decode("utf-8", errors="replace")
                self.stats.note_malformed()
            self._events_handle.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
            if isinstance(parsed, ErrorMessage):
                self._last_error = "{}: {}".format(parsed.code, parsed.message)

        now = time.monotonic()
        if now - self._last_flush >= 1.0:
            self._flush(False)
            self._last_flush = now
        if now - self._last_fsync >= 5.0:
            self._flush(True)
            self._last_fsync = now

    def record_event(self, kind: str, **fields: Any) -> Dict[str, Any]:
        """Append a host-side experiment event (press/release/ready).

        Callers that also read the serial port from another thread should hold
        their own lock around record_event/record_line so the two writers do not
        interleave at the Python level.  The file handles are separate.
        """
        event: Dict[str, Any] = {
            "host_received_unix_ns": time.time_ns(),
            "host_received_iso": utc_now_iso(),
            "host_monotonic_ns": time.monotonic_ns(),
            "kind": kind,
        }
        event.update(fields)
        self._events_handle.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
        self._events_handle.flush()
        return event

    def _flush(self, do_fsync: bool) -> None:
        self._csv_handle.flush()
        self._events_handle.flush()
        if do_fsync:
            for handle in (self._raw_handle, self._csv_handle, self._events_handle):
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass

    def finalize(self) -> Dict[str, Any]:
        if self._closed:
            return {}
        self._flush(True)
        self._csv_handle.close()
        self._events_handle.close()
        self._raw_handle.close()
        self._closed = True
        ended = utc_now_iso()
        summary = self.stats.summary()
        run = {
            "software_version": SOFTWARE_VERSION,
            "data_kind": "REAL_HARDWARE_SERIAL",
            "started_utc": self.started_utc,
            "ended_utc": ended,
            "wall_duration_s": round(time.monotonic() - self.started_monotonic, 3),
            "port": self.port,
            "baud": self.baud,
            "identity": self.identity.__dict__ if hasattr(self.identity, "__dict__") else str(self.identity),
            "summary": summary,
            "files": {
                "raw_frames.jsonl": {
                    "path": str(self.raw_path),
                    "bytes": self.raw_path.stat().st_size,
                    "sha256": sha256_file(self.raw_path),
                },
                "samples.csv": {
                    "path": str(self.csv_path),
                    "bytes": self.csv_path.stat().st_size,
                    "sha256": sha256_file(self.csv_path),
                },
                "events.jsonl": {
                    "path": str(self.events_path),
                    "bytes": self.events_path.stat().st_size,
                    "sha256": sha256_file(self.events_path),
                },
            },
        }
        if getattr(self, "_last_error", None):
            run["last_device_error"] = self._last_error
        self.run_path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
        try:
            directory_fd = os.open(str(self.root), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
        return run


def default_run_directory(port: str, base: Optional[Path] = None) -> Path:
    root = Path(base) if base is not None else Path("data/real/tactile")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = port.replace("/", "_").replace(" ", "_")
    return root / "{}_{}".format(stamp, name)
