"""Serial discovery, connection and device identification.

The old ESP32 and the ESP32-S3 can both expose a CP210x port.  A port name is
therefore never treated as proof of identity: the collector asks the device for
STATUS and requires the tactile firmware version prefix before it writes any
experiment data.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

import serial
from serial.tools import list_ports

from .protocol import (
    ErrorMessage,
    HelloMessage,
    PongMessage,
    SampleFrame,
    StatusMessage,
    encode_command,
    parse_message,
)

TACTILE_FIRMWARE_PREFIX = "tactile-sense-"


class SerialTransportError(Exception):
    pass


class DeviceIdentityError(Exception):
    pass


def list_serial_ports() -> List[Dict[str, Any]]:
    result = []
    for info in list_ports.comports():
        device = info.device
        description = info.description or ""
        is_bluetooth = "bluetooth" in device.lower() or "bluetooth" in description.lower()
        is_debug = "debug-console" in device.lower()
        is_usb = info.vid is not None
        result.append(
            {
                "device": device,
                "description": description,
                "hwid": info.hwid,
                "vid": None if info.vid is None else "{:04X}".format(info.vid),
                "pid": None if info.pid is None else "{:04X}".format(info.pid),
                "serial_number": info.serial_number,
                "manufacturer": info.manufacturer,
                "product": info.product,
                "interface": info.interface,
                "is_usb": is_usb,
                "candidate": is_usb and not is_bluetooth and not is_debug,
            }
        )
    result.sort(key=lambda item: item["device"])
    return result


def candidates(ports: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    ports = ports if ports is not None else list_serial_ports()
    return [item for item in ports if item["candidate"]]


def choose_port(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    found = candidates()
    if len(found) == 1:
        return found[0]["device"]
    if not found:
        raise SerialTransportError(
            "no USB serial port found; connect the old ESP32 USB cable and check the cable/hub"
        )
    names = ", ".join(item["device"] for item in found)
    raise SerialTransportError(
        "multiple USB serial ports found ({}); pass --port explicitly after confirming the old ESP32".format(names)
    )


def port_info(device: str) -> Dict[str, Any]:
    for item in list_serial_ports():
        if item["device"] == device:
            return item
    return {"device": device, "candidate": False, "note": "port not present at enumeration time"}


@dataclass
class DeviceIdentity:
    device_id: str
    boot_id: str
    firmware_version: str
    channel_count: int
    reference_mode: Optional[str]
    streaming: bool
    adc_status: List[Dict[str, Any]]
    port: str
    port_info: Dict[str, Any]
    hello_seen: bool = False
    hello: Optional[Dict[str, Any]] = None


class SerialSession:
    def __init__(self, port: str, baud: int = 921600) -> None:
        self.port = port
        self.baud = baud
        self.ser: Optional[serial.Serial] = None
        self._buffer = bytearray()
        self._line_count = 0

    def open(self) -> None:
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.0,
                write_timeout=1.0,
                exclusive=True,
            )
        except (serial.SerialException, OSError) as exc:
            raise SerialTransportError("cannot open {}: {}".format(self.port, exc)) from exc
        try:
            self.ser.reset_input_buffer()
        except (serial.SerialException, OSError):
            pass

    @property
    def is_open(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def close(self) -> None:
        if self.ser is not None:
            try:
                self.ser.close()
            except (serial.SerialException, OSError):
                pass
            self.ser = None

    def send_bytes(self, payload: bytes) -> None:
        if self.ser is None:
            raise SerialTransportError("serial port is not open")
        try:
            self.ser.write(payload)
            self.ser.flush()
        except (serial.SerialException, OSError) as exc:
            raise SerialTransportError("serial write failed: {}".format(exc)) from exc

    def send_command(
        self,
        cmd: str,
        value: Any = None,
        target_id: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> str:
        request_id = request_id or uuid.uuid4().hex[:12]
        self.send_bytes(encode_command(cmd, value=value, request_id=request_id, target_id=target_id))
        return request_id

    def read_available(self) -> List[bytes]:
        if self.ser is None:
            raise SerialTransportError("serial port is not open")
        try:
            waiting = self.ser.in_waiting
            chunk = self.ser.read(waiting if waiting > 0 else 1)
        except (serial.SerialException, OSError) as exc:
            raise SerialTransportError("serial read failed: {}".format(exc)) from exc
        if chunk:
            self._buffer.extend(chunk)
        lines: List[bytes] = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                break
            line = bytes(self._buffer[:newline])
            del self._buffer[: newline + 1]
            if line.endswith(b"\r"):
                line = line[:-1]
            if line:
                lines.append(line)
        if len(self._buffer) > 65536:
            self._buffer.clear()
            raise SerialTransportError("serial line exceeded 64 KiB without a newline")
        return lines

    def messages(self, timeout_s: float = 0.0) -> List[Any]:
        """Return parsed messages received within the timeout."""
        deadline = time.monotonic() + timeout_s
        result: List[Any] = []
        while True:
            for line in self.read_available():
                self._line_count += 1
                try:
                    result.append(parse_message(line))
                except Exception as exc:  # the caller records the raw line separately
                    result.append(exc)
            if time.monotonic() >= deadline:
                break
            time.sleep(0.003)
        return result

    def wait_hello(self, timeout_s: float = 2.0) -> Optional[HelloMessage]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for item in self.messages(0.05):
                if isinstance(item, HelloMessage):
                    return item
            time.sleep(0.01)
        return None

    def identify(self, timeout_s: float = 8.0) -> DeviceIdentity:
        if not self.is_open:
            self.open()
        hello = self.wait_hello(1.5)
        deadline = time.monotonic() + timeout_s
        status: Optional[StatusMessage] = None
        last_error: Optional[Exception] = None
        request_id = uuid.uuid4().hex[:12]
        next_send = 0.0
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_send:
                try:
                    self.send_command("STATUS", request_id=request_id)
                except SerialTransportError as exc:
                    last_error = exc
                    break
                next_send = now + 0.7
            for item in self.messages(0.05):
                if isinstance(item, StatusMessage) and item.request_id == request_id:
                    status = item
                    break
                if isinstance(item, HelloMessage) and hello is None:
                    hello = item
                if isinstance(item, ErrorMessage):
                    last_error = DeviceIdentityError(
                        "device replied ERROR {}: {}".format(item.code, item.message)
                    )
            if status is not None:
                break
            time.sleep(0.005)

        if status is None and hello is None:
            detail = "" if last_error is None else " ({})".format(last_error)
            raise DeviceIdentityError(
                "no tactile STATUS/HELLO response from {}{}; the port may belong to the S3 or another device, "
                "the baud rate may differ, or the firmware may not be running".format(self.port, detail)
            )
        firmware = (status.firmware_version if status is not None else hello.firmware_version)
        if not firmware.startswith(TACTILE_FIRMWARE_PREFIX):
            raise DeviceIdentityError(
                "{} reports firmware_version={!r}, not the tactile firmware ({}*); refusing to treat it as the "
                "sensor".format(self.port, firmware, TACTILE_FIRMWARE_PREFIX)
            )
        channel_count = 12
        if hello is not None and hello.channel_count != 12:
            raise DeviceIdentityError("tactile HELLO reports {} channels, expected 12".format(hello.channel_count))
        if status is not None and status.raw.get("channel_count") not in (None, 12):
            raise DeviceIdentityError("tactile STATUS reports an unexpected channel_count")
        adc_status = []
        if status is not None:
            adc_status = [
                {
                    "id": item.index,
                    "state": item.state,
                    "code": item.code,
                    "consecutive_errors": item.consecutive_errors,
                    "total_errors": item.total_errors,
                    "recovered": item.recovered,
                    "last_error": item.last_error,
                }
                for item in status.adc_status
            ]
        return DeviceIdentity(
            device_id=(status.device_id if status is not None else hello.device_id),
            boot_id=(status.boot_id if status is not None else hello.boot_id),
            firmware_version=firmware,
            channel_count=channel_count,
            reference_mode=(status.reference_mode if status is not None else hello.reference_mode),
            streaming=(status.streaming if status is not None else True),
            adc_status=adc_status,
            port=self.port,
            port_info=port_info(self.port),
            hello_seen=hello is not None,
            hello=None if hello is None else hello.raw,
        )

    def request_status(self, timeout_s: float = 3.0) -> StatusMessage:
        request_id = self.send_command("STATUS")
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for item in self.messages(0.05):
                if isinstance(item, StatusMessage) and item.request_id == request_id:
                    return item
            time.sleep(0.005)
        raise SerialTransportError("STATUS request timed out after {:.1f}s".format(timeout_s))

    def request_diag(self, timeout_s: float = 10.0) -> StatusMessage:
        request_id = self.send_command("DIAG")
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for item in self.messages(0.05):
                if isinstance(item, StatusMessage) and item.request_id == request_id and item.diag is not None:
                    return item
                if isinstance(item, ErrorMessage):
                    raise SerialTransportError("DIAG failed: {} {}".format(item.code, item.message))
            time.sleep(0.005)
        raise SerialTransportError("DIAG timed out after {:.1f}s".format(timeout_s))

    def set_streaming(self, enabled: bool, timeout_s: float = 2.0) -> Optional[StatusMessage]:
        request_id = self.send_command("STREAM", value=bool(enabled))
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for item in self.messages(0.05):
                if isinstance(item, StatusMessage) and item.request_id == request_id:
                    return item
            time.sleep(0.005)
        return None
