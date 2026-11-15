# 触觉采集样例帧（V2）

这些 JSONL 行**由固件帧构造器通过 host 模拟实际输出**，再写入文件，不是手写样例，也不是硬件实测。

- 设备标识已替换为 `tactile-esp32-01` / `sim-fsr2-boot-01`，不含个人路径或真实 MAC。
- 生成/校验命令：`python3 scripts/check_fsr2_frames.py`（会重写本目录文件并写
  `evidence/fsr2/frames/frames_check.json`）。
- 解析参考：`tools/fsr2/protocol_v2.py`。

| 文件 | 内容 |
|---|---|
| `hello_fsr1.json`、`sample_fsr1_*.json`、`status_fsr1_no_adc4.json` | 当前单 FSR_A，ADC4 AIN0，通道 0，含 ADC4 故障 |
| `hello_electrodes12_fsr1_unmapped.json`、`sample_electrodes12_fsr1_*.json`、`status_electrodes12_fsr1_no_adc4.json` | 13 通道，通道 12 为 FSR_A，电极保持未映射 |
| `hello_fsr_only.json` | 历史 FSR_ONLY HELLO，2 通道 |
| `sample_fsr_only_valid.json` | FSR 健康帧 |
| `sample_fsr_only_no_adc4.json` | ADC4 无响应：两路 FSR `null` + `NO_DATA` |
| `hello_electrodes12_fsr2_unmapped.json` | 12 电极 + FSR HELLO，`mapping_status = PENDING_REAL_WIRING` |
| `sample_electrodes12_fsr2_unmapped.json` | 12 电极全部 `null` + `NO_DATA`，FSR 两路有效 |
| `sample_electrodes12_fsr2_fsr_absent.json` | ADC4 缺失：FSR 失效，电极仍为未映射 |
| `hello_electrodes12_mapped_synthetic.json` | 12 电极**合成映射** HELLO（仅测试） |
| `sample_electrodes12_mapped_synthetic.json` | 合成映射下 12 路电极数值（仅测试） |
| `sample_electrodes12_mapped_adc_absent.json` | 合成映射下 ADC1 缺失（仅测试） |

五组另有 `status_*.json`：C++ host 模拟调用同一个 STATUS 帧构造器生成，含
`request_id=fixture-status-1`、对应故障状态和最后帧序号。前三类既有 HELLO/SAMPLE 原件保留。

**注意**：`*_mapped_*` 系列使用 `tools/fsr2_sim/electrode_test_profile.h` 的
`SIM_SYNTHETIC_MAPPING`，只证明"映射齐全时读数正确"的代码路径；它不是现场接线表，不能作为
配置模板或验收证据。真实 R/C→ADC/AIN 映射缺失状态见 `docs/ISSUES.md` I-107。

真实硬件跑通后，再补一组带实测 AVDD 与按压记录的样例；在此之前本目录**不得**被引用为硬件证据。
