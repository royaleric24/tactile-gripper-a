#!/usr/bin/env python3
"""Launch offline NiceGUI, audit its rendered pages in Chrome, and verify Trial artifacts."""

import argparse
import csv
import json
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "fsr1": (1, 1, ("原始 ADC 762601", "FSR_A")),
    "fsr1-adc4-fault": (0, 1, ("ADC4", "全部缺失", "FSR_A")),
    "electrodes12-fsr1": (1, 13, ("12 路无效", "PENDING_REAL_WIRING", "FSR_A", "原始 ADC 2287802")),
    "electrodes12-fsr1-adc4-fault": (0, 13, ("ADC4", "全部缺失", "PENDING_REAL_WIRING", "FSR_A")),
    "fsr": (2, 2, ("原始 ADC 762601", "原始 ADC 889701")),
    "fsr-adc4-fault": (0, 2, ("ADC4", "全部缺失")),
    "electrodes12": (12, 12, ("R1–R6 / C1–C6", "SIM_SYNTHETIC_MAPPING")),
    "electrodes12-partial": (8, 12, ("4 路无效", "ADC1")),
    "electrodes12-fsr2": (2, 14, ("12 路无效", "PENDING_REAL_WIRING", "FSR_A", "FSR_B")),
    "electrodes12-fsr2-adc4-fault": (0, 14, ("ADC4", "全部缺失", "PENDING_REAL_WIRING")),
}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def dashboard(out, args):
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "PYTHONPATH": "src:."}
    cmd = [sys.executable, "-m", "tactile_gripper.ui", "--no-browser",
           "--host", "127.0.0.1", "--port", str(port), "--data-root", str(out), *args]
    out.mkdir(parents=True)
    with (out / "server.log").open("w") as log:
        log.write("$ " + " ".join(cmd) + "\n")
        log.flush()
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline and proc.poll() is None:
                try:
                    with urlopen(base, timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError(f"Dashboard failed to start: {out / 'server.log'}")
            yield base
        finally:
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def audit(base, out, label, pages, viewports, markers):
    env = {**os.environ, "AUDIT_BASE": base, "OUT_DIR": str(out / "browser"),
           "LABEL": label, "PAGES": pages, "VIEWPORTS": viewports, "DEBUG_PORT": str(free_port()),
           "EXERCISE_TRIAL": "1" if "analysis" in pages else "0"}
    with (out / "browser.log").open("w") as log:
        log.write(f"$ LABEL={label} PAGES={pages} VIEWPORTS={viewports} node scripts/ui_screenshot_audit.mjs\n")
        log.flush()
        subprocess.run(["node", "scripts/ui_screenshot_audit.mjs"], cwd=ROOT, env=env, stdout=log,
                       stderr=subprocess.STDOUT, timeout=100, check=True)
    report = json.loads((out / "browser" / f"{label}-audit.json").read_text())
    for entry in report["viewports"]:
        if entry["consoleErrors"]:
            raise RuntimeError(f"{label} {entry['page']}: {entry['consoleErrors']}")
        if entry["metrics"]["bodyScrollWidth"] > entry["width"]:
            raise RuntimeError(f"{label} {entry['page']}: page overflows viewport horizontally")
        if str(out) in entry["text"] or str(ROOT) in entry["text"]:
            raise RuntimeError(f"{label} {entry['page']}: rendered page exposes a host path")
        if entry["page"] == "live":
            for marker in markers:
                if marker not in entry["text"]:
                    raise RuntimeError(f"{label}: rendered page did not show {marker!r}")
            if "传感器数据正常" in entry["text"] or "HISTORICAL" in entry["text"]:
                raise RuntimeError(f"{label}: current frame mislabelled")
            if "fsr1" in label and "FSR_B" in entry["text"]:
                raise RuntimeError(f"{label}: current FSR frame displayed FSR_B")
        elif entry["page"] == "analysis":
            expected = ("触觉帧检查", "只读回放", "CSV 已导出")
            if label == "fsr-adc4-fault":
                expected += ("第 2/2 帧", "0/2 有效")
            if label == "fsr1-adc4-fault":
                expected += ("第 2/2 帧", "0/1 有效")
            if any(marker not in entry["text"] for marker in expected):
                raise RuntimeError(f"{label}: Trial loading, frame step or CSV export not visible")
        elif entry["page"] == "demo-6x6":
            if any(marker not in entry["text"] for marker in markers) or "提交 PWM" in entry["text"]:
                raise RuntimeError(f"{label}: synthetic preview isolation or next-frame interaction failed")
    return len(report["viewports"])


def scenario(case, root):
    valid, count, markers = CASES[case]
    out = root / case
    full = case in ("fsr-adc4-fault", "electrodes12-fsr2", "fsr1-adc4-fault", "electrodes12-fsr1")
    with dashboard(out, ["--firmware-fixture", case, "--record-fixture"]) as base:
        pages = audit(base, out, case, "live,experiments,analysis" if full else "live",
                      "1440x900,1280x800" if full else "1440x900",
                      (f"{valid}/{count} 有效", "离线固件帧已读完", "AUTO_REAL_ENABLED=False", *markers))
    [trial] = list((out / "data" / "simulated" / "trials").iterdir())
    with (trial / "frames.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    last = rows[-1]
    if (int(last["valid_count"]), int(last["channel_count"]), last["source"]) != (valid, count, "SIMULATION"):
        raise RuntimeError(f"{case}: Trial CSV counts or provenance incorrect")
    for index in range(count):
        if (last[f"ch_{index}"] == "") != (last[f"valid_{index}"] == "false"):
            raise RuntimeError(f"{case}: Trial CSV used a value for an invalid channel")
    if (out / "data" / "real").exists() or "Traceback" in (out / "server.log").read_text():
        raise RuntimeError(f"{case}: unexpected real Trial data or server exception")
    return {"scenario": case, "valid": valid, "channels": count, "trial_frames": len(rows),
            "viewports": pages, "replay": str((trial / "replay.jsonl").relative_to(root))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new directory for screenshots, logs and Trial data")
    root = parser.parse_args().out.resolve()
    root.mkdir(parents=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda key: scenario(key, root), CASES))
    replay_views = 0
    for case, quality in (("electrodes12-fsr1", "1/13 有效"), ("electrodes12-fsr2", "2/14 有效")):
        path = root / next(result["replay"] for result in results if result["scenario"] == case)
        label = f"replay-{case}"
        replay = root / label
        with dashboard(replay, ["--source", "REPLAY", "--sensor-file", str(path)]) as base:
            replay_views += audit(base, replay, label, "live", "1440x900",
                                  ("只读回放", quality, "PENDING_REAL_WIRING", "只读回放 · 已禁用"))
            try:
                with urlopen(base + "/demo-6x6", timeout=3):
                    raise RuntimeError("6×6 synthetic preview is exposed in REPLAY")
            except HTTPError as exc:
                if exc.code != 404:
                    raise
        if (replay / "data" / "real").exists() or (replay / "data" / "simulated").exists():
            raise RuntimeError("read-only replay wrote Trial data")
    preview = root / "demo-6x6"
    with dashboard(preview, []) as base:
        preview_views = audit(base, preview, "demo-6x6", "demo-6x6", "1440x900,1280x800",
                              ("SIMULATION ONLY", "帧 2", "36/36 格有值", "合成格值"))
    if (preview / "data" / "real").exists() or (preview / "data" / "simulated").exists():
        raise RuntimeError("standalone synthetic preview wrote Trial data")
    report = {"result": "PASS", "evidence": "OFFLINE_VERIFIED",
              "scenarios": results, "replay_viewports": replay_views, "preview_viewports": preview_views}
    (root / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
