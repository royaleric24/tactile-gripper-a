"""Shared demo state: detector, trial storage, dry-run gripper request."""
from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, Optional

from .config import DetectorConfig
from .detector import CONTACT, UNKNOWN, ContactDetector
from .store import TrialStore


class DryRunStopSink:
    """Only records STOP requests. Never touches serial/S3/PWM."""
    def __init__(self, store: TrialStore):
        self.store = store
        self.requests = []

    def request_stop(self, sample: Dict[str, Any], reason: str) -> Dict[str, Any]:
        request = {
            "host_monotonic_ns": sample.get("host_monotonic_ns"),
            "source_sequence": sample.get("seq"),
            "reason": reason,
            "action": "STOP",
            "executed": False,
            "mode": "DRY_RUN",
            "note": "No servo/gripper command was sent.",
        }
        self.requests.append(request)
        self.store.stop_request(request)
        return request


class DemoState:
    def __init__(self, store: TrialStore, detector: Optional[ContactDetector] = None,
                 source_name: str = "unknown"):
        self.store = store
        self.detector = detector or ContactDetector(DetectorConfig())
        self.stop_sink = DryRunStopSink(store)
        self.source_name = source_name
        self.connection = "CONNECTING"
        self.connection_detail = ""
        self.firmware = store.firmware
        self.latest_sample: Optional[Dict[str, Any]] = None
        self.latest_detection = self.detector.snapshot()
        self.events = deque(maxlen=200)
        self.history = deque(maxlen=300)
        self.sample_count = 0
        self.malformed = 0
        self.last_error: Optional[str] = None
        self.round_name: Optional[str] = None
        self.started_ns = time.monotonic_ns()
        self._lock = threading.Lock()

    def _emit(self, event: Dict[str, Any]) -> None:
        event = dict(event)
        event.setdefault("utc", time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()))
        self.events.append(event)
        self.store.event(event)

    def set_connection(self, status: str, detail: str = "") -> None:
        with self._lock:
            self.connection = status
            self.connection_detail = detail
            if status not in ("CONNECTED", "STREAMING"):
                self.detector.force_unknown(time.monotonic_ns(), "serial_" + status.lower())
                self.latest_detection = self.detector.snapshot()
            self._emit({"kind": "CONNECTION", "status": status, "detail": detail})

    def on_hello(self, hello: Dict[str, Any]) -> None:
        with self._lock:
            self.firmware = hello.get("firmware")
            self.connection = "CONNECTED"
            self.connection_detail = "DIAG_HELLO"
            self._emit({"kind": "HELLO", "firmware": self.firmware,
                        "fixed_reg0": hello.get("fixed_reg0"),
                        "fixed_reg2": hello.get("fixed_reg2"),
                        "fixed_reg3": hello.get("fixed_reg3")})

    def on_sample(self, sample: Dict[str, Any], now_ns: Optional[int] = None) -> Dict[str, Any]:
        now_ns = now_ns if now_ns is not None else int(sample.get("host_monotonic_ns") or time.monotonic_ns())
        with self._lock:
            before_state = self.detector.state.state
            detection = self.detector.update(sample, now_ns)
            for event in self.detector.drain_events():
                self._emit(event)
            self.latest_sample = sample
            self.latest_detection = detection
            self.history.append({
                "host_monotonic_ns": now_ns,
                "counts": sample.get("counts"),
                "filtered_counts": detection.get("filtered_counts"),
                "baseline_counts": detection.get("baseline_counts"),
                "state": detection.get("state"),
                "quality": detection.get("quality"),
            })
            self.sample_count += 1
            self.store.sample(sample, detection)
            if (before_state != CONTACT and detection.get("state") == CONTACT
                    and detection.get("control_eligible") is True):
                request = self.stop_sink.request_stop(sample, "verified_contact")
                self._emit({"kind": "DRY_RUN_STOP", "request": request})
            return detection

    def on_error(self, message: str) -> None:
        with self._lock:
            self.last_error = message
            self.connection = "ERROR"
            self.detector.force_unknown(time.monotonic_ns(), "serial_error")
            self.latest_detection = self.detector.snapshot()
            self._emit({"kind": "ERROR", "message": message})

    def on_malformed(self, message: str) -> None:
        with self._lock:
            self.malformed += 1
            self.last_error = message

    def recalibrate(self) -> Dict[str, Any]:
        with self._lock:
            self.detector.recalibrate(time.monotonic_ns(), "user_recalibrate")
            for event in self.detector.drain_events():
                self._emit(event)
            self.latest_detection = self.detector.snapshot()
            self._emit({"kind": "RECALIBRATE"})
            return self.latest_detection

    def round_marker(self, name: str) -> None:
        with self._lock:
            self.round_name = name
            self.store.round_marker(name, host_monotonic_ns=time.monotonic_ns())
            self._emit({"kind": "ROUND", "round": name})

    def tick(self) -> Dict[str, Any]:
        with self._lock:
            before = self.detector.state.state
            self.latest_detection = self.detector.tick(time.monotonic_ns())
            for event in self.detector.drain_events():
                self._emit(event)
            return self.latest_detection

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "source": self.source_name,
                "data_kind": self.store.data_kind,
                "label": self.store.label,
                "trial_id": self.store.trial_id,
                "connection": self.connection,
                "connection_detail": self.connection_detail,
                "firmware": self.firmware,
                "sample_count": self.sample_count,
                "malformed_lines": self.malformed,
                "last_error": self.last_error,
                "round": self.round_name,
                "detection": self.latest_detection,
                "latest_sample": self.latest_sample,
                "events": list(self.events)[-20:],
                "history": list(self.history),
                "stop_requests": list(self.stop_sink.requests)[-10:],
                "boundary": "UNVERIFIED contact candidates never trigger STOP; dry-run only.",
            }


class S3StopSink:
    """Reserved real-gripper interface. Not enabled in H4."""
    def request_stop(self, sample, reason):
        raise PermissionError("real S3 STOP is not enabled; H4 is dry-run only")
