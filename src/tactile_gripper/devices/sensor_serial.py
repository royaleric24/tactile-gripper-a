"""Real-sensor serial transport scaffolding.

The actual hardware scan/protocol is NOT confirmed.  This module only provides
the lifecycle/transport layer around the existing strict JSONL parser; it never
writes to the device and never opens a port until ``connect()`` is called.
"""

from __future__ import annotations

import json
import math
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..errors import SensorOffline
from .sensor import SensorAdapter


@dataclass(frozen=True)
class SerialSensorConfig:
    port: str | None = None
    baudrate: int = 921600
    bytesize: int = 8
    parity: str = "N"
    stopbits: int = 1
    read_timeout_s: float = 0.1
    boot_wait_s: float = 0.0
    max_line_bytes: int = 8192
    reconnect_enabled: bool = True
    reconnect_initial_s: float = 0.5
    reconnect_max_s: float = 10.0
    queries_enabled: bool = True

    def __post_init__(self) -> None:
        if self.port is not None and not isinstance(self.port, str):
            raise ValueError("port must be null or string")
        if type(self.baudrate) is not int or self.baudrate <= 0:
            raise ValueError("baudrate must be a positive integer")
        if self.bytesize not in (5, 6, 7, 8):
            raise ValueError("bytesize must be 5..8")
        if self.parity not in ("N", "E", "O"):
            raise ValueError("parity must be N, E or O")
        if self.stopbits not in (1, 2):
            raise ValueError("stopbits must be 1 or 2")
        for name in ("read_timeout_s", "boot_wait_s", "reconnect_initial_s", "reconnect_max_s"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and >= 0")
        if type(self.max_line_bytes) is not int or self.max_line_bytes <= 0:
            raise ValueError("max_line_bytes must be positive")
        if type(self.queries_enabled) is not bool:
            raise ValueError("queries_enabled must be boolean")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SerialSensorConfig":
        if not isinstance(value, dict):
            raise ValueError("sensor serial config must be an object")
        known = {field for field in cls.__dataclass_fields__}
        return cls(**{key: item for key, item in value.items() if key in known})

    @classmethod
    def from_file(cls, path: Path | str | None) -> "SerialSensorConfig":
        if path is None:
            return cls()
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if "sensor_serial" in value:
            value = value["sensor_serial"]
        return cls.from_dict(value)

    def with_port(self, port: str | None, baudrate: int | None = None) -> "SerialSensorConfig":
        return SerialSensorConfig(
            port=port,
            baudrate=self.baudrate if baudrate is None else baudrate,
            bytesize=self.bytesize,
            parity=self.parity,
            stopbits=self.stopbits,
            read_timeout_s=self.read_timeout_s,
            boot_wait_s=self.boot_wait_s,
            max_line_bytes=self.max_line_bytes,
            reconnect_enabled=self.reconnect_enabled,
            reconnect_initial_s=self.reconnect_initial_s,
            reconnect_max_s=self.reconnect_max_s,
            queries_enabled=self.queries_enabled,
        )


class SerialSensorTransport:
    """Read-only pyserial line transport.

    No port is touched at construction.  ``connect`` is explicit; DTR/RTS are
    deasserted before opening to avoid an unintended reset.  The transport has
    no write method by design.
    """

    def __init__(
        self,
        config: SerialSensorConfig,
        *,
        clock=time.monotonic,
        sleeper=time.sleep,
    ):
        self.config = config
        self.clock = clock
        self.sleeper = sleeper
        self.port = None
        self.connected = False
        self.oversize_lines = 0
        self.opened_count = 0
        self.last_query = None
        self._partial = bytearray()
        self._lines: deque[bytes] = deque()
        self._discard = False

    @property
    def baudrate(self) -> int:
        return self.config.baudrate

    def connect(self) -> None:
        if self.connected:
            raise RuntimeError("already_connected")
        if not self.config.port:
            raise SensorOffline("sensor serial port is not configured")
        import serial  # local import: no hardware import at module import time

        port = serial.Serial(
            port=None,
            baudrate=self.config.baudrate,
            bytesize=self.config.bytesize,
            parity=self.config.parity,
            stopbits=self.config.stopbits,
            timeout=self.config.read_timeout_s,
            write_timeout=0,
            exclusive=True,
        )
        port.dtr = False
        port.rts = False
        port.port = self.config.port
        try:
            port.open()
            if self.config.boot_wait_s:
                self.sleeper(self.config.boot_wait_s)
            # macOS opening the port resets the ESP32. Discard boot text that
            # arrived during the wait so the V2 handshake sees only the HELLO
            # response instead of treating boot noise as a rejected frame.
            reset_input = getattr(port, "reset_input_buffer", None)
            if reset_input is not None:
                reset_input()
            # A line may have been mid-transmission when the buffer was reset;
            # drop that partial line so the first parsed line is a full frame.
            self._partial.clear()
            self._lines.clear()
            self._discard = False
        except BaseException as exc:
            try:
                port.close()
            except Exception:
                pass
            raise SensorOffline(f"could not open sensor serial port: {exc}") from exc
        self.port = port
        self.connected = True
        self.opened_count += 1
        self._partial.clear()
        self._lines.clear()
        self._discard = False

    def write_line(self, payload: bytes) -> None:
        """Explicit, opt-in host query.  Never opens or arms the gripper."""
        if not self.config.queries_enabled:
            raise SensorOffline("sensor queries are disabled by configuration")
        if not self.connected or self.port is None:
            raise SensorOffline("sensor serial port is not connected")
        try:
            if self.port.write(payload) != len(payload):
                raise OSError("short serial write")
            self.last_query = payload
        except Exception as exc:
            raise SensorOffline(f"sensor serial write failed: {exc}") from exc

    def close(self) -> None:
        if self.port is not None:
            try:
                self.port.close()
            finally:
                self.port = None
                self.connected = False

    def readline(self, timeout_s: float) -> bytes | None:
        if not self.connected or self.port is None:
            return None
        deadline = self.clock() + max(0.0, timeout_s)
        # A tick uses timeout=0. Drain only currently available bytes and
        # keep incomplete lines across ticks; never block the UI on the port.
        for _ in range(16):
            if self._lines:
                return self._lines.popleft()
            try:
                waiting = self.port.in_waiting
                remaining = max(0.0, deadline - self.clock())
                if not waiting and remaining == 0:
                    return None
                self.port.timeout = 0 if waiting else min(self.config.read_timeout_s, remaining)
                chunk = self.port.read(min(waiting, 4096) if waiting else 1)
            except Exception as exc:
                raise SensorOffline(f"sensor serial read failed: {exc}") from exc
            if not chunk:
                return None
            for byte in chunk:
                if byte == 10:
                    if not self._discard and len(self._partial) < self.config.max_line_bytes:
                        self._lines.append(bytes(self._partial) + b"\n")
                    elif not self._discard:
                        self.oversize_lines += 1
                    self._discard = False
                    self._partial.clear()
                    continue
                if not self._discard:
                    if len(self._partial) < self.config.max_line_bytes:
                        self._partial.append(byte)
                    else:
                        self._discard = True
                        self.oversize_lines += 1
        return self._lines.popleft() if self._lines else None


def serial_sensor_adapter(
    config: SerialSensorConfig,
    *,
    channel_config=None,
    clock_ns=time.monotonic_ns,
    stale_after_s: float = 2.0,
) -> SensorAdapter:
    """Build a LIVE SensorAdapter around a replaceable serial transport."""
    from ..sources import DataSource

    transport = SerialSensorTransport(config)
    reconnect = config.reconnect_enabled
    return SensorAdapter(
        transport,
        channel_config,
        source=DataSource.LIVE,
        clock_ns=clock_ns,
        stale_after_s=stale_after_s,
        max_line_bytes=min(config.max_line_bytes, 8192),
        strict_v2=True,
        request_hello_on_connect=config.queries_enabled,
        transport_factory=(lambda: SerialSensorTransport(config)) if reconnect else None,
        reconnect_initial_s=config.reconnect_initial_s,
        reconnect_max_s=config.reconnect_max_s,
    )


class ReconnectableSensorTransport:
    """Small test helper for a transport factory (not used in production)."""

    def __init__(self, factory: Callable[[], Any]):
        self.factory = factory
        self.current = None

    def connect(self) -> None:
        self.current = self.factory()
        self.current.connect()

    def close(self) -> None:
        if self.current is not None:
            self.current.close()

    def readline(self, timeout_s: float):
        if self.current is None:
            return None
        return self.current.readline(timeout_s)
