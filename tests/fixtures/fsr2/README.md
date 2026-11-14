# FSR V2 样例帧

这些 JSONL 行**由固件帧构造器通过 host 模拟实际输出**，再写入文件，不是手写样例，也不是硬件实测。

- 设备标识已替换为 `tactile-esp32-01` / `sim-fsr2-boot-01`，不含个人路径或真实 MAC。
- 生成/校验命令：`python3 scripts/check_fsr2_frames.py`（会重写本目录文件并写
  `evidence/fsr2/frames/frames_check.json`）。
- 解析参考：`tools/fsr2/protocol_v2.py`。

| 文件 | 内容 |
|---|---|
| `hello_fsr_only.json` | FSR_ONLY HELLO，2 通道，四 ADC 全 OK |
| `sample_fsr_only_valid.json` | 健康帧，两路 counts 有效 |
| `sample_fsr_only_no_adc4.json` | ADC4 无响应：两通道 null + `NO_DATA` |
| `hello_hybrid.json` | HYBRID_6X6_FSR2 HELLO，38 通道 |
| `sample_hybrid_valid.json` | 38 通道健康帧 |
| `sample_hybrid_no_adc4.json` | 矩阵 36 通道有效、两路 FSR 失效 |

真实硬件跑通后，再补一组带实测 AVDD 与按压记录的样例；在此之前本目录**不得**被引用为硬件证据。
