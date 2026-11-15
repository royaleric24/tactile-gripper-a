"""JSON Lines protocol for the offline 6x6 matrix prototype."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from tools.tactile_acq.protocol import decode_line

from .model import MatrixFrame, build_frame, validate_frame

MESSAGE_TYPE = "MATRIX_FRAME"


def parse_matrix_line(raw: Any) -> MatrixFrame:
    message = decode_line(raw)
    return validate_frame(message)


def encode_matrix_frame(
    frame_seq: int,
    timestamp_us: int,
    cells,
    valid,
    flags,
    frame_period_us: Optional[int] = None,
    reference_mode: str = "AVDD_AVSS",
) -> bytes:
    message = build_frame(
        frame_seq=frame_seq,
        timestamp_us=timestamp_us,
        cells=cells,
        valid=valid,
        flags=flags,
        frame_period_us=frame_period_us,
        reference_mode=reference_mode,
    )
    return (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")


def frame_to_dict(frame: MatrixFrame) -> Dict[str, Any]:
    return dict(frame.raw)
