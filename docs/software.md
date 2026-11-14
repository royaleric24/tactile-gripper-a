# 主机软件

main 的 src/gripper_a/ 和 scripts/pwm_console.py 提供控制板通信及人工控制台。软件组分支扩展 src/tactile_gripper/，安装和启动命令见 README。

| 模块 | 职责 |
|---|---|
| protocol.py、models.py | 将原始帧解析为带来源、时钟与有效位的数据模型 |
| devices/ | 适配传感器和夹爪，管理串口与模拟输入 |
| control/core.py、control/auto.py | 管理状态转换、动作权限和离线 AUTO 策略 |
| ui/ | 中文监控、实验管理、回放与对比 |
| experiments/store.py | 按 Trial 保存 metadata.json、frames.jsonl、events.jsonl，支持 CSV 导出和恢复 |

各入口的来源标签随数据保存。模拟演示使用 scripts/run_simulation_demo.py；软件分支 docs/DATA_FORMAT_V1.md 和 docs/DASHBOARD_QUICKSTART_ZH.md 分别说明存储格式及界面操作。真实双板联调时先比对握手与帧语义，再评估控制路径。
