"""CLI for recording/analyzing the 6x6 matrix prototype."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .acquire import MatrixRecorder, default_run_directory, record_session
from .analysis import baseline_from_frames, summarize_frames
from .model import load_config
from .protocol import parse_matrix_line

ROOT = Path(__file__).resolve().parents[2]


def load_frames(path: Path):
    frames = []
    errors = 0
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                frames.append(parse_matrix_line(line))
            except Exception:
                errors += 1
    return frames, errors


def command_run(args) -> int:
    from tools.tactile_acq.transport import SerialSession, SerialTransportError

    config = load_config(Path(args.config) if args.config else None)
    session = SerialSession(args.port, baud=args.baud)
    try:
        session.open()
    except SerialTransportError as exc:
        print("RUN FAILED: {}".format(exc), file=sys.stderr)
        return 2
    run_dir = Path(args.out) if args.out else default_run_directory(args.port)
    recorder = MatrixRecorder(run_dir, args.port, args.baud, config)
    print("recording MATRIX_FRAME to {}".format(run_dir))
    try:
        run = record_session(session, args.duration, recorder)
    finally:
        session.close()
    print(json.dumps(run, indent=2))
    if run["frames"] == 0:
        print("WARNING: no MATRIX_FRAME received", file=sys.stderr)
    return 0


def command_analyze(args) -> int:
    path = Path(args.path)
    raw = path / "raw_frames.jsonl" if path.is_dir() else path
    if not raw.is_file():
        print("no raw_frames.jsonl in {}".format(path), file=sys.stderr)
        return 2
    frames, errors = load_frames(raw)
    if not frames:
        print("no valid frames ({} parse errors)".format(errors), file=sys.stderr)
        return 2
    summary = summarize_frames(frames)
    baseline = baseline_from_frames(frames)
    result = {
        "path": str(raw),
        "parse_errors": errors,
        "summary": summary,
        "baseline_mean": list(baseline.mean),
        "baseline_std": list(baseline.std),
    }
    print(json.dumps(result, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    config = load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="record MATRIX_FRAME from the old ESP32")
    p_run.add_argument("--port", required=True)
    p_run.add_argument("--baud", type=int, default=int(config.get("serial_baud", 921600)))
    p_run.add_argument("--duration", type=float, default=60.0)
    p_run.add_argument("--out")
    p_run.add_argument("--config")
    p_run.set_defaults(func=command_run)

    p_analyze = sub.add_parser("analyze", help="summarize a raw_frames.jsonl or run directory")
    p_analyze.add_argument("path")
    p_analyze.set_defaults(func=command_analyze)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
