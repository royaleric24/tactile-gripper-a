"""SIMULATED-only finite-step logic; target units are arbitrary, not degrees."""
from .gripper_controller import FakeGripper
from .sensor import validate, number

class ClosedLoop:
    def __init__(self, gripper, config):
        if type(gripper) is not FakeGripper or config.get("run_kind") != "SIMULATED":
            raise ValueError("simulation_only")
        keys = ("min_target", "max_target", "initial_target", "step", "max_cumulative", "timeout_ms", "min_interval_ms", "contact_threshold")
        if not all(number(config.get(k)) for k in keys): raise ValueError("config")
        if not config["min_target"] <= config["initial_target"] <= config["max_target"]: raise ValueError("range")
        if any(config[k] <= 0 for k in ("step", "max_cumulative", "timeout_ms", "min_interval_ms")): raise ValueError("positive_limits")
        if not config.get("qualities"): raise ValueError("qualities")
        self.g, self.c = gripper, dict(config)
        self.state, self.target = "DISARMED", config["initial_target"]
        self.last_id, self.last_sensor_stamp = -1, -1
        self.last_receive = self.last_step = self.last_now = None
        self.total = 0
        self.events = []
    def transition(self, state, reason):
        self.events.append(dict(run_kind="SIMULATED", before=self.state, after=state, reason=reason))
        self.state = state
    def stop(self, reason="manual", state="STOPPED"):
        self.g.inhibit_closing(reason)
        self.transition(state, reason)
    def start(self, now):
        if self.state != "DISARMED" or not number(now): raise ValueError("start")
        self.last_receive = self.last_now = now
        self.transition("READY", "explicit_simulation_start")
    def tick(self, now):
        if self.state not in ("READY", "CLOSING_STEP"): return
        if not number(now) or now < self.last_now:
            self.stop("clock", "FAULT"); return
        self.last_now = now
        if now - self.last_receive >= self.c["timeout_ms"]: self.stop("sensor_timeout", "FAULT")
    def on_frame(self, frame, now):
        self.tick(now)
        if self.state not in ("READY", "CLOSING_STEP"): return
        try:
            validate(frame, self.c["qualities"])
            if frame["frame_id"] <= self.last_id or frame["timestamp_ms"] < self.last_sensor_stamp: raise ValueError("replayed_or_out_of_order")
        except ValueError as exc:
            self.stop(str(exc), "FAULT"); return
        self.last_id, self.last_sensor_stamp = frame["frame_id"], frame["timestamp_ms"]
        self.last_receive = now
        if frame["contact_score"] >= self.c["contact_threshold"]:
            self.stop("contact", "CONTACT_STOP"); return
        if self.last_step is not None and now - self.last_step < self.c["min_interval_ms"]: return
        target = self.target + self.c["step"]
        if target > self.c["max_target"] or self.total + self.c["step"] > self.c["max_cumulative"]:
            self.stop("limit", "FAULT"); return
        self.g.set_target(target)
        self.target, self.last_step = target, now
        self.total += self.c["step"]
        self.transition("CLOSING_STEP", "fresh_frame")
    def release(self, authorized=False):
        if not authorized or self.state != "CONTACT_STOP": raise ValueError("release_not_authorized")
        self.g.release()
        self.transition("RELEASE_REQUESTED", "explicit_simulated_release")
