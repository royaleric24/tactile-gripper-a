"""Trial storage for live/replay contact detection."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class TrialStore:
    def __init__(self, root: Path, *, source: str, data_kind: str, label: str,
                 config: Dict[str, Any], firmware: Optional[str] = None):
        if data_kind not in ("LIVE_REAL", "REPLAY_REAL", "SIMULATED"):
            raise ValueError("data_kind")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.trial_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:6]
        self.dir = self.root / self.trial_id
        self.dir.mkdir(parents=True, exist_ok=False)
        self.data_kind = data_kind
        self.source = source
        self.label = label
        self.config = config
        self.firmware = firmware
        self.started_utc = utc_now()
        self.files = {
            "meta": self.dir / "meta.json",
            "samples": self.dir / "samples.jsonl",
            "events": self.dir / "events.jsonl",
            "stop_requests": self.dir / "stop_requests.jsonl",
            "summary": self.dir / "SUMMARY.json",
            "report": self.dir / "REPORT.md",
        }
        self._handles = {k: open(v, "w", encoding="utf-8") for k, v in self.files.items()
                         if k in ("samples", "events", "stop_requests")}
        self._samples = 0
        self._events = 0
        self._stops = 0
        self._verified_contact = 0
        self._unverified_contact = 0
        self._invalid = 0
        self._rounds = []
        self._write_meta("RUNNING")

    def _write_meta(self, status: str) -> None:
        meta = {
            "trial_id": self.trial_id,
            "started_utc": self.started_utc,
            "status": status,
            "data_kind": self.data_kind,
            "source": self.source,
            "label": self.label,
            "firmware": self.firmware,
            "detector_config": self.config,
            "units": "ADC counts; voltage display uses nominal AVDD; not pressure/force",
            "note": "LIVE_REAL is real serial; REPLAY_REAL is a replay of a stored real trial; SIMULATED is not real.",
        }
        self.files["meta"].write_text(json.dumps(meta, indent=2) + "\n")

    def sample(self, sample: Dict[str, Any], detection: Dict[str, Any]) -> None:
        record = dict(sample)
        record["detection"] = detection
        self._handles["samples"].write(json.dumps(record) + "\n")
        self._handles["samples"].flush()
        self._samples += 1
        if sample.get("read_ok") is not True or sample.get("ready") is not True:
            self._invalid += 1
        if detection.get("state") == "CONTACT":
            if detection.get("quality") == "VERIFIED":
                self._verified_contact += 1
            else:
                self._unverified_contact += 1

    def event(self, event: Dict[str, Any]) -> None:
        self._handles["events"].write(json.dumps(event) + "\n")
        self._handles["events"].flush()
        self._events += 1

    def stop_request(self, request: Dict[str, Any]) -> None:
        self._handles["stop_requests"].write(json.dumps(request) + "\n")
        self._handles["stop_requests"].flush()
        self._stops += 1
        self.event({"host_monotonic_ns": request.get("host_monotonic_ns"),
                    "kind": "STOP_REQUEST", "request": request})

    def round_marker(self, name: str, **fields) -> None:
        item = {"phase": name, "utc": utc_now()}; item.update(fields)
        self._rounds.append(item)
        self.event({"host_monotonic_ns": fields.get("host_monotonic_ns"),
                    "kind": "ROUND_MARKER", "round": item})

    def finalize(self, status: str = "DONE", errors: Optional[List[str]] = None) -> Dict[str, Any]:
        summary = {
            "trial_id": self.trial_id, "data_kind": self.data_kind, "status": status,
            "samples": self._samples, "events": self._events,
            "verified_contact_samples": self._verified_contact,
            "unverified_contact_samples": self._unverified_contact,
            "invalid_samples": self._invalid, "stop_requests": self._stops,
            "rounds": self._rounds, "errors": errors or [],
            "note": "Contact detection is not pressure/force calibration. UNVERIFIED results must not command the gripper.",
        }
        self.files["summary"].write_text(json.dumps(summary, indent=2) + "\n")
        self._write_meta(status)
        lines = [
            "# Contact Detection Trial {}".format(self.trial_id), "",
            "- data kind: **{}**".format(self.data_kind),
            "- source: `{}`".format(self.source), "- label: {}".format(self.label),
            "- samples: {}; events: {}; invalid: {}".format(self._samples, self._events, self._invalid),
            "- verified contact samples: {}".format(self._verified_contact),
            "- unverified contact samples: {}".format(self._unverified_contact),
            "- dry-run STOP requests: {}".format(self._stops),
            "- status: {}".format(status), "",
            "## Boundary", "",
            "ADC counts are proxies, not pressure or force. UNVERIFIED frames may be displayed but must never trigger automatic gripper closing. LIVE_REAL/REPLAY_REAL are distinct from SIMULATED.",
        ]
        self.files["report"].write_text("\n".join(lines) + "\n")
        for handle in self._handles.values():
            handle.close()
        return summary
