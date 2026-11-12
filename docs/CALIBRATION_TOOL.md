# 交互式局部标定工具

本轮仅离线开发。没有打开真实串口、发PWM或上传；不改固件/硬件配置。入口 scripts/calibrate_gripper.py，核心 src/gripper_a/calibration.py，复用 LimitedTrialController/SerialClient/FakeGripper。原 manual_trial.py 保留。

## 启动（默认模拟，可现在使用）

项目根目录运行：

```sh
PYTHONPATH=src .venv/bin/python scripts/calibrate_gripper.py
```

默认 SIMULATED，不访问设备。`--output` 可选指定一个尚不存在的新目录。日志/参考/观察/候选范围默认保存 logs/simulated/calibration/<唯一ID>/；底层传输日志在该目录旁，均标SIMULATED，不可作为真实标定。

真实模式另需用户授权后显式提供 `--real --port <实际端口> --hardware-permission`；运动还需 `--motion-permission`、有依据的初始参考和每次动作确认。本轮没有执行真实模式。真实记录在 logs/real/calibration/，应用日志标REAL_CALIBRATION，传输日志REAL_SERIAL；数值仍是命令/用户观察，不是编码器反馈。

## 指令与流程

| 指令 | 作用 |
|---|---|
| status | 设备/固件/许可、工具阶段、上次命令脉宽、最后人工确认安全的命令值、待观察状态；实际位置仍未知 |
| reference FILE | 载入初始参考证据JSON，展示后必须输入REVIEWED；只确认人工已有依据，不发送BEGIN或PWM |
| locate | 展示参考initial；再次输入EXECUTE 加该整数才请求一次BEGIN_TRIAL和首脉冲。首参考未确认、未授权则拒绝 |
| step +N / step -N | 相对上次命令的一次增减；展示目标并逐次EXECUTE确认，无自动重复；先记录上一动作观察 |
| observe | 人工录入OPENING/CLOSING/NONE/UNKNOWN、可选实测开度及方法、安全确认、异常和备注；未测量为空，不默认为0 |
| stop / disarm | 撤销会话，清除当前参考许可；不切断动力，不保证机械保持 |
| export MARGIN_US | 用多处人工确认安全记录导出内部候选端点，不写回固件或改变UNCALIBRATED |
| quit / Ctrl-C / EOF | 尝试DISARM、关闭串口和日志，保存观察数据；失败仍记录，不宣称已物理停止 |

工具阶段：UNREFERENCED → REFERENCE_CONFIRMED → LOCAL_CALIBRATING → LOCAL_RANGE_COMPLETE；FAULT单独锁定。STOP/到期清参考，不自动重开Trial；再次操作需重新人工审核参考。FAULT后不可仅重新reference覆盖状态；需停止、检查现场与故障原因后另启新工具会话。绝不把重启当作机械故障已排除。

## 初始参考不是“填个数字”

空模板 config/calibration_reference.template.json 含null及safe_path_confirmed=false，不能直接使用。真实参考需 installation_id、evidence_source、safe_initial_reason、reviewer、approval=INITIAL_TARGET_AND_PATH_REVIEWED、safe_path_confirmed=true、low/high/initial整数及source_kind=HUMAN_REVIEWED_REAL_EVIDENCE。来源应对应实际装配及首目标必经路径。模板不是范例首脉宽，不含1500默认值。

该文件是人工审核记录，不是自动生成的物理证据；不能靠把字段改成true来发现安全位置。软件只在参考已确认后使用LOCAL_RANGE_CONFIRMED，不能替代实际核查。

当前完整机械爪基本闭合、无PWM历史/方向/角反馈，因此工具默认所有运动操作被拒绝。建立参考的可行途径是先取得本套装配的可靠位置/脉宽依据并核对限位/路径；如果完全没有依据，就需另行批准由有能力人员采用脱联动、受约束夹具或其他明确风险控制的标定方式。仅凭照片、短输出或1500中位不能保证首定位安全；保持完整装配且无对应证据时，本工具不能消除首跳风险。

## 与现有固件兼容

无需改固件或重传。当前 gripper-control-trial-0.9b2.0 继续执行范围1460–1540、单步20、累计80、单次500ms、会话30秒、失联5秒、FAULT/UNKNOWN和boot_id/sequence检查。工具不扩大边界、不发正式ARM/SET，不自动扫描。

等待终端输入时只发送心跳，不发送脉冲；30秒窗口不可由心跳延长。输入多行观察或确认时，阻塞输入可能导致5秒通信超时，固件会收敛，后续命令拒绝；工具不会为方便而放宽期限或自动恢复。单次脉冲500ms按板端逻辑结束，与实际机械位移无比例保证。可跨会话积累同一installation记录，每次重新核实首参考；改变安装必须新建记录目录。

## 导出与日志

calibration.jsonl含UTC/单调时刻、固件版本、操作/目标PWM、设备响应、人工方向、实测开度/方法、异常、安全范围及参考来源；observed_positions.json存确认记录。不确认就不成为安全位置。pulse_us是已发出的目标，不是实际角度；实际角度始终null。

候选导出要求至少4个不同的已观察安全目标、无异常/不安全记录、无待确认动作、正数余量。以观察外缘向内收缩，并仅取确实观察过的内部目标为候选端点；样本不足就拒绝。方向关系按增/减命令和人工观察计算，矛盾则拒绝，缺证据写UNKNOWN。

candidate_range.json标CANDIDATE_ONLY_NOT_DEVICE_CALIBRATION，continuous_interval_verified=false、automatic_hardware_enable=false。它不证明两个端点之间整个区间无干涉，也不触发设备CONFIRMED；须人工复核机构/样本密度及余量。继续动作或出现FAULT时，已导出文件标STALE_REVIEW_REQUIRED，不能当现行放行文件。

异常记录后立即停止后续动作、尝试STOP，并要求现场人员按既定方法切断独立舵机电源；关闭PWM/拔主控USB不等于切断舵机动力。没有供电反馈或波形仪器，不能声称物理停止已验证。

## 2026-11-11 连接修复更新

以上“仅离线开发/本轮未执行真实模式”为原开发阶段记录。现已完成3次真实连接、7次PING/GET_STATUS验证（含两次完整CLI status/quit），无需更改固件；详情见SERIAL_CONNECTION_FIX.md。连接后先等待2秒，随后查询，不自动重试。无--motion-permission时stop/disarm/退出仅清理本地会话并关闭串口，不发送任何控制命令；获得运动许可的模式仍保留原STOP/DISARM策略。连接验证期间舵机动力已断开，真实标定/运动仍未进行。
