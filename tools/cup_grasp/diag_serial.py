"""Framing and strict parsing for the fixed-AIN1 diagnostic serial protocol."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

MAX_LINE_BYTES = 4096
VALID_REG0 = 0x91
VALID_REG2 = 0xC0
VALID_REG3 = 0x02


class DiagProtocolError(ValueError):
    pass


def _regs(value, name):
    if not isinstance(value, list) or len(value) != 4 or any(type(x) is not int for x in value):
        raise DiagProtocolError("{} must be four integers".format(name))
    return value


def parse_diag_line(line: bytes) -> Tuple[str, Dict[str, Any]]:
    """Parse exactly one complete JSON line; reject garbage/extra data."""
    if not line or b"\x00" in line:
        raise DiagProtocolError("empty or NUL line")
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DiagProtocolError("non-UTF8 line") from exc
    try:
        item = json.loads(text)
    except ValueError as exc:
        raise DiagProtocolError("invalid JSON") from exc
    if not isinstance(item, dict):
        raise DiagProtocolError("JSON is not an object")
    kind = item.get("type")
    if kind == "DIAG_HELLO":
        if not isinstance(item.get("firmware"), str):
            raise DiagProtocolError("HELLO missing firmware")
        for key in ("adc2_regs",):
            regs = _regs(item.get(key), key)
            if regs[0] != VALID_REG0 or regs[2] != VALID_REG2 or regs[3] != VALID_REG3:
                raise DiagProtocolError("HELLO {} not fixed AIN1/AVDD/DRDYM".format(key))
        if item.get("fixed_reg0") != VALID_REG0 or item.get("fixed_reg2") != VALID_REG2 or item.get("fixed_reg3") != VALID_REG3:
            raise DiagProtocolError("HELLO fixed config mismatch")
        return kind, item
    if kind == "DIAG_SAMPLE":
        before = _regs(item.get("before"), "before")
        after = _regs(item.get("after"), "after")
        for name, regs in (("before", before), ("after", after)):
            if regs[0] != VALID_REG0 or regs[2] != VALID_REG2 or regs[3] != VALID_REG3:
                raise DiagProtocolError("{} register set is not 0x91/0x80/0xC0/0x02".format(name))
        if item.get("mux_before") != 9 or item.get("mux_after") != 9:
            raise DiagProtocolError("MUX did not remain AIN1")
        if item.get("vref_before") != 3 or item.get("vref_after") != 3:
            raise DiagProtocolError("VREF did not remain AVDD")
        if item.get("reg3_before") != VALID_REG3 or item.get("reg3_after") != VALID_REG3:
            raise DiagProtocolError("DRDYM did not remain enabled")
        if item.get("extra_clocks") != 8:
            raise DiagProtocolError("extra_clocks must be 8")
        raw = item.get("raw")
        if raw is not None and (not isinstance(raw, str) or len(raw) != 6):
            raise DiagProtocolError("raw must be 6 hex chars or null")
        if item.get("read_ok") is True:
            if not isinstance(item.get("counts"), int):
                raise DiagProtocolError("read_ok sample missing integer counts")
        return kind, item
    raise DiagProtocolError("unknown type {!r}".format(kind))


class LineFramer:
    """Newline framer that survives boot garbage, partial lines and oversize lines."""
    def __init__(self, max_line_bytes: int = MAX_LINE_BYTES):
        self.buffer = bytearray()
        self.max_line_bytes = max_line_bytes
        self.dropped_bytes = 0
        self.overflow_events = 0

    def feed(self, chunk: bytes) -> List[bytes]:
        self.buffer.extend(chunk)
        lines = []
        while True:
            idx = self.buffer.find(b"\n")
            if idx < 0:
                break
            line = bytes(self.buffer[:idx])
            del self.buffer[: idx + 1]
            if line.endswith(b"\r"):
                line = line[:-1]
            if line:
                lines.append(line)
        if len(self.buffer) > self.max_line_bytes:
            # Boot noise without a newline: discard it rather than concatenating
            # it with the next valid JSON line.
            self.dropped_bytes += len(self.buffer)
            self.overflow_events += 1
            self.buffer.clear()
        return lines
