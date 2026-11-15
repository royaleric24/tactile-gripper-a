#!/usr/bin/env python3
"""One-command Mac launcher for the P3-B read-only FSR + PWM live monitor.

What it starts
--------------
1. ``scripts/capture_fsr_live.py``  — owns the FSR serial port, writes
   ``<session>/fsr/fsr_stream.jsonl``.
2. ``tactile_gripper.ui`` (LIVE, log-follow) — tails both JSONL files, records
   one Trial, exports CSV + REPLAY on exit.  It never opens a serial port.
3. ``scripts/pwm_console.py --real`` in *this* terminal — the only PWM writer,
   logging to ``<session>/transport.jsonl``.

So the operator needs one terminal and one command.  The dashboard stays
read-only; PWM is typed into the console exactly as before.

Examples
--------
    .venv/bin/python scripts/run_live_monitor.py
    .venv/bin/python scripts/run_live_monitor.py --fsr-port /dev/cu.usbserial-0001
    .venv/bin/python scripts/run_live_monitor.py --no-console   # watch only
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PWM_PORT = "/dev/cu.usbserial-A5069RR4"
DEFAULT_FSR_PORT = "/dev/cu.usbserial-0001"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_name() -> str:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    return f"session_{stamp}_{uuid.uuid4().hex[:4]}"


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def pick_port(start: int) -> int:
    for candidate in range(start, start + 25):
        if not port_in_use(candidate):
            return candidate
    raise SystemExit(f"no free local port in {start}..{start + 24}")


def wait_http(url: str, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def child_env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = "src:."
    env["PYTHONUNBUFFERED"] = "1"
    return env


def wait_for_fsr_hello(path: Path, timeout_s: float = 12.0) -> bool:
    """Wait until the FSR capture has written a HELLO line."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if '"type":"HELLO"' in line or '"type": "HELLO"' in line:
                        return True
        except OSError:
            pass
        time.sleep(0.25)
    return False


def stop_process(proc: subprocess.Popen | None, *, name: str, interrupt_first: bool) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        if interrupt_first:
            proc.send_signal(signal.SIGINT)  # let the capture send STREAM stop
            proc.wait(timeout=6)
        else:
            proc.terminate()
            proc.wait(timeout=12)
    except subprocess.TimeoutExpired:
        print(f"[launcher] {name} did not stop; killing", flush=True)
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pwm-port", default=DEFAULT_PWM_PORT, help="ESP32-S3 control port (pwm_console)")
    parser.add_argument("--fsr-port", default=DEFAULT_FSR_PORT, help="ESP32 FSR acquisition port")
    parser.add_argument("--session", type=Path, help="explicit session directory (default logs/real/sessions/<utc>)")
    parser.add_argument("--web-port", type=int, default=8080, help="Dashboard port (auto-increments if busy)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true", help="do not open the Dashboard in a browser")
    parser.add_argument("--no-fsr", action="store_true", help="do not start FSR capture (watch console only)")
    parser.add_argument("--no-console", action="store_true", help="do not start pwm_console; watch logs only")
    parser.add_argument("--no-record", action="store_true", help="do not create a Trial automatically")
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT, help="Trial data root")
    parser.add_argument("--fsr-baud", type=int, help="override FSR baud (default from config)")
    args = parser.parse_args()

    if not args.no_fsr and args.fsr_port == args.pwm_port:
        parser.error("--fsr-port and --pwm-port must differ (two independent devices)")

    session = args.session or (PROJECT_ROOT / "logs" / "real" / "sessions" / session_name())
    session = session.resolve()
    session.mkdir(parents=True, exist_ok=True)
    fsr_dir = session / "fsr"
    fsr_dir.mkdir(parents=True, exist_ok=True)
    fsr_stream = fsr_dir / "fsr_stream.jsonl"
    if fsr_stream.exists() and not args.no_fsr:
        raise SystemExit(f"FSR stream already exists; choose a new --session: {fsr_stream}")
    if (session / "transport.jsonl").exists() and not args.no_console:
        raise SystemExit(f"transport.jsonl already exists; choose a new --session: {session / 'transport.jsonl'}")

    web_port = pick_port(args.web_port)
    metadata = {
        "session": str(session),
        "started_utc": utc_now(),
        "pwm_port": args.pwm_port,
        "fsr_port": None if args.no_fsr else args.fsr_port,
        "fsr_baud": args.fsr_baud,
        "dashboard_url": f"http://{args.host}:{web_port}",
        "dashboard_read_only": True,
        "pwm_writer": "scripts/pwm_console.py",
        "fsr_writer": "scripts/capture_fsr_live.py",
        "record_trial": not args.no_record,
    }
    (session / "session.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")

    fsr_proc = None
    dashboard_proc = None
    console_proc = None
    try:
        if not args.no_fsr:
            fsr_cmd = [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "capture_fsr_live.py"),
                "--port",
                args.fsr_port,
                "--authorize",
                "--output",
                str(fsr_stream),
                "--label",
                session.name,
            ]
            if args.fsr_baud:
                fsr_cmd.extend(["--baud", str(args.fsr_baud)])
            fsr_log = (session / "fsr_capture.log").open("w", encoding="utf-8")
            fsr_proc = subprocess.Popen(
                fsr_cmd,
                cwd=PROJECT_ROOT,
                env=child_env(),
                stdout=fsr_log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            print(f"[launcher] FSR capture started (pid {fsr_proc.pid}) -> {fsr_stream}", flush=True)
            if wait_for_fsr_hello(fsr_stream):
                print("[launcher] FSR HELLO 已收到，启动 Dashboard。", flush=True)
            else:
                print(
                    "[launcher] 警告：12s 内未见 FSR HELLO；Dashboard 仍会启动，"
                    "传感器可能显示等待/离线，请查看 fsr_capture.log。",
                    flush=True,
                )

        dash_cmd = [
            sys.executable,
            "-m",
            "tactile_gripper.ui",
            "--source",
            "LIVE",
            "--follow-session",
            str(session),
            "--data-root",
            str(args.data_root),
            "--host",
            args.host,
            "--port",
            str(web_port),
        ]
        if not args.no_record:
            dash_cmd.append("--follow-record")
        if args.no_browser:
            dash_cmd.append("--no-browser")
        dash_log_path = session / "dashboard.log"
        dash_log = dash_log_path.open("w", encoding="utf-8")
        dashboard_proc = subprocess.Popen(
            dash_cmd,
            cwd=PROJECT_ROOT,
            env=child_env(),
            stdout=dash_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        url = f"http://{args.host}:{web_port}/"
        if not wait_http(url, 40):
            stop_process(dashboard_proc, name="dashboard", interrupt_first=False)
            tail = dash_log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            raise SystemExit(f"Dashboard did not start. Log tail:\n{tail}")
        print(f"[launcher] Dashboard: {url}", flush=True)
        print(f"[launcher] Session:   {session}", flush=True)

        if args.no_console:
            if not sys.stdin.isatty():
                raise SystemExit("--no-console 需要可交互终端；请直接 Ctrl+C 结束")
            print("[launcher] --no-console：Ctrl+C 结束会话。", flush=True)
            try:
                while dashboard_proc.poll() is None:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                print("\n[launcher] 结束会话…", flush=True)
        else:
            print(
                "[launcher] Dashboard 只读；下面进入 PWM 控制台，输入 500..2500 / status / stop / quit。"
                " 打开网页不会发送任何 PWM。",
                flush=True,
            )
            if not sys.stdin.isatty():
                raise SystemExit(
                    "pwm_console 需要交互式终端（REAL）。请在 Terminal 运行，或加 --no-console 只观察。"
                )
            console_cmd = [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "pwm_console.py"),
                "--real",
                "--port",
                args.pwm_port,
                "--target",
                "s3",
                "--authorize",
                "--log-dir",
                str(session),
            ]
            console_proc = subprocess.Popen(console_cmd, cwd=PROJECT_ROOT, env=child_env())
            try:
                console_proc.wait()
            except KeyboardInterrupt:
                console_proc.wait(timeout=30)
    finally:
        stop_process(console_proc, name="pwm_console", interrupt_first=False)
        stop_process(dashboard_proc, name="dashboard", interrupt_first=False)
        stop_process(fsr_proc, name="fsr_capture", interrupt_first=True)
        stopped = utc_now()
        try:
            payload = json.loads((session / "session.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        payload["finished_utc"] = stopped
        (session / "session.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        print(f"\n[launcher] 会话结束：{session}", flush=True)
        print(f"[launcher] Dashboard 日志：{session / 'dashboard.log'}", flush=True)
        trials = sorted(
            (Path(args.data_root) / "data" / "real" / "trials").glob("*/frames.csv"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if trials:
            print(f"[launcher] 最新 CSV：{trials[0]}", flush=True)
        else:
            print("[launcher] 未找到 Trial CSV（可能未启用 --follow-record 或没有帧）。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
