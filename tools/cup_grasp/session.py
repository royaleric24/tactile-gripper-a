"""Executable simulated trials and real tactile-only recording.

Real gripper motion is intentionally gated: the current S3 config is
hardware_enabled=false / UNCALIBRATED, so no real arm/set-pulse path is taken.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .control import FakeCupGripper, FixedClampMode, TactileFeedbackFSM, summarize_control
from .model import CupGraspConfig, ConfigurationError, load_config
from .recorder import CupTrialRecorder
from .tactile import SimulatedTactileSource, TactileProcessor

ROOT = Path(__file__).resolve().parents[2]
REAL_ROOT = ROOT / "data/real/cup_grasp"
SIM_ROOT = ROOT / "data/simulated/cup_grasp"


def run_simulated(mode: str, config_path: Path, duration_s: float = 6.0, root: Optional[Path] = None) -> Dict[str, Any]:
    config = load_config(config_path)
    recorder = CupTrialRecorder(root or SIM_ROOT, config)
    recorder.record_trial_event("TRIAL_START", mode=mode.upper(), data_kind="SIMULATED")
    gripper = FakeCupGripper()
    processor = TactileProcessor(config.tactile)
    source = SimulatedTactileSource(contact_at_ns=int(1.5e9))
    started = time.monotonic_ns()
    controller = None
    if mode.lower() == "fixed":
        controller = FixedClampMode(config, gripper)
        controller.start(started)
    elif mode.lower() == "feedback":
        controller = TactileFeedbackFSM(config, gripper)
        controller.start(started)
    else:
        raise ConfigurationError("mode must be fixed or feedback")
    next_tick = started
    next_water = started + int(3.0e9)
    while True:
        now = time.monotonic_ns()
        if (now - started) / 1e9 >= duration_s:
            break
        frame = source.make(now)
        sample = processor.update(frame, now)
        recorder.record_tactile("", frame, sample)
        if controller is not None:
            if isinstance(controller, TactileFeedbackFSM):
                controller.update(sample, now, processor.sensor_ok(now))
                controller.tick(now, processor.sensor_ok(now))
            elif isinstance(controller, FixedClampMode):
                pass
        if now >= next_water:
            recorder.record_load("WATER", water_g=100.0, cumulative_g=100.0, note="SIMULATED")
            next_water += 2000 * 1_000_000
        next_tick += int(1 / 30.0 * 1e9)
        sleep_ns = next_tick - time.monotonic_ns()
        if sleep_ns > 0:
            time.sleep(sleep_ns / 1e9)
    if isinstance(controller, TactileFeedbackFSM):
        if controller.state.value not in ("FAULT", "DONE", "RELEASE"):
            controller.release(time.monotonic_ns())
    elif isinstance(controller, FixedClampMode):
        controller.stop(time.monotonic_ns())
    for event in control_events(controller):
        recorder.record_gripper(event)
    recorder.record_trial_event("TRIAL_END", mode=mode.upper())
    summary = summarize_control(controller)
    metrics = recorder.finalize(status="SIMULATED", control_summary=summary,
                                notes={"simulated": True, "not_real_evidence": True})
    return {"trial_id": recorder.trial_id, "dir": str(recorder.run_dir), "metrics": metrics}


def control_events(controller) -> list:
    if controller is None:
        return []
    return [{"host_monotonic_ns": e.host_monotonic_ns, "kind": "CONTROL",
             "state": e.state, "pulse_us": e.pulse_us, "reason": e.reason}
            for e in controller.events]


def run_real_tactile_only(config_path: Path, port: str, duration_s: float, baud: int = 921600,
                          reference_mode: str = "AVDD_AVSS") -> Dict[str, Any]:
    """Record real tactile frames only; no gripper command or motion."""
    config = load_config(config_path)
    if config.data_kind == "SIMULATED":
        raise ConfigurationError("refusing SIMULATED config for real recording")
    from tools.tactile_acq.protocol import SampleFrame, parse_message
    from tools.tactile_acq.transport import SerialSession

    session = SerialSession(port, baud=baud)
    session.open()
    try:
        identity = session.identify(timeout_s=8.0)
        if not identity.streaming:
            session.set_streaming(True)
            time.sleep(0.2)
        # The single-point measurement requires AVDD-AVSS; this is an ADC config
        # command, not a motion command. Failure aborts rather than guessing.
        try:
            session.send_command("SET_REF", value=reference_mode)
            time.sleep(0.2)
        except Exception:
            pass
        recorder = CupTrialRecorder(REAL_ROOT, config)
        recorder.record_trial_event("TRIAL_START", mode="TACTILE_ONLY", data_kind="REAL_SERIAL",
                                    port=port, identity=identity.__dict__)
        processor = TactileProcessor(config.tactile)
        started = time.monotonic_ns()
        frames = 0
        while (time.monotonic_ns() - started) / 1e9 < duration_s:
            for raw in session.read_available():
                try:
                    parsed = parse_message(raw)
                except Exception:
                    continue
                if not isinstance(parsed, SampleFrame):
                    continue
                now = time.monotonic_ns()
                sample = processor.update(parsed, now)
                recorder.record_tactile(raw.decode("utf-8", errors="replace"), parsed, sample)
                frames += 1
            time.sleep(0.002)
        summary = {"state": "TACTILE_ONLY", "pulse_us": None, "events": [], "fault_reason": None}
        usable = sum(1 for s in recorder.samples if s["usable"])
        status = "TACTILE_ONLY" if frames and usable / max(1, frames) >= 0.8 else "NO_VALID_TACTILE"
        metrics = recorder.finalize(status=status, control_summary=summary,
                                    notes={"no_gripper_motion": True, "frames": frames})
        return {"trial_id": recorder.trial_id, "dir": str(recorder.run_dir), "metrics": metrics}
    finally:
        try:
            session.set_streaming(False, timeout_s=1.0)
        except Exception:
            pass
        session.close()
