"""Data source isolation and filesystem mapping.

LIVE data may only be produced by real devices and is stored under
``data/real``.  SIMULATION data is stored under ``data/simulated``.  REPLAY is
read-only and never receives a recording directory.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class DataSource(str, Enum):
    LIVE = "LIVE"
    REPLAY = "REPLAY"
    SIMULATION = "SIMULATION"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value

    @property
    def allows_control(self) -> bool:
        """Whether this source may ever submit a control command."""
        return self is not DataSource.REPLAY

    @property
    def is_real(self) -> bool:
        return self is DataSource.LIVE

    @property
    def label(self) -> str:
        return {
            DataSource.LIVE: "LIVE / 真实设备",
            DataSource.REPLAY: "REPLAY / 只读回放",
            DataSource.SIMULATION: "SIMULATION / 模拟",
        }[self]


def parse_source(value: object) -> DataSource:
    if isinstance(value, DataSource):
        return value
    if not isinstance(value, str):
        raise ValueError("data source must be LIVE, REPLAY or SIMULATION")
    try:
        return DataSource(value.upper())
    except ValueError as exc:
        raise ValueError("data source must be LIVE, REPLAY or SIMULATION") from exc


def trial_parent(root: Path | str, source: DataSource) -> Path:
    """Return the only directory a recording of ``source`` may use.

    REPLAY is read-only, so it has no recording directory.  Callers that try to
    record replay data receive an explicit error instead of a quiet fallback.
    """
    root = Path(root)
    if source is DataSource.LIVE:
        return root / "data" / "real" / "trials"
    if source is DataSource.SIMULATION:
        return root / "data" / "simulated" / "trials"
    raise PermissionError("REPLAY is read-only and cannot create a recording")
