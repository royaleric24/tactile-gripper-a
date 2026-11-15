# P3-B1｜重开 console 后直接闭合与再次 NUL 超时（2026-11-16）

状态：**本轮同步 1040 夹杯未完成**。新的关键证据是：**一个没有任何 PWM 命令的会话**
（`ab8d2f…`）在 `BEGIN_BENCH` 就收到含 12 个 NUL 的 ACK 并超时；同时操作者观察到重开
console 后机械爪直接合上。日志证明这次闭合**不是软件下发的 PWM 命令**。串口损坏不再只
出现在 PWM 输出期间；Test A（舵机 5V 关、信号线断开）仍是干净的。

## 1. 最近一次成功 1040 夹杯（机械成功，无 FSR 同步）

`logs/real/bench/cab80845836e496bb3955739e5fcff56/transport.jsonl`

| 项 | 结果 |
|---|---|
| 命令 / 应答 / 匹配 | **409 / 409 / 409** |
| 应答 NUL | **0** |
| `corrupt_response` / timeout / FAULT | **0 / 0 / 0** |
| PWM 序列 | 1500、1450、1500、1300、1200、1100、1000、900、1200、1150、1000、1200、1150、1100、1050、1040 |
| 最终 | **DISARMED / DISABLED_UNMEASURED / commanded=null** |

结论：这次机械夹持成功期间通信干净；但该会话**没有 FSR 同步采集**，不能算触觉同步成功。

## 2. 重开 console 后的失败会话

| 日志 | PWM 命令 | 超时前最后命令 | 损坏 RX | 结果 |
|---|---|---|---|---|
| `a1790d…` | 1500 | HEARTBEAT seq 28 | 957 B，**24 NUL** | timeout，state ACTIVE/pulse 1500 |
| `296054…` | 1500、1400 | HEARTBEAT seq 12 | 957 B，**12 NUL** | timeout，state ACTIVE/pulse 1400 |
| `ab8d2f…` | **无** | BEGIN_BENCH seq 3 | 958 B，**12 NUL** | timeout，state ARMED，fault `GRIPPER_ASSEMB< NUL >ED_AUTHORIZED` |

`ab8d2f…` 是决定性证据：

- 该会话只有 `GET_STATUS`、`GET_STATUS`、`BEGIN_BENCH` 三条命令，**没有任何
  `BENCH_HOLD`/`BENCH_PULSE`**；
- 最后一个有效 STATUS 是 `DISARMED / DISABLED_UNMEASURED / commanded=null`；
- `BEGIN_BENCH` 的 ACK 被 12 个 NUL 破坏，主机 3 s 超时；
- 因此 **重开 console 后“机械爪直接合上”不是软件 PWM 命令造成的**。它是之前
  `STOP`/`DISARM` 之后舵机失电/失持、机械弹簧或残余位置造成的机械闭合；console
  的 “Session ready; no PWM sent” 是准确的。

## 3. 串口损坏的新定位

- Test A（PM15S 5V 关闭、信号线断开）：151/151 应答、0 NUL，S3 的 PWM+UART 路径干净。
- 成功 1040 会话：409/409、0 NUL。
- 重开后的失败会话：即使 **没有 PWM 命令**（`ab8d2f`）也出现 NUL 损坏；另外两个会话在
  1500/1400 输出后损坏。
- 共同差异：**舵机连接/通电**（以及可能处于闭合/堵转/失持状态），而不是 S3 产生 PWM 本身。

因此，问题**强烈指向舵机供电/共地/线束/EMI 或闭合堵转状态**，但**没有实测证据证明供电故障**。
NUL 出现在 JSON 字符串值中间（如 `GRIPPER_ASSEMB\x00ED_AUTHORIZED`），是单字节被替换，
更像 UART 信号完整性/地弹问题，而不是 TX 缓冲区末尾截断；Test A 也排除了“纯 GPIO4 PWM +
S3 Serial/UART”这一项。

## 4. 需要修复的具体位置

### 4.1 机械/操作（不是固件命令）

- `STOP`/`DISARM` **不保证保持夹持**；舵机失电后机械爪可能因弹簧/残余位置闭合。
- 重开 console 时，S3 复位、LEDC 关闭，第一条数字命令之前不会输出 PWM；`ab8d2f` 已证明
  没有 PWM 命令。
- 处理：若需要保持张开，**不要在 1040 后 `stop`/退出**；先回到 1500 并保持会话，
  或物理支撑/手动张开机械爪。重开后第一条命令是 1500，但必须等串口链路稳定后再试。
- **不需要**为此修改固件或增加自动开爪（自动 PWM 被禁止）。

### 4.2 电气（优先测量，不先归因）

需要现场实测：

1. 舵机独立 5V 在 idle、1500、1040、闭合/堵转时的电压与电流；
2. S3 GND 与舵机 5V GND 的电位差、共地点/地环路；
3. 5V 电源容量、体电容（如 470–1000 µF）、接插件接触；
4. 舵机电源线与 USB/UART 线的走向/屏蔽；
5. 信号线串联电阻/电平与地回流路径。

可尝试的最小电气整改：独立 5V 供电、**单点共地**、舵机端加体电容、动力线与 UART/USB 分开、
信号线加串联电阻。**没有测量前不得直接写“供电故障”**。

### 4.3 固件/主机

- 不改固件：Test A 已证明 S3 PWM+UART 在舵机隔离时干净；`ab8d2f` 还证明损坏可在无 PWM
  命令时发生，进一步削弱“PWM 生成代码”假设。
- 不自动重试 PWM、不扩大超时、不改 PWM 范围。
- 心跳/只读命令的重试只能作为临时缓解，不能替代电气根因；当前未实现。

## 5. 下一次最小验证方案（不执行）

在完成上述电气检查/整改后，按以下顺序，每步只改一个变量：

1. **舵机通电、但无 PWM 命令、机械爪张开/有支撑**：
   `GET_STATUS → BEGIN_BENCH → BENCH_HOLD_MODE → 20× HEARTBEAT → STATUS → DISARM`。
   - 若仍出现 NUL → 舵机通电/5V/地/线束本身在干扰 UART；
   - 若干净 → 问题与闭合/堵转状态或 PWM 负载相关。
2. **舵机通电、机械空载、只发 1500**：60× HEARTBEAT，观察是否复现。
3. **1500 → 1040，机械空载**：60× HEARTBEAT；若干净，再做有杯 1040 + FSR 同步。
4. 每步记录 5V/地电位/电流；若出现 NUL/失稳，立即停止并保存数据。

在串口链路稳定前，不继续 1040 夹杯、不自动重试 PWM、不改范围。

## 6. 本轮数据（失败，未标记成功）

- console 日志：`a1790d…`、`296054…`、`ab8d2f…`，以及成功 1040 的 `cab808…`；
  证据包 `evidence/p3b1/private/rerun_timeout_20261116/summary.json`。
- FSR：`evidence/p3b1/private/cup_1040_sync_20261115T175105Z/`
  - 15,909 SAMPLE、100% valid、257.67 s
  - min −126,287 / max 159,253 counts；`0x04` 5,258；无饱和
  - capture 起点 17:51:18Z，在成功 1040 会话结束（17:49:47Z）之后，覆盖的是失败的重开会话，
    **不是成功 1040 夹持的 FSR 曲线**；本轮不标记为空杯/触觉同步成功。
- 本轮未修改固件、Dashboard、FSR、PWM 范围；未自动重试。

## 7. 当前判定

| 项 | 状态 |
|---|---|
| 成功 1040 机械夹持 | **VERIFIED_REAL（操作者观察；console 409/409、0 NUL）** |
| 1040 + FSR 同步 | **NOT_TESTED / 未成功** |
| 重开直接闭合 | **不是 PWM 命令（ab8d2f 无 PWM）；机械失持/残余位置（VERIFIED_REAL 日志）** |
| 重开后的 timeout 直接原因 | **ACK NUL 损坏（a1790d 24、296054 12、ab8d2f 12）** |
| NUL 机制 | **LEADING_HYPOTHESIS：舵机通电/5V/地/线束或闭合堵转；未证实，需测量** |
| S3 PWM+UART（舵机隔离） | **Test A PASS，151/151、0 NUL** |
| 固件/范围修改 | **未修改；不自动重试 PWM** |
