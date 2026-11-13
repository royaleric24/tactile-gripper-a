#!/usr/bin/env python3
"""Run the complete Stage H1 hardware validation sequence on the old ESP32.

Steps: identify -> DIAG -> 60 s acquisition -> analyze -> Markdown/JSON report.
The report distinguishes PASSED / FAILED / NOT_TESTED.  It never invents channel
values or a press response.  Run this only with the old ESP32 connected.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run_step(cmd: list[str], log_path: Path) -> tuple[int, str]:
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log_path.write_text("$ " + " ".join(cmd) + "\n\n" + proc.stdout)
    print(proc.stdout, end="", flush=True)
    return proc.returncode, proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--out-root", default=str(ROOT / "data/real/tactile"))
    parser.add_argument("--report-dir", default=str(ROOT / "evidence/sensor"))
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    run_dir = Path(args.out_root) / "{}_h1_validation".format(stamp)
    diag_path = report_dir / "h1_diagnostics_{}.json".format(stamp)
    logs = {
        "identify": report_dir / "h1_identify_{}.log".format(stamp),
        "diag": report_dir / "h1_diag_{}.log".format(stamp),
        "run": report_dir / "h1_run_{}.log".format(stamp),
        "analyze": report_dir / "h1_analyze_{}.log".format(stamp),
    }

    ident_code, ident_text = run_step(
        [PY, "-m", "tools.tactile_acq", "identify", "--port", args.port, "--baud", str(args.baud)],
        logs["identify"],
    )
    if ident_code != 0:
        print("IDENTIFY FAILED; no DIAG or acquisition was attempted.")
        return 2
    diag_code, _ = run_step(
        [PY, "-m", "tools.tactile_acq", "diag", "--port", args.port, "--baud", str(args.baud), "--out", str(diag_path)],
        logs["diag"],
    )
    run_code, _ = run_step(
        [
            PY, "-m", "tools.tactile_acq", "run",
            "--port", args.port, "--baud", str(args.baud),
            "--duration", str(args.duration), "--monitor", "none", "--out", str(run_dir),
        ],
        logs["run"],
    )
    analyze_code, analyze_text = run_step(
        [PY, "-m", "tools.tactile_acq", "analyze", str(run_dir)],
        logs["analyze"],
    )

    diag = json.loads(diag_path.read_text()) if diag_path.is_file() else None
    run_path = run_dir / "run.json"
    run_meta = json.loads(run_path.read_text()) if run_path.is_file() else None
    summary = (run_meta or {}).get("summary") or {}
    diag_pass = bool(diag and diag.get("overall") == "PASSED")
    samples = int(summary.get("samples") or 0)
    rate = summary.get("device_frame_rate_hz")
    rate_pass = rate is not None and rate >= 20.0
    drop_rate = (summary.get("frame_seq") or {}).get("drop_rate")
    result = "PASSED" if (diag_pass and samples > 0 and rate_pass) else "FAILED"

    lines = [
        "# Stage H1 真实硬件验证报告",
        "",
        "- 时间：{}".format(datetime.now(timezone.utc).isoformat()),
        "- 端口：`{}`".format(args.port),
        "- 设备：{}".format((run_meta or {}).get("identity", {}).get("device_id") if run_meta else "UNKNOWN"),
        "- 固件：{}".format((run_meta or {}).get("identity", {}).get("firmware_version") if run_meta else "UNKNOWN"),
        "- 数据目录：`{}`".format(run_dir),
        "- 总结果：**{}**".format(result),
        "",
        "## 1. 三颗 ADS1220 通信与配置",
        "",
        "| 检查 | 结果 |",
        "|---|---|",
    ]
    if diag:
        for check in diag.get("checks", []):
            lines.append("| {} | {} |".format(check["check"], check["result"]))
        lines.append("")
        lines.append("| ADC | 当前配置 | Pattern A 读回 | Pattern B 读回 | Offset | AVDD mV | 温度 °C | AIN0..3 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for item in diag.get("devices", []):
            lines.append(
                "| {} | {} | {} | {} | {} | {} | {} | {} |".format(
                    item.get("adc"),
                    item.get("current_config"),
                    item.get("pattern_a_readback"),
                    item.get("pattern_b_readback"),
                    item.get("offset_raw"),
                    item.get("avdd_mv"),
                    "-" if item.get("temperature_centi_c") is None else round(item["temperature_centi_c"] / 100.0, 2),
                    item.get("channel_raw"),
                )
            )
    else:
        lines.append("| DIAG | FAILED (no diagnostics JSON) |")
    lines += [
        "",
        "## 2. 12 通道真实采样",
        "",
        "| 指标 | 实测 |",
        "|---|---|",
        "| 完整帧数 | {} |".format(samples),
        "| 设备时间帧率 | {} Hz |".format(rate),
        "| Mac 接收帧率 | {} Hz |".format(summary.get("host_frame_rate_hz")),
        "| 固件窗口帧率均值 | {} Hz |".format(summary.get("mean_effective_frame_rate_hz")),
        "| 丢帧数 / 丢帧率 | {} / {} |".format((summary.get("frame_seq") or {}).get("missing"), drop_rate),
        "| 重复 / 乱序 | {} / {} |".format((summary.get("frame_seq") or {}).get("duplicates"), (summary.get("frame_seq") or {}).get("out_of_order")),
        "| 主机超时次数 | {} |".format(summary.get("host_timeouts")),
        "| 有效通道比例 | {} |".format(summary.get("valid_ratio")),
        "| 饱和通道 | {} |".format(summary.get("saturated_channels")),
        "| 固定不变通道 | {} |".format(summary.get("fixed_channels")),
        "",
        "| CH | 标签 | valid | min | max | mean | std | 唯一值 | 饱和 | flags |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in summary.get("channels", []):
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                item.get("channel"), item.get("label"), item.get("valid_count"),
                item.get("min"), item.get("max"), item.get("mean"), item.get("std"),
                item.get("unique_values"), item.get("saturated_high", 0) + item.get("saturated_low", 0),
                ",".join(item.get("flag_counts", {}).keys()) or "-",
            )
        )
    lines += [
        "",
        "## 3. 人工按压/释放响应",
        "",
        "**NOT_TESTED**：自动化脚本不能证明真实接触响应；需要在场人员按压、保持、释放并记录观察。",
        "",
        "## 4. 判定",
        "",
        "- 三颗 ADC 通信/配置/内部自检：{}".format("PASSED" if diag_pass else "FAILED"),
        "- 12 路真实采样：{}".format("PASSED" if samples > 0 else "FAILED"),
        "- 完整帧率 ≥20 Hz：{}（实测 {} Hz）".format("PASSED" if rate_pass else "FAILED", rate),
        "- 人工按压响应：NOT_TESTED",
        "",
        "原始数据：`{}`".format(run_dir),
        "DIAG：`{}`".format(diag_path),
    ]
    report_path = report_dir / "H1_VALIDATION_{}.md".format(stamp)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path = report_dir / "H1_VALIDATION_{}.json".format(stamp)
    json_path.write_text(
        json.dumps(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "port": args.port,
                "result": result,
                "diag": diag,
                "run": run_meta,
                "analyze_log": analyze_text,
                "report": str(report_path),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("\nREPORT {} -> {}".format(result, report_path))
    return 0 if result == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
