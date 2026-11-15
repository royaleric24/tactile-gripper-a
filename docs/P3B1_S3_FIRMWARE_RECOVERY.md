# P3-B1｜ESP32-S3 控制固件恢复记录（2026-11-15/16）

状态：**固件构建 PASS、上传 PASS、真实 STATUS PASS**。本轮只恢复 S3 控制固件并读取
STATUS；**未发送 PWM、未启动 AUTO、未操作旧 ESP32 的 FSR 固件、未做机械动作**。
上传前按用户确认断开 PM15S 独立动力电源。

## 1. 授权与设备身份

| 项 | 值 |
|---|---|
| 授权范围 | 仅 `/dev/cu.usbserial-A5069RR4` 的 ESP32-S3 固件恢复 |
| 芯片 | ESP32-S3 (QFN56) revision v0.2 |
| MAC | `c4:9e:7e:08:25:78` |
| PSRAM | 8 MB（Embedded PSRAM 8MB AP_3v3） |
| Flash | 16 MB |
| USB 桥 | FT232R（串口 `/dev/cu.usbserial-A5069RR4`） |
| esptool | 5.1.0（Arduino CLI 内置） |
| Arduino CLI | 1.5.1 |
| 上传前状态 | PM15S 独立动力电源断开（用户确认） |

## 2. 构建

命令：

```bash
python3 scripts/build_firmware.py s3
```

结果：**PASS**（`Sketch uses 316139 bytes (10%)`；全局变量 21676 B）。

完整编译 FQBN：

```
esp32:esp32:esp32s3:FlashSize=16M,FlashMode=qio,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,UploadSpeed=921600,USBMode=hwcdc,CDCOnBoot=default,UploadMode=default,EraseFlash=none
```

| 资产 | 大小 | SHA-256 |
|---|---:|---|
| app `gripper_control.ino.bin` | 316288 | `d20782808447385a2ad090e63082f55e7f824652220441f07230f9dbf89830c4` |
| bootloader | 20224 | `a9e4646a54fd2fe0dbfe724788a68597d5fb4820acd1203aa1f8502922243153` |
| partitions | 3072 | `ace02503447d0f470692e65fa76002f2d77a92dc81cd3813d8aa66718d716da9` |
| merged | 16777216 | `71da3c89726feaf204022bd7d9ac3875a7eaeacdaf41b7193561fe533ca38cbc` |
| ELF | 6898044 | `8bb2c8c054cbc37c9030a115034a6e3d643a736e78953e84e4d42434442fda27` |

配置与生成头：

| 文件 | SHA-256 | 说明 |
|---|---|---|
| `config/board_s3.json` | `e4dbbdf2b0c8afda19f6942f1997c322ca18c89426862c26346ba44e9ed4e4f7` | 板级/FQBN/端口描述 |
| `config/gripper_s3.json` | `b4929f059940365a67df7dccf8df6c838c55b4e5f9bb3cbcaff3ddf51db44b78` | 0.9b26.0 运行配置 |
| `firmware/gripper_control/generated_config_s3.h` | `83c8af394eb2ff8fd41b5fb0572077a000270612b31ffa880cadeaefffa08c64` | 与历史验收清单一致 |
| `firmware/gripper_control/gripper_control.ino` | `7f709f1d5560fd8c1ca8a6ef1a28cb6a4509890044e0e0c95832e6b41dee97e5` | 与历史清单一致 |
| `firmware/gripper_control/SafetyCore.h` | `dc083e6f9f83d35a1399c9e00646f240354eb89430a04e33d6abec9280c98c47` | 与历史清单一致 |

生成头文件重新生成后与备份逐字节一致；`CFG_FIRMWARE_VERSION="gripper-control-s3-0.9b26.0"`、
`CFG_GPIO=4`、`CFG_FREQUENCY_HZ=50`、`CFG_RESOLUTION_BITS=14`、`CFG_HARDWARE_ENABLED=false`、
`CFG_BENCH_ENABLED=true`、`CFG_CALIBRATED=false`。

**与历史验收二进制的差异**：历史 app SHA 为 `04c77eed02c1d300f1d6aede842069489295f9fab4638ad2612acecb519c9348`
（316272 B），本次为 `d20782…`（316288 B）。bootloader 与分区表哈希与历史完全一致；源码、生成头、
运行配置哈希也与历史清单一致。16 B 差异与构建路径/工具链非确定性一致，版本字符串与配置常量
已从新二进制中确认，**不是源码变更**。历史 app 二进制不在本 worktree（I-213 保留）。

## 3. 上传

使用项目适配的 Arduino CLI，FQBN 与构建相同，但上传速率按历史成功值改为 **460800**
（构建产物的 `UploadSpeed=921600` 不改变固件内容）：

```bash
arduino-cli --config-file .tools/arduino-cli.yaml upload \
  -p /dev/cu.usbserial-A5069RR4 \
  --fqbn "esp32:esp32:esp32s3:FlashSize=16M,FlashMode=qio,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,UploadSpeed=460800,USBMode=hwcdc,CDCOnBoot=default,UploadMode=default,EraseFlash=none" \
  --input-dir "$PWD/evidence/stage09b26/build_s3" \
  "$PWD/firmware/gripper_control"
```

结果：**PASS**。未执行全片擦除；写入范围：

- `0x00000000–0x00004fff` bootloader
- `0x00008000–0x00008fff` partitions
- `0x0000e000–0x0000ffff` boot_app0
- `0x00010000–0x0005dfff` app

每一段均 `Hash of data verified`。上传日志：
`evidence/stage09b26/upload_s3_20261115T235933.log`，
SHA-256 `76175d40d204515b5cfe487d2bbe7087aee2d1b252c76fbb2c026031f5eea420`。

## 4. 真实 STATUS（只读）

连接后只发送 `GET_STATUS`，未发送 PWM、BEGIN_BENCH、STOP 或 DISARM。
真实响应（完整 JSON 在本地 `evidence/stage09b26/s3_status_20261116T000018.json`）：

| 字段 | 值 |
|---|---|
| `firmware_version` | `gripper-control-s3-0.9b26.0` |
| `board_target` | `esp32s3` |
| `pwm_gpio` | 4 |
| `pwm_frequency_hz` | 50 |
| `pwm_resolution_bits` | 14 |
| `chip_model` | `ESP32-S3` |
| `flash_size_bytes` | 16777216 |
| `psram_size_bytes` | 8388608 |
| `state` | **DISARMED** |
| `fault_reason` | `BOOT`（启动原因字段，不是故障） |
| `hardware_enabled` | false |
| `calibration_state` | `UNCALIBRATED` |
| `bench_capable` | true |
| `bench_active` | false |
| `output_state` | `DISABLED_UNMEASURED` |
| `commanded_pulse_us` | null |
| `actual_angle_deg` / `actual_opening` | null / null |
| `boot_id` | `2fc1e71327aa656e7040fe9114932e4e` |

通信检查：整个会话 1 次 `GET_STATUS` 匹配成功；159 条 ESP-ROM 启动 banner 被
`boot_or_invalid_json` 过滤；**0 个 ERROR、0 个 FAULT、0 个 timeout**。
`fault_reason=BOOT` 只是启动原因，不是故障锁存。

## 5. 证据与状态

| 项 | 状态 |
|---|---|
| S3 离线构建 | **PASS / OFFLINE_VERIFIED** |
| 上传（460800，无全片擦除） | **PASS / VERIFIED_REAL**，每段 hash verified |
| 真实 STATUS 版本/GPIO/频率/位数/DISARMED | **PASS / VERIFIED_REAL** |
| 通信异常 | **0 ERROR / 0 FAULT / 0 timeout** |
| PWM 输出 / 机械动作 | **NOT_TESTED（本轮明确禁止）** |
| AUTO | **NOT_TESTED / 保持 `AUTO_REAL_ENABLED=False`** |
| 旧 ESP32 FSR 固件 | **未触碰** |

本地证据（未提交）：`evidence/stage09b26/build_s3/`、`build_s3.json`、`build_s3.txt`、
`generate_s3.txt`、`generated_config_s3.h`、`upload_s3_*.log`、`s3_status_*.json`、
`s3_recovery_summary.json`；传输日志 `logs/real/s3_status_verify/20261116T000018/transport.jsonl`。

## 6. 下一步

> 2026-11-16 更新：随后两次真实 console 会话出现 `response_timeout`，已定位为 `respond()` 的
> 900 B TX 阈值不足（ACK/STATUS 实测 942–963 B）。修复版 `bd039a8…`（317840 B）已 **460800 重烧**
> 并通过真实无 PWM 验证（64/64 应答、0 NUL、5 次连续会话 + 20 次背靠背心跳、最终 DISARMED）；
> **当前运行是修复版 `bd039a8…`**，本文记录的 `d20782…` 为上一版。空杯运动等待用户明确恢复。
> 详见 [TX 背压诊断](P3B1_S3_TX_BACKPRESSURE_DIAGNOSIS.md)。

S3 已恢复为已验收的 `gripper-control-s3-0.9b26.0`，`DISARMED`、`DISABLED_UNMEASURED`、
`bench_capable=true`。下一步是空杯 MANUAL 抓取与 FSR 同步采集；仍需：

1. 重新确认 PM15S 独立动力电源接通、共地、机械爪装配、空杯有支撑、可随时断电；
2. 用户在自己的 Terminal 运行 `pwm_console.py --target s3 --real --port /dev/cu.usbserial-A5069RR4 --authorize`；
3. 按已授权 **1300–1500 μs、50 μs 步进、1300 下限（不进 1270）** 执行，FSR 只记录不闭环；
4. 每次抓取前采连续空载基线，记录 PWM/ACK/FSR 原始 counts/接触/稳定/形变。
