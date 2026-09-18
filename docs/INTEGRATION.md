# 接入模型、设备和原 inference

## 策略客户端

现有客户端只需被包装，不要求修改模型服务。

```python
from all_in_inference.adapters import CallablePolicy
from all_in_inference.codecs import JointCodec

codec = JointCodec(robot.spec, model_joint_names=[j.name for j in robot.spec.joints])
policy = CallablePolicy(
    predict_fn=client.infer,  # 客户端自身配置小于 policy_timeout 的网络 timeout
    encode_fn=lambda req: {
        "state": req.observation.position.copy(),
        "images": req.observation.sensors.get("images", {}),
    },
    decode_fn=lambda output, req: codec.decode(output["actions"], req),
)
```

具体字段必须匹配你的服务，框架不假设 OpenPI、LingBot 或其他服务共用协议。`JointCodec` 的 scale / offset 采用**模型关节顺序**，先反归一化再重排。relative 模式每一行相对于请求观测，不是累计 delta；其他 action 表示应自定义 decode。TCP / quaternion 不能直接当作关节 action 发送。

`Request.pending` 是已排队的 robot-space 未来动作。如果 RTC 服务需要原始 model-space 前缀，应由策略适配器保存其原始输出并维护映射，不能盲目把 pending 当作归一化模型动作。

## 硬件桥接

使用 `CallbackRobot(spec, read, send, hold)` 或实现同名接口。`read()` 返回 `Observation(q, timestamp, sensors)`，timestamp 必须为实际反馈采样时的单调时钟值。缓存状态读取时不要用当前时刻冒充反馈产生时刻。

`write(q)` 必须是有界、直接下发；不能在里面发起推理、同步写日志、等待相机或加入另一条平滑队列。`read()` 必须可与 write 并行；SDK 若不允许，设备插件需要使用短锁/独立反馈缓存。硬件接入、扭矩使能、CAN 配置、模式配置应在应用层显式执行。

`hold(measured)` 必须保持当前扭矩和夹爪状态。framework 的终止不代表设备连接被关闭，调用方根据设备契约管理资源；禁止通过断使能来实现通用软件停止。

## 原 inference：两种迁移路径

已参考推理机上的 `action_buffers.py`、`runtime.py` 与 `robot_io.py`，精确源文件指纹见 [PROVENANCE.md](PROVENANCE.md)。原实现有自己的 high-follow 控制 worker。

**路径 A：先只替换时间轴/平滑。** 保留原 runtime 和 high-follow writer，以原 action 频率取出新 Timeline 的值，交给原 `apply_action`。此时不要启动本仓库 `Runtime`；原 worker 仍负责实际 200 Hz、插值和停止。适合逐层做 A/B 对照。

**路径 B：使用本仓库完整 runtime。** 在应用启动阶段确认旧 high-follow worker 已退出、队列已清空，硬件已配置好；新 RobotAdapter 直接调用底层发送方法。读取源实现可知：

| 原方法 | 用途 / 注意事项 |
| --- | --- |
| `PiperArm.read_state()` | 单臂 6 关节 rad + 夹爪 m；返回 timestamp 不是本框架要求的 monotonic，需要审查并转换 |
| `PiperArm.apply_high_follow(q_ref, gripper, gripper_effort)` | 直接向 SDK 发送；可作为新 adapter 的发送入口 |
| `PiperDualArm.apply_action(action14)` | high-follow 模式下加入旧队列；不能作为本框架 200 Hz 的直接发送接口 |
| `AgilexRobotIO.get_observation()` | 会等图像与同步状态；不能放在 200 Hz 控制线程中 |

现有 `read_state()` 在部分反馈缺失时可能回退到当前 wall clock，且 aggregate timestamp 不一定证明每个关节和夹爪都新鲜。真机插件应检查每路底层消息的时间/序号，不能只对旧函数的返回值加 `time.monotonic()`。图像由独立采集器更新有时间戳的缓存。

两臂命令顺序必须由命名关节/组配置决定。左右 CAN 映射、使能状态、控制模式、夹爪 effort、设备固件和允许频率都留在本机部署配置，不提交机器地址或认证信息。

本仓库目前提供完整模拟器与通用 callback bridge，**未提供经新框架真机验收的 Piper / Franka / UR 设备插件**。可配置 6/7/14/更多维度代表软件布局兼容，不表示物理设备已全部验证。

## 从模拟到真机的最小验收

1. 用真实 joint names、单位和限位替换示例配置，验证模型输出解码与当前状态一致。
2. 对适配器做只读检查，确认时间戳新鲜、关节顺序和每路反馈有效；测量 I/O 最坏延迟。
3. 确认现场授权与停止装置后，单关节小范围、低速度验收；核对命令/反馈方向。
4. 测量设备侧接收频率、丢帧、跟踪误差、停止保持，再进行单臂与多臂任务。
5. 比较 replace / temporal / ensemble，分别统计策略延迟、过期 action 和控制 jitter。

当前整理与测试阶段没有下发任何真机动作。
