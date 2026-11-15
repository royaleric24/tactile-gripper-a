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


def wait_for_fsr_hello(
    path: Path,
    *,
    timeout_s: float = 15.0,
    process: subprocess.Popen | None = None,
) -> tuple[bool, str]:
    """Wait for the FSR capture HELLO.

    Returns ``(ready, reason)``.  ``ready`` is False when the HELLO is missing
    before the timeout **or** the capture process exits first; the caller must
    then abort without starting the PWM console.  A short grace after HELLO
    catches a capture that wrote the handshake and died immediately.
    """
    deadline = time.monotonic() + max(0.1, timeout_s)
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return False, f"fsr_exited:{process.returncode}"
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if '"type":"HELLO"' in line or '"type": "HELLO"' in line:
                        time.sleep(0.3)
                        if process is not None and process.poll() is not None:
                            return False, f"fsr_exited:{process.returncode}"
                        return True, "hello"
        except OSError:
            pass
        time.sleep(0.25)
    return False, "hello_timeout"


def read_trial_artifacts(session: Path) -> dict | None:
    """Read this session's Trial sidecar written by the Dashboard.

    Never falls back to a global "newest CSV": that could print a different
    session's recording.
    """
    try:
        payload = json.loads((session / "trial.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def update_session_metadata(session: Path, **fields) -> None:
    """Merge lifecycle fields into this session's metadata sidecar."""
    try:
        payload = json.loads((session / "session.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    payload.update(fields)
    (session / "session.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def wait_after_console_failure(
    dashboard_proc: subprocess.Popen,
    fsr_proc: subprocess.Popen | None,
    *,
    fsr_enabled: bool,
    sleeper=time.sleep,
) -> str:
    """Keep passive monitoring alive until the operator ends it.

    The S3 console is intentionally not restarted and no command is replayed.
    FSR and Dashboard remain independent; if FSR later exits, the Dashboard
    stays up and reports stale data until the operator presses Ctrl+C.
    """
    print(
        "[launcher] PWM Console 通信故障：已禁止新的 PWM 命令；不会自动重连或重发。",
        flush=True,
    )
    print(
        "[launcher] FSR 采集与 Dashboard 将继续运行。检查/记录完成后按 Ctrl+C 结束整个监控。",
        flush=True,
    )
    fsr_warned = False
    try:
        while dashboard_proc.poll() is None:
            if (
                fsr_enabled
                and fsr_proc is not None
                and not fsr_warned
                and fsr_proc.poll() is not None
            ):
                print(
                    f"[launcher] 警告：FSR 采集也已退出（code {fsr_proc.returncode}）；"
                    "Dashboard 保持运行并显示 STALE，按 Ctrl+C 结束。",
                    flush=True,
                )
                fsr_warned = True
            sleeper(0.5)
    except KeyboardInterrupt:
        print("\n[launcher] 操作者结束故障后监控…", flush=True)
        return "operator_interrupt"
    return "dashboard_exit"


def stop_process(
    proc: subprocess.Popen | None,
    *,
    name: str,
    interrupt_first: bool,
    timeout: float | None = None,
) -> None:
    if proc is None or proc.poll() is not None:
        return
    wait_s = timeout if timeout is not None else (6.0 if interrupt_first else 12.0)
    try:
        if interrupt_first:
            proc.send_signal(signal.SIGINT)  # let the capture send STREAM stop
            proc.wait(timeout=wait_s)
        else:
            proc.terminate()
            proc.wait(timeout=wait_s)
    except subprocess.TimeoutExpired:
        print(f"[launcher] {name} did not stop; killing", flush=True)
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def main() -> int:
    def _terminate(signum, _frame):
        # Convert SIGTERM into SystemExit so the finally block still stops the
        # collectors, lets the Dashboard drain/export, and writes session.json.
        raise SystemExit(128 + signum)

    try:
        signal.signal(signal.SIGTERM, _terminate)
    except (ValueError, OSError):  # not in the main thread (tests)
        pass

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
    parser.add_argument(
        "--fsr-timeout",
        type=float,
        default=15.0,
        help="seconds to wait for the FSR HELLO; on failure the console is NOT started",
    )
    args = parser.parse_args()

    if not args.no_fsr and args.fsr_port == args.pwm_port:
        parser.error("--fsr-port and --pwm-port must differ (two independent devices)")
    if not args.no_console and not sys.stdin.isatty():
        parser.error("pwm_console 需要交互式终端；请在 Terminal 运行，或加 --no-console 只观察")

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
    abort_reason = None
    console_exit_code = None
    console_exit_status = "NOT_STARTED"
    continued_after_console_error = False
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
            try:
                ready, reason = wait_for_fsr_hello(
                    fsr_stream,
                    timeout_s=args.fsr_timeout,
                    process=fsr_proc,
                )
            except KeyboardInterrupt:
                abort_reason = "interrupted"
                print("[launcher] 用户中断：未启动 Dashboard 或 PWM Console。", flush=True)
                raise SystemExit(130)
            if not ready:
                abort_reason = reason
                print(
                    f"[launcher] 停止：FSR 未就绪（{reason}）。"
                    "不会启动 Dashboard，也不会启动 PWM Console。",
                    flush=True,
                )
                try:
                    tail = (session / "fsr_capture.log").read_text(encoding="utf-8", errors="replace")[-1500:]
                except OSError:
                    tail = ""
                if tail:
                    print(f"[launcher] fsr_capture.log 末尾：\n{tail}", flush=True)
                raise SystemExit(3)
            print("[launcher] FSR HELLO 已收到，启动 Dashboard。", flush=True)

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
            # Keep the Dashboard out of the terminal's Ctrl+C process group so
            # it survives until the FSR capture has flushed and the launcher
            # can stop it *after* the writers (drain-before-export order).
            start_new_session=True,
        )
        url = f"http://{args.host}:{web_port}/"
        if not wait_http(url, 40):
            stop_process(dashboard_proc, name="dashboard", interrupt_first=False)
            tail = dash_log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            raise SystemExit(f"Dashboard did not start. Log tail:\n{tail}")
        print(f"[launcher] Dashboard: {url}", flush=True)
        print(f"[launcher] Session:   {session}", flush=True)

        # Re-check the capture after the Dashboard startup delay: a process
        # that died between HELLO and this point must not lead to a PWM console
        # session with no FSR data.
        if not args.no_fsr and fsr_proc.poll() is not None:
            abort_reason = f"fsr_exited:{fsr_proc.returncode}"
            print(
                f"[launcher] 停止：FSR 采集在启动 PWM Console 前退出"
                f"（{abort_reason}）。不会启动 PWM Console。",
                flush=True,
            )
            raise SystemExit(3)

        if args.no_console:
            print(
                "[launcher] --no-console：Ctrl+C 或 SIGTERM 结束会话；"
                "结束后仍会 drain 并导出本会话 Trial。",
                flush=True,
            )
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
            fsr_warned = False
            try:
                while console_proc.poll() is None:
                    if (
                        not args.no_fsr
                        and not fsr_warned
                        and fsr_proc.poll() is not None
                    ):
                        print(
                            f"[launcher] 警告：FSR 采集已退出"
                            f"（code {fsr_proc.returncode}）；Dashboard 将显示 STALE。"
                            " PWM Console 不会自动停止，请手动 stop/quit。",
                            flush=True,
                        )
                        fsr_warned = True
                    time.sleep(0.5)
            except KeyboardInterrupt:
                console_proc.wait(timeout=30)
            console_exit_code = console_proc.poll()
            console_exit_status = (
                "NORMAL" if console_exit_code == 0 else "COMMUNICATION_ERROR"
            )
            update_session_metadata(
                session,
                console_exit_code=console_exit_code,
                console_exit_status=console_exit_status,
                console_finished_utc=utc_now(),
            )
            if console_exit_code != 0:
                continued_after_console_error = True
                update_session_metadata(
                    session,
                    monitor_continued_after_console_error=True,
                )
                wait_after_console_failure(
                    dashboard_proc,
                    fsr_proc,
                    fsr_enabled=not args.no_fsr,
                )
    finally:
        # Stop the writers first so the Dashboard can read their last flushed
        # JSONL lines before it stops the Trial.  Reversing this order drops
        # trailing frames/ACKs from CSV and REPLAY.
        stop_process(console_proc, name="pwm_console", interrupt_first=False, timeout=15)
        stop_process(fsr_proc, name="fsr_capture", interrupt_first=True, timeout=10)
        time.sleep(0.3)
        stop_process(dashboard_proc, name="dashboard", interrupt_first=False, timeout=30)
        stopped = utc_now()
        fields = {
            "finished_utc": stopped,
            "console_exit_code": console_exit_code,
            "console_exit_status": console_exit_status,
            "monitor_continued_after_console_error": continued_after_console_error,
        }
        if abort_reason:
            fields["aborted"] = abort_reason
        update_session_metadata(session, **fields)
        print(f"\n[launcher] 会话结束：{session}", flush=True)
        print(f"[launcher] Dashboard 日志：{session / 'dashboard.log'}", flush=True)
        if abort_reason:
            print("[launcher] 本次未生成 Trial：FSR 未就绪，Dashboard 未启动。", flush=True)
        elif args.no_record:
            print("[launcher] 未启用 Trial 记录（--no-record）。", flush=True)
        else:
            artifacts = read_trial_artifacts(session)
            if artifacts and artifacts.get("csv"):
                print(
                    f"[launcher] 本次 Trial：{artifacts.get('trial_id')}"
                    f"（{artifacts.get('status') or 'UNKNOWN'}）",
                    flush=True,
                )
                print(f"[launcher] CSV：{artifacts['csv']}", flush=True)
                if artifacts.get("replay"):
                    print(f"[launcher] REPLAY：{artifacts['replay']}", flush=True)
            elif artifacts:
                print(
                    f"[launcher] Trial {artifacts.get('trial_id')} 未导出"
                    f"（status={artifacts.get('status')}）；查看 {session / 'dashboard.log'}",
                    flush=True,
                )
            else:
                print(
                    "[launcher] 本次会话没有 trial.json（Dashboard 未启动或未启用 --follow-record）；"
                    "不使用全局最新 CSV 代替。",
                    flush=True,
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
