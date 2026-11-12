# Stage 0.8 串口测试协议 v1

固件 serial-test-0.8.0，仅 UART0 Serial（USB CP210x 桥），115200 / 8N1。JSONL：单行最多 512 字节（不含 LF），request_id 为 1–64 字节字符串；请求 protocol_version=1、command=PING 或 GET_STATUS。回复含 protocol_version、request_id、type、firmware_version；PING→PONG，GET_STATUS→STATUS（state、uptime_ms、chip_model、flash_bytes、motion_enabled=false）。不实现任何运动命令。

错误：INVALID_JSON、INVALID_REQUEST_ID、INVALID_ENVELOPE、UNKNOWN_COMMAND、FRAME_TOO_LONG、INCOMPLETE_FRAME_TIMEOUT。能读取合法 ID 时原样返回；非法 JSON、超长行无法可靠提取 ID，返回 request_id=null，不能伪造关联。完整错误帧需要换行；半帧闲置超过 1000ms 报错并清空。

接收缓存固定大小，每轮最多处理 64 字节。没有 GPIO 配置、PWM、舵机库或自动回中。串口输出可能受驱动缓冲背压影响；本测试不作为后续实时运动固件。当前参数在 config/serial_test.json，固件常量与其同步记录，变更需测试。

Python 客户端仅显式 connect 开串口，设置读/写/请求超时，不自动重连。按版本、固件版本及 request_id 过滤；启动文本、无关 JSON、错 ID 和超长回复仅记录，不能判作 PONG。读写失败或超时记录异常并关闭连接。控制器 SerialGripper 仍禁用；此通信客户端不能用于驱动爪。

真实日志用 REAL_SERIAL，模拟测试用 SIMULATED；REAL_SERIAL 仅指真实串口，不是舵机或闭环 Trial。日志保存 UTC/单调时间、TX/RX 原始十六进制、匹配响应和错误。

固件写入前必须保留备份文件大小、SHA-256、芯片/Flash 检测与构建版本。读取 Flash 会进入下载模式并复位，备份不包含不可读取的 eFuse；加密/安全启动可能影响恢复。覆盖只允许用户明确授权的扇区，不执行整片擦除。备份失败不得自动上传。
