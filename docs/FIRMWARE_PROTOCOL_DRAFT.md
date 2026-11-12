# 上位机与 ESP32 协议草案（未实现、不可发送）

版本：Stage 0.7 草案。不是现有固件已支持的协议，不包含上传或端口操作。

上位机 SerialTransport 设计：显式 connect、send、receive_line、close；连接配置含 port/baudrate、read/write_timeout、RTS/DTR 策略。导入和构造时不得开端口。当前 SerialGripper 构造直接报错，不加载 pyserial。串口参数仍未知；未来读取需有界缓冲、最大帧长度、分包/粘包处理，日志和串口阻塞不得延迟安全检查。

拟议 UTF-8 JSONL 消息字段：version、session_id、command_id、type、payload、关联 frame_id。类型为 HELLO、STATUS、ARM、SET_TARGET、STOP、HOLD、RELEASE、DISABLE_PWM、HEARTBEAT。精确字段类型和兼容规则待联调冻结，暂不生成可发出的数据。波特率/时限/PWM 由验证后的配置确定。

命令与回复：一次至多一个未确认目标；回复包含同一 session_id/command_id 和 ACCEPTED/REJECTED/OUTPUT_SET、reason。OUTPUT_SET 只说明输出设定，不等于机械到位。绝对目标与重复 ID 幂等处理；旧会话、乱序、无效帧不得执行或刷新动作租约。复位清空会话与队列，不恢复运动。

固件默认 DISARMED 且不输出 PWM、不自动回中。ARM 要求完整配置和显式许可。板端独立检查限幅、累计幅度、速率、命令租约及通信超时；心跳不能无限延长旧动作。解析必须有界，检查点不能被串口读写无限阻塞。板端代码尚未实现或验证。

STOP 语义首先撤销待处理闭合并拒绝继续闭合；其实际输出策略需另行确认：

| 操作 | 含义与局限 |
|---|---|
| INHIBIT_CLOSING | 禁止后续闭合命令；不能证明当前电机已经停止 |
| HOLD / RELEASE | 尝试保持目标或释放；是独立动作，须确认策略/授权，保持最后目标仍可能运动 |
| DISABLE_PWM | 关闭信号；可能失去保持力，不能保证保持杯子或安全释放 |
| 人工切断舵机电源 | 独立现场动作，可能掉落负载；需预先支撑与核对，不伪装成远程 API |

状态机原型：DISARMED → 显式 start → READY → 新鲜有效低接触帧触发 CLOSING_STEP；接触阈值触发 CONTACT_STOP；异常/超时/限幅进入 FAULT，禁止自动恢复；人工 stop 进入 STOPPED；CONTACT_STOP 下单独授权 release 只产生 RELEASE_REQUESTED，不冒充已释放。当前只绑定 FakeGripper，没有板端超时/ACK/真实保持策略实现。
