"""Live serial and real-data replay sources."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.cup_grasp.diag_serial import DiagProtocolError, LineFramer, parse_diag_line


class LiveSerialSource(threading.Thread):
    def __init__(self, port: str, baud: int, state, store, *, handshake_timeout=8.0):
        super().__init__(daemon=True)
        self.port = port; self.baud = baud; self.state = state; self.store = store
        self.handshake_timeout = handshake_timeout
        self.stop_event = threading.Event()
        self.ser = None
        self.raw_bin = open(store.dir / "raw.bin", "wb")
        self.raw_hex = open(store.dir / "raw_hex.log", "w", encoding="utf-8")
        self.framer = LineFramer()
        self.last_hello_ns = 0
        self.hello = None

    def _write_raw(self, chunk: bytes):
        self.raw_bin.write(chunk); self.raw_bin.flush()
        self.raw_hex.write("{} {}\n".format(time.monotonic_ns(), chunk.hex())); self.raw_hex.flush()

    def _feed(self, chunk: bytes):
        for line in self.framer.feed(chunk):
            try:
                kind, item = parse_diag_line(line)
            except DiagProtocolError as exc:
                self.state.on_malformed("{} raw={}".format(exc, line.hex()[:160]))
                continue
            if kind == "DIAG_HELLO":
                self.state.on_hello(item)
                self.last_hello_ns = time.monotonic_ns()
                if self.hello is None:
                    self.hello = item
            elif kind == "DIAG_SAMPLE":
                item["host_monotonic_ns"] = time.monotonic_ns()
                self.state.on_sample(item)
        self.state.tick()

    def run(self):
        import serial
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.05, exclusive=True)
            try:
                self.ser.dtr = False; self.ser.rts = False
            except Exception:
                pass
            try:
                self.ser.reset_input_buffer()
            except Exception:
                pass
            self.ser.write(b"HELLO\n"); self.ser.flush()
            self.state.set_connection("CONNECTING", "waiting for DIAG_HELLO")
            deadline = time.monotonic() + self.handshake_timeout
            while time.monotonic() < deadline and self.hello is None and not self.stop_event.is_set():
                chunk = self.ser.read(4096)
                if chunk:
                    self._write_raw(chunk)
                    self._feed(chunk)
            if self.hello is None:
                self.state.on_error("DIAG_HELLO timeout; raw bytes saved")
                return
            self.state.set_connection("STREAMING", "DIAG_HELLO received")
            while not self.stop_event.is_set():
                chunk = self.ser.read(4096)
                if chunk:
                    self._write_raw(chunk)
                    self._feed(chunk)
                else:
                    self.state.tick()
        except Exception as exc:
            self.state.on_error(str(exc))
        finally:
            try:
                if self.ser is not None:
                    self.ser.close()
            except Exception:
                pass
            self.raw_bin.close(); self.raw_hex.close()

    def stop(self):
        self.stop_event.set()


class ReplaySource(threading.Thread):
    def __init__(self, samples_path: Path, state, speed: float = 1.0, hello: Optional[Dict[str, Any]] = None):
        super().__init__(daemon=True)
        self.samples_path = Path(samples_path); self.state = state; self.speed = max(0.1, speed)
        self.hello = hello; self.stop_event = threading.Event()
        self.error = None

    def run(self):
        try:
            if self.hello:
                self.state.on_hello(self.hello)
            self.state.set_connection("STREAMING", "REPLAY_REAL")
            with open(self.samples_path, encoding="utf-8") as handle:
                for line in handle:
                    if self.stop_event.is_set():
                        break
                    try:
                        item = json.loads(line)
                    except ValueError:
                        self.state.on_malformed("replay invalid JSON line")
                        continue
                    item.pop("detection", None)
                    item["host_monotonic_ns"] = time.monotonic_ns()
                    self.state.on_sample(item)
                    time.sleep((1.0 / 20.0) / self.speed)
            self.state.set_connection("DONE", "replay finished")
        except Exception as exc:
            self.error = str(exc)
            self.state.on_error(str(exc))

    def stop(self):
        self.stop_event.set()
