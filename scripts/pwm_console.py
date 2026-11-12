"""Interactive gripper console. Menu selects mechanical (continuous) or detached (pulse) mode."""

import argparse, json, os, select, sys, uuid
from pathlib import Path
from gripper_a.bench import BenchController

TARGET_CONFIGS = {
    "esp32": Path("config/gripper_bench.json"),
    "s3": Path("config/gripper_s3.json"),
}
MENU = """Select mode:
  1 - mechanical gripper (GRIPPER_ASSEMBLED, continuous hold)
  2 - detached servo test (DETACHED_BENCH, pulse <=500ms)
  0 - exit"""
HELP = "number (500..2500, any step) | status | stop | help | quit"


class Lines:
    """Non-blocking line reader; keeps heartbeats running while idle."""
    def __init__(self, fd=0):
        self.fd = fd
        self.buf = b""

    def readline(self, timeout):
        if b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            return line.decode("utf-8", "replace")
        if not select.select([self.fd], [], [], timeout)[0]:
            return None
        chunk = os.read(self.fd, 4096)
        if not chunk:
            raise EOFError
        self.buf += chunk
        if b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            return line.decode("utf-8", "replace")
        return None


def prompt(lines, text):
    print(text, end="", flush=True)
    while True:
        try:
            line = lines.readline(0.2)
        except EOFError:
            return None
        if line is not None:
            return line.strip()


def choose_menu(lines):
    while True:
        print(MENU)
        raw = prompt(lines, "choice> ")
        if raw is None:
            return None
        if raw == "0":
            return None
        if raw == "1":
            return "mech"
        if raw == "2":
            return "detached"
        print("Invalid choice.")


def control(g, lines):
    print("Enter PWM 500..2500 directly; stop/status/help/quit.")
    while True:
        try:
            pending = g.pending_until is not None
            g.poll()
            if pending and g.pending_until is None:
                print("[output ended; ready for next target]")
        except Exception as e:
            print("Session error:", e)
            return "error"
        try:
            line = lines.readline(0.1)
        except EOFError:
            return "eof"
        if line is None:
            continue
        cmd = line.strip().lower()
        if not cmd:
            continue
        try:
            if cmd in ("quit", "exit"):
                return "quit"
            if cmd == "help":
                print(HELP)
            elif cmd == "status":
                print(json.dumps(g.get_status(), ensure_ascii=False))
            elif cmd == "stop":
                g.stop()
                print("STOP sent; session stopped. Choose a mode to restart.")
                return "stopped"
            elif cmd.isascii() and cmd.isdigit():
                r = g.pulse(int(cmd))
                print(("ACK" if r.get("type") == "ACK" else r.get("type")), cmd, "us")
            else:
                raise ValueError("unknown_command")
        except (ValueError, PermissionError) as e:
            print("Rejected:", e)
        except RuntimeError as e:
            print("Session error:", e)
            return "error"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--real", action="store_true")
    p.add_argument("--port", help="explicit Mac serial port, e.g. /dev/cu.usbserial-XXXX")
    p.add_argument("--target", choices=sorted(TARGET_CONFIGS), default=None,
                   help="board target profile; default esp32 for backward compatibility")
    p.add_argument("--config", help="explicit config JSON; overrides --target")
    p.add_argument("--list-ports", action="store_true", help="list serial ports and exit without opening one")
    p.add_argument("--authorize", action="store_true", help="Authorize this console session")
    p.add_argument("--authorize-detached-bench", action="store_true", help=argparse.SUPPRESS)
    a = p.parse_args()
    if a.list_ports:
        from serial.tools import list_ports
        for port in list_ports.comports():
            print(port.device, "|", port.description, "|", port.hwid)
        return
    authorized = a.authorize or a.authorize_detached_bench
    if a.real and (not a.port or not authorized):
        p.error("REAL requires --port and --authorize")
    if a.real and not sys.stdin.isatty():
        p.error("REAL requires interactive terminal; no serial opened")
    if not a.real and authorized:
        p.error("authorization flag requires --real")
    target = a.target or "esp32"
    config_path = Path(a.config) if a.config else TARGET_CONFIGS[target]
    try:
        config = json.loads(config_path.read_text())
    except (OSError, ValueError) as e:
        p.error(f"cannot load config {config_path}: {e}")
    kind = "REAL_SERIAL" if a.real else "SIMULATED"
    folder = Path("logs/real" if a.real else "logs/simulated") / "bench" / uuid.uuid4().hex
    folder.mkdir(parents=True)
    g = BenchController(
        config=config,
        dry_run=not a.real,
        hardware_permission=a.real,
        authorized=True,
        log_path=folder / "transport.jsonl",
    )
    lines = Lines()
    print(kind, "interactive console; no PWM until you choose a mode and enter a target.")
    print("Target:", target, "Config:", config_path)
    print("Expected firmware:", g.config["firmware_version"], "Logs:", folder)
    try:
        print(json.dumps(g.connect(a.port), ensure_ascii=False))
    except Exception as e:
        print("Connect failed:", e)
        return
    try:
        while True:
            mode = choose_menu(lines)
            if mode is None:
                break
            assembled = (mode == "mech")
            try:
                g.begin(assembled=assembled)
                g.select_mode(True if assembled else False)
                print("Session ready; no PWM sent. Enter a target yourself.")
                result = control(g, lines)
            except Exception as e:
                print("Session error:", e)
                result = "error"
            if result == "quit":
                break
            if result == "error":
                break
    except KeyboardInterrupt:
        print("\nCtrl+C: stopping.")
    finally:
        try:
            g.close()
        except Exception as e:
            print("Close failed; output UNKNOWN:", e)
        print("Console closed; STOP/DISARM does not cut servo power.")


if __name__ == "__main__":
    main()
