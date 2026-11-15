# 资产清单与备份记录（S0 基线）

- 日期：2026-11-12（Asia/Shanghai）
- 范围：现有稳定固件、源码快照、构建配置、关键控制配置、PWM Console、关键实验记录与证据。
- 原则：本文件只记录位置、用途、版本和 SHA-256；不复制密钥。稳定文件未被修改、移动、覆盖或删除。
- Git 策略：源码、配置和文档纳入 Git；`data/`、`logs/`、`videos/`、`evidence/`、固件构建产物和二进制由 `.gitignore` 排除，另存独立备份。

## 1. 独立备份

| 项目 | 内容 |
|---|---|
| 备份根目录 | `/home/example/Developer/research/tactile-gripper-backups/S0-20261112T192245+0800` |
| 与项目关系 | 位于项目目录和两个 worktree 之外；未提交进 Git |
| 内容 | 两版稳定固件源码/构建配置/二进制、全部 `config/*.json`、PWM Console 与上位机源码、关键文档、全部现有日志、关键证据摘要、S3 迁移前 Flash 与旧 ESP32 Flash 备份 |
| 文件数 | 244（含 `manifest.sha256` 与 `BACKUP_README.md`） |
| 大小 | 约 88 MB |
| 校验 | `shasum -a 256 -c manifest.sha256` 已验证全部 OK |
| 未整体复制 | 完整 `evidence/` 树（约 550 MB，含历史构建目录、`.map`、中间文件）；`.tools/`（约 6.5 GB）；`.venv/`。原位置保留 |

## 2. 旧 ESP32 稳定固件（回退基线）

| 资产 | 路径 | 用途 | 版本 | SHA-256 | 独立备份 |
|---|---|---|---|---|---|
| 应用 BIN | `evidence/stage09b24/build_bench/gripper_control.ino.bin` | 已验证 Bench/机械控制固件 | `gripper-control-bench-0.9b24.0` | `bd02b1d22165afda4bf6ab5e39907693e238d3c017145368b3a7e0aa9ffb98e1` | 是 |
| Bootloader BIN | `evidence/stage09b24/build_bench/gripper_control.ino.bootloader.bin` | 恢复/重烧所需引导区 | 同上 | `0f017cfd0a11841594147a09fb2dd23b1c3e183797888137dab9ebe73b2185c2` | 是 |
| 分区表 BIN | `evidence/stage09b24/build_bench/gripper_control.ino.partitions.bin` | 恢复/重烧所需分区表 | 同上 | `148b959cbff1c38aa8e1d5c0ba9d612c54997b945e56a63f41223eef650653a1` | 是 |
| 合并 BIN | `evidence/stage09b24/build_bench/gripper_control.ino.merged.bin` | 整片恢复参考 | 同上 | `76280a73c7391afe9045131adc0e6a65c6a37d8bf7239e45afe239d90aa70c4b` | 是 |
| ELF | `evidence/stage09b24/build_bench/gripper_control.ino.elf` | 符号/构建追溯 | 同上 | `0f40a462fb88c9dc8ece36ff719dedc24718dc21b9c0e236fe4bdba2dd95028f` | 是 |
| 应用源码快照 | `evidence/stage09b26/backups/gripper_control.ino.orig` | 0.9b24 实际源码（与 `evidence/stage09b24/sha256_after.txt` 一致） | 同上 | `0803ef55f107dedc68985ec213d6e8258acd0bdb06c86c479f9e1f56de4a13c2` | 是 |
| 安全核心源码 | `evidence/stage09b26/backups/SafetyCore.h.orig` | 0.9b24 实际 `SafetyCore.h` | 同上 | `fb4eca95557a355cfc6b9c8009ff7aabaabcf5a4964482194458bfaca66f65d3` | 是 |
| 生成配置 | `evidence/stage09b24/build_bench/sketch/generated_config.h` | 0.9b24 构建时实际生成的配置头 | 同上 | `1a0457a7ac35d5774dff49e8f59c86fa51e8bea9c8fa60c98894056a78d48fbe` | 是 |
| 构建目标 | `evidence/stage09b24/build_bench/build.options.json` | FQBN `esp32:esp32:nodemcu-32s` | — | `ee4d7cc7887944c68613071ab90918d2f55cd89ba5103e23497a497206e6150f` | 是 |

注意：当前 `firmware/gripper_control/gripper_control.ino` 与 `SafetyCore.h` 是 **S3 0.9b26 源码**，不是旧 ESP32 0.9b24 的源码；旧版实际源码快照以本表 `evidence/stage09b26/backups/*.orig` 为准。

## 3. ESP32-S3 稳定固件（当前主控制器）

| 资产 | 路径 | 用途 | 版本 | SHA-256 | 独立备份 |
|---|---|---|---|---|---|
| 应用 BIN | `evidence/stage09b26/build_s3/gripper_control.ino.bin` | 已上传/已验收 S3 固件 | `gripper-control-s3-0.9b26.0` | `04c77eed02c1d300f1d6aede842069489295f9fab4638ad2612acecb519c9348` | 是 |
| Bootloader BIN | `evidence/stage09b26/build_s3/gripper_control.ino.bootloader.bin` | 恢复/重烧所需引导区 | 同上 | `a9e4646a54fd2fe0dbfe724788a68597d5fb4820acd1203aa1f8502922243153` | 是 |
| 分区表 BIN | `evidence/stage09b26/build_s3/gripper_control.ino.partitions.bin` | 恢复/重烧所需分区表 | 同上 | `ace02503447d0f470692e65fa76002f2d77a92dc81cd3813d8aa66718d716da9` | 是 |
| 合并 BIN | `evidence/stage09b26/build_s3/gripper_control.ino.merged.bin` | 整片恢复参考（16 MB） | 同上 | `d2c2f97f54f90fe4455b08c6c971894b61de293b1011a7fc6b99d216201f23cc` | 是 |
| ELF | `evidence/stage09b26/build_s3/gripper_control.ino.elf` | 符号/构建追溯 | 同上 | `ff2bfa69dcb0cc09cafa8b636ced99a1f9de00802f4335b6052925551a1e7437` | 是 |
| 应用源码 | `firmware/gripper_control/gripper_control.ino` | 当前 S3 源码 | 同上 | `7f709f1d5560fd8c1ca8a6ef1a28cb6a4509890044e0e0c95832e6b41dee97e5` | 是 |
| 安全核心源码 | `firmware/gripper_control/SafetyCore.h` | 当前 S3 安全核心 | 同上 | `dc083e6f9f83d35a1399c9e00646f240354eb89430a04e33d6abec9280c98c47` | 是 |
| S3 生成配置 | `firmware/gripper_control/generated_config_s3.h` | GPIO4/50 Hz/14-bit 构建配置 | 同上 | `83c8af394eb2ff8fd41b5fb0572077a000270612b31ffa880cadeaefffa08c64` | 是 |
| S3 运行配置 | `config/gripper_s3.json` | S3 控制/串口/Bench 参数 | 同上 | `b4929f059940365a67df7dccf8df6c838c55b4e5f9bb3cbcaff3ddf51db44b78` | 是 |
| S3 构建目标 | `evidence/stage09b26/build_s3/build.options.json` | FQBN `esp32:esp32:esp32s3...` | — | `c0955ffad92da18e95ee294355aab1ed14168cc58aeac7f230cdb2301be35716` | 是 |
| 板级配置（当前） | `config/board_s3.json` | 板型、Flash/PSRAM、串口 | — | `9dfb68696159b9f65747a9e40c70b9dc26b16ca57d35cb7870a230b5d7c350b7` | 是 |

> **2026-11-16 恢复构建（当前运行）**：同源同配置重建并上传 app `d20782808447385a2ad090e63082f55e7f824652220441f07230f9dbf89830c4`（316288 B），
> 上传 460800、无全片擦除，真实 STATUS 为 `gripper-control-s3-0.9b26.0` / DISARMED / GPIO4 / 50 Hz / 14-bit。
> 历史验收 app `04c77eed…`（316272 B）保留为历史；bootloader/分区表/生成头/源码/配置哈希与上表一致。
> 详见 [P3-B1 S3 恢复记录](P3B1_S3_FIRMWARE_RECOVERY.md)（I-216）。
> **2026-11-16 TX 背压修复版（当前运行）**：app `bd039a8ae54bb908c3d8afefcf1eb60326ff7c80d9fd3cca9620faec05cb48ee`（317840 B），
> 已 460800 重烧并通过真实无 PWM 验证（64/64 应答、0 NUL、5 次连续会话 + 20 次背靠背心跳）；
> `d20782…` 为上一版。详见 [TX 背压诊断](P3B1_S3_TX_BACKPRESSURE_DIAGNOSIS.md)（I-217）。

注意：`config/board_s3.json` 当前哈希与 `evidence/stage09b26/sha256_after.txt` 记录的历史值 `b8079273...` 不同（S3 部署后更新了板级/上传描述字段）；控制参数以 `config/gripper_s3.json`（`b4929f...`）和 `generated_config_s3.h`（`83c8af...`）为准，不把当前板级描述反推为部署时快照。

## 4. PWM Console 与关键上位机工具

| 资产 | 路径 | 用途 | SHA-256 | 独立备份 |
|---|---|---|---|---|
| PWM Console | `scripts/pwm_console.py` | 真实/模拟 PWM 控制台；本 S0 未修改其行为 | `759e013b5664b6f4abccffdbc3c7faba6dbc9eb3e51ffc77818f6e8df31d7363` | 是 |
| Console 文档 | `docs/PWM_CONSOLE.md` | 使用与安全约束 | `afa44a8a851e1bd990c61f1e0c415cadd9f3954f45529fea606ba0a834d4c2b6` | 是 |
| Bench 适配 | `src/gripper_a/bench.py` | Console 的设备端交互与日志 | `c70e6e93e176e8455cf621477ec12871373c08d49d23272685b8cf4604c2e755` | 是 |
| 串口客户端 | `src/gripper_a/serial_client.py` | JSONL/超时/日志传输 | `c26c7a225131d2b7af9db0b7f07293b6d338497d7ce7662264277e8af7b04367` | 是 |
| 固件构建脚本 | `scripts/build_firmware.py` | `esp32`/`s3` 独立构建目标 | `af31cd1cc9fc1a0345a0f24edb2ea64f0d7186cb467e7cfa7599c4288358d5c9` | 是 |
| 配置生成脚本 | `scripts/generate_gripper_config.py` | 从 JSON 生成固件配置头 | `a4b7e2dddb4686f239e34264a1ff4eae19f6eb5e0157de88b3617302b9496472` | 是 |

## 5. 关键配置（全部 `config/*.json`）

| 文件 | SHA-256 | 说明 |
|---|---|---|
| `config/board_esp32.json` | `093b49e586a7246554ad67a8132c1a11af6d52c268a0be9a8333e6bc80401342` | 旧 ESP32 回退板级配置 |
| `config/board_s3.json` | `9dfb68696159b9f65747a9e40c70b9dc26b16ca57d35cb7870a230b5d7c350b7` | S3 板级配置（当前） |
| `config/calibration_reference.template.json` | `524fe83e2cd4aebb975bd7508a4d9ee11e4949c801684ff9878c26ad4c581a7d` | 未确认标定模板 |
| `config/control.template.json` | `799af19de69fc1e548d54cb8b8f21df19564259090615b6fb9b31161fb1defb2` | 设计模板，非可执行 |
| `config/first_motion_record.template.json` | `4ee4909163479401ac3bab46c9b5697826ef59e1df3d6ccff94121aab5ba3f60` | 首次运动记录模板 |
| `config/gripper_bench.json` | `9aa3f6f58b9bf81c374def9f9c1b1ec06032104db3ff23a233b1266be40e2acd` | 旧 ESP32 0.9b24 Bench 配置 |
| `config/gripper_control.json` | `0853b322ade89638944c7907e260143e32635d103f2d63d81d533ed0aea948c9` | 通用控制配置 |
| `config/gripper_s3.json` | `b4929f059940365a67df7dccf8df6c838c55b4e5f9bb3cbcaff3ddf51db44b78` | S3 0.9b26 配置 |
| `config/gripper_trial.json` | `7fa5f3f688f2b6363c74d1b09a94c62d7969dca0913a69d8c35fb24f399713d3` | Trial 配置 |
| `config/serial_test.json` | `a6856151ddf5448e5376257c883d7fd36f7571b501831a86ce7571c08839c202` | 串口测试配置 |
| `config/simulated.json` | `c8092dcd99b53c1a3d60590d36c5be59a49ef49647bae1527d36ca32e27e0566` | 模拟配置 |

## 6. 关键实验记录与证据

| 资产 | 路径 | 说明 | SHA-256 | 独立备份 |
|---|---|---|---|---|
| S3 真实验收日志 | `logs/real/bench/0e0571fd739d4f638541df1ccae5cc9b/transport.jsonl` | 0.9b26 真实命令/ACK/状态时间线；不证明机械位置 | `a8721adfca98471a602266aff2418fb74eaee8abc2f1619d1a44e4037512e241` | 是（`logs/`） |
| S3 阶段摘要 | `evidence/stage09b26/summary.json` | 构建、上传、验收摘要 | `e142fb8d1f544ca770e21c500b752e7db93975827756b7614ab609bb7a5ae907` | 是 |
| S3 真实验收 | `evidence/stage09b26/real_acceptance.json` | 用户报告开合 PASS 与 UNKNOWN 项 | `9a9acd2a025d21cdabbcfbf6e28722c91024582bd6545ed8d8cb796f5209a8b7` | 是 |
| 旧 ESP32 阶段摘要 | `evidence/stage09b24/summary.json` | 0.9b24 构建/上传/测试摘要 | `79e5b5a49d79ed80958e372d1e120ebfd5a1bb94431618fa13cfce147a6b428d` | 是 |
| S3 迁移前 Flash | `evidence/stage09b26/s3_pre_migration_flash_16MB_460800.bin` | 迁移前 16 MB 只读备份 | `cd0f30ac9491da499eaf2167f07b5accf23cf6779c506110431aa766f346273e` | 是（`flash-backups/`） |
| 旧 ESP32 Stage 0.8 Flash | `evidence/stage08/flash_backup_original.bin` / `flash_backup_verify.bin` | 原始/校验 4 MB 备份 | 见 `evidence/stage08/backup_manifest.json` | 是（`flash-backups/`） |

## 8. P3-B 双日志监控资产（2026-11-16）

只读 Dashboard 新增的文件（源码随 Git 保存；真实日志/证据仍只在本地）：

| 资产 | 路径 | 用途 | SHA-256（源码） |
|---|---|---|---|
| FSR 采集脚本 | `scripts/capture_fsr_live.py` | 独占 FSR 串口，写 `fsr_stream.jsonl`（host UTC + monotonic + raw/message） | `fa9862879dc584d6b37dbe1ade095d48b4215aece6f4a7abd34fa89d0263a589` |
| 一键启动器 | `scripts/run_live_monitor.py` | 启 FSR 采集 + 只读 Dashboard + 当前终端 console；会话收尾/CSV 提示 | `716e69a7bc02bbf5483a43d0908996fdd70d87679efd35019daf3df9d7acdf35` |
| 只读适配器 | `src/tactile_gripper/devices/log_follow.py` | JSONL tail、PWM 命令/ACK 状态机、FSR 严格解析接入 | 随 Git 提交 |
| 会话目录 | `logs/real/sessions/session_<UTC>_<id>/` | `session.json`、`transport.jsonl`、`fsr/fsr_stream.jsonl`、两份 `.log` | 本地（`logs/` 已 gitignore） |
| 测试 | `tests/test_log_follow.py` | 正常/无 ACK/STOP/陈旧/轮转/半行/截断/NUL/0x04/CSV/回放 | 随 Git 提交 |

FSR 流字段：`host_time_utc`、`host_monotonic_ns`、`direction`、`raw`、`message`；
`MARKER` 记录标记 `CAPTURE_START/END`。PWM 流沿用既有 `transport.jsonl` 事件
（`COMMAND/TX/RX/IGNORED/MATCHED/RESPONSE/COMMUNICATION_ERROR/BENCH_ACTION/CLOSED`）。
真实会话日志不得提交到公开仓库。

## 9. 未改动与未执行声明


- 本轮未修改、覆盖、删除任何稳定固件、PWM Console 行为或现有实验记录。
- 本轮未打开真实串口、未发 PWM、未烧录 ESP32、未进行机械运动或接线/上电。
- 完整历史 `evidence/` 树未整体复制到备份；其原始文件保留在原位置，关键子集已复制。若后续需要完整异地备份，应另行安排磁盘与校验。
