"""Mac-side acquisition and persistence for MATRIX_FRAME JSON Lines.

The transport is injected so this module can be tested with a fake session.  It
never fabricates cells: only frames received from the device are written.
"""
from __future__ import annotations

import csv
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .analysis import baseline_from_frames, summarize_frames
from .model import CELL_COUNT, MatrixFrame, cell_coord, cell_label, load_config
from .protocol import parse_matrix_line

SOFTWARE_VERSION = "tactile-matrix-acq-0.1.0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_run_directory(port: str, base: Optional[Path] = None) -> Path:
    base = base or Path(__file__).resolve().parents[2] / "data/real/tactile_matrix"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_port = port.replace("/", "_").replace(":", "_")
    return Path(base) / "{}_{}".format(stamp, safe_port)


class MatrixRecorder:
    def __init__(self, run_dir: Path, port: str, baud: int, config: Dict[str, Any]) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.port = port
        self.baud = baud
        self.config = config
        self.started_utc = datetime.now(timezone.utc).isoformat()
        self.frames: List[MatrixFrame] = []
        self.errors: List[Dict[str, Any]] = []
        self.raw_path = self.run_dir / "raw_frames.jsonl"
        self.csv_path = self.run_dir / "cells.csv"
        self.events_path = self.run_dir / "events.jsonl"
        self.run_path = self.run_dir / "run.json"
        self._raw = open(self.raw_path, "w", encoding="utf-8")
        self._events = open(self.events_path, "w", encoding="utf-8")
        self._csv = open(self.csv_path, "w", encoding="utf-8", newline="")
        self._writer = csv.writer(self._csv)
        self._writer.writerow([
            "frame_seq", "timestamp_us", "cell_index", "cell", "row", "column",
            "value", "valid", "flags",
        ])
        self.first_timestamp_us: Optional[int] = None
        self.last_timestamp_us: Optional[int] = None

    def record_line(self, raw: str, frame: MatrixFrame) -> None:
        self._raw.write(raw.rstrip("\r\n") + "\n")
        self._raw.flush()
        self.frames.append(frame)
        if self.first_timestamp_us is None:
            self.first_timestamp_us = frame.timestamp_us
        self.last_timestamp_us = frame.timestamp_us
        for index in range(CELL_COUNT):
            row, column = cell_coord(index)
            self._writer.writerow([
                frame.frame_seq,
                frame.timestamp_us,
                index,
                cell_label(index),
                row,
                column,
                "" if frame.cells[index] is None else frame.cells[index],
                int(frame.valid[index]),
                frame.flags[index],
            ])
        self._csv.flush()

    def record_error(self, text: str, error: Exception) -> None:
        event = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "kind": "PARSE_ERROR",
            "error": str(error),
            "raw": text[:500],
        }
        self.errors.append(event)
        self._events.write(json.dumps(event) + "\n")
        self._events.flush()

    def finalize(self) -> Dict[str, Any]:
        self._raw.close()
        self._events.close()
        self._csv.close()
        ended = datetime.now(timezone.utc).isoformat()
        summary = summarize_frames(self.frames)
        period = None
        if len(self.frames) >= 2 and self.first_timestamp_us is not None and self.last_timestamp_us is not None:
            span = self.last_timestamp_us - self.first_timestamp_us
            if span > 0:
                period = span / float(len(self.frames) - 1)
        run = {
            "software_version": SOFTWARE_VERSION,
            "data_kind": "REAL_HARDWARE_SERIAL" if self.frames else "NO_DATA",
            "started_utc": self.started_utc,
            "ended_utc": ended,
            "port": self.port,
            "baud": self.baud,
            "config": self.config,
            "frames": len(self.frames),
            "parse_errors": len(self.errors),
            "measured_frame_period_us": period,
            "measured_frame_rate_hz": (1_000_000.0 / period) if period else None,
            "summary": summary,
            "files": {
                "raw_frames.jsonl": str(self.raw_path),
                "cells.csv": str(self.csv_path),
                "events.jsonl": str(self.events_path),
            },
        }
        run["file_sha256"] = {
            name: sha256(Path(path))
            for name, path in run["files"].items()
            if Path(path).is_file()
        }
        self.run_path.write_text(json.dumps(run, indent=2) + "\n")
        return run


def record_session(session, duration_s: float, recorder: MatrixRecorder, poll_s: float = 0.01) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        while time.monotonic() - started < duration_s:
            for raw in session.read_available():
                text = raw.decode("utf-8", errors="replace").rstrip("\r")
                if not text:
                    continue
                try:
                    frame = parse_matrix_line(text)
                except Exception as exc:  # preserve the raw line and continue
                    recorder.record_error(text, exc)
                    continue
                recorder.record_line(text, frame)
            time.sleep(poll_s)
    except KeyboardInterrupt:
        pass
    finally:
        return recorder.finalize()
