"""Real-sensor serial transport scaffolding.

The actual hardware scan/protocol is NOT confirmed.  This module only provides
the lifecycle/transport layer around the existing strict JSONL parser; it never
writes to the device and never opens a port until ``connect()`` is called.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..constants import MAX_SENSOR_LINE_BYTES
from ..errors import SensorOffline
from .sensor import SensorAdapter


@dataclass(frozen=True)
class SerialSensorConfig:
    port: str | None = None
    baudrate: int = 115200
    bytesize: int = 8
    parity: str = "N"
    stopbits: int = 1
    read_timeout_s: float = 0.1
    boot_wait_s: float = 0.0
    max_line_bytes: int = MAX_SENSOR_LINE_BYTES
    reconnect_enabled: bool = True
    reconnect_initial_s: float = 0.5
    reconnect_max_s: float = 10.0

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
        except BaseException as exc:
            try:
                port.close()
            except Exception:
                pass
            raise SensorOffline(f"could not open sensor serial port: {exc}") from exc
        self.port = port
        self.connected = True
        self.opened_count += 1

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
        if timeout_s <= 0 and not getattr(self.port, "in_waiting", 0):
            return None
        deadline = self.clock() + max(0.0, timeout_s)
        buffer = bytearray()
        discard = False
        while True:
            remaining = max(0.0, deadline - self.clock())
            if remaining <= 0:
                break
            try:
                self.port.timeout = min(max(self.config.read_timeout_s, 0.001), remaining)
                byte = self.port.read(1)
            except Exception as exc:
                raise SensorOffline(f"sensor serial read failed: {exc}") from exc
            if not byte:
                break
            if byte == b"\n":
                if discard:
                    discard = False
                    buffer.clear()
                    continue
                buffer.extend(byte)
                return bytes(buffer)
            if discard:
                continue
            if len(buffer) < self.config.max_line_bytes:
                buffer.extend(byte)
            else:
                discard = True
                self.oversize_lines += 1
        return None


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
