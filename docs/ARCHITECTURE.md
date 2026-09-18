# 架构与时序约定

## 数据流与线程归属

`RobotAdapter.read → Observation → Policy.predict(Request) → ActionChunk → Timeline → interpolation → SlewLimiter → RobotAdapter.write`

`Runtime.run()` 的调用线程是唯一硬件命令写入者。观察线程只读反馈；策略线程只调用模型、解码、写时间轴。两个后台线程可以阻塞在其自身有超时的 I/O 上；控制循环不等待推理。调度和模型调用在同一个策略 worker 中，保持最多一个在途请求。

`Observation.position`、`Request.pending` 和 `ActionChunk.positions` 均复制为只读数组。`sensors` 映射只读，但其 payload 必须由适配器保证不可变或独占，例如独立复制的图像；核心不在控制循环复制视频帧。

## 统一时基

runtime 启动时记单调时钟 `epoch`。时间轴坐标为 `tick=(monotonic-epoch)*action_hz`。每一 chunk 的行对应 `start_tick+i`，**不是**网络返回时刻，也不是 200 Hz 命令序号。

异步请求默认从 `floor(request_tick)+lead_steps` 开始，`lead_steps=1`。该值应符合策略对首 action 的未来时间语义，不应靠随意增大它来隐藏网络延迟。结果到达后删除所有 `tick <= floor(arrival_tick)` 的动作；已被控制器消费的 tick 同样不可覆写。若整个 horizon 过期，整包丢弃，不执行最后一个过期点。

同步模式在旧 horizon 耗尽后发起请求，到达后重新设定 `start_tick=floor(arrival_tick)+1`。适用于等待期间机器人保持的策略。异步模式不会自动补偿模型本身的状态预测误差；RTC、future-conditioned 模型要通过策略接口与调度扩展实现。

`request_id` 单调递增；较旧结果拒绝。`generation` 在 reset 时递增，旧 episode 的迟到结果拒绝。Runtime 实例单次使用，异常后新建实例，不在运动中重新初始化硬件。

## Temporal smoothing

时间轴只对**相同目标 tick** 的动作融合。`temporal` 在 `N` 个重叠 tick 上采用：

```text
w_new(i) = i / (N - 1)             N > 1
q(i) = (1 - w_new(i))*old(i) + w_new(i)*new(i)
```

单点重叠时权重为 0，遵循原 stream buffer 的约定；可选择 `replace` 或 `ensemble` 改变这一行为。`ensemble` 采用配置值 `ensemble_new_weight` 的 EMA，权重越大越偏向新预测。

`blend=false` 的轴直接采纳该目标 tick 的新值，不做新旧混合，采样时零阶保持。适合夹爪事件；若夹爪是连续位置控制，kind 设为 `prismatic`，仍经过速度限制。真正离散的模式/开关轴 kind=`discrete`，不做速度限制，设备端负责合法值校验。

新 horizon 末端之后的旧尾部被丢弃；旧值只保留在新 chunk 开始之前。容量是显式限制，超长 chunk 报错，不使用会静默弹出未执行点的队列。融合和 sample 共用短锁；大量 horizon 会增加锁占用，因此 capacity 不宜无限放大。

## 连续插值与速度限制

时间轴使用线性或单调三次 Hermite 插值。三次切线由相邻区间割线的加权调和平均得到，在极值处设零，避免各轴区间过冲。固定 knot 序列内部的一阶连续性有测试覆盖；在线更新不是全局 C1 轨迹优化器。

速度 guard 对连续轴满足 `|q_cmd-q_prev| <= max_velocity*min(dt, 1/control_hz)`。超时后不按长时间间隔跳大步。它不保证加速度或 jerk；发生限制时会落后于策略轨迹，在报告中记录 `velocity_limited_steps`。该计数持续较高时，应降低动作速度或增加策略 horizon / 重定时，不能以更大的速度上限掩盖模型输出问题。

队列耗尽时**保持最后实际下发值**，不追赶过期终点。若应用需要严格到达终点，应在策略 horizon 尾部添加足够长的常值段，并由上层基于反馈确认到位；不能用“horizon 已消费”作为任务成功信号。

## 控制时钟与停止

周期调度使用 `time.monotonic()` 和可中断 wait。错过的时槽直接跳过，不做补发 burst。记录主机 send 完成时间和 deadline lateness；硬件到达率需要设备侧时间戳另行验证。多个机械臂在一个 adapter.write 内顺序发送，不保证跨总线原子同步。

`stop()` 只设置事件。`run()` 负责退出、join worker、使旧 generation 失效和最后一次新鲜实测 hold。`stop()` 返回并不意味着已经停稳，等待 `run()` 返回才表示框架不再下发后续命令。即使驱动调用开始后收到 stop，也必须等该有界调用返回。

故障来源包括过期反馈、推理超时、horizon 长期耗尽、解码异常和适配器异常。它们传播为 `RuntimeFault`，不会静默继续。最后无法取得新鲜反馈时不发送臆测的测量保持命令，记录 fault；电机/总线自己的看门狗仍需在设备层配置。没有 `DisableArm`、reset、自动断扭矩或自动张爪逻辑。

## 扩展规则

- 新策略：实现 `predict(Request) -> ndarray[H,D]`；在此完成 payload、网络调用和机器人空间解码。
- 新异步方法：使用 `MethodPolicy` + `InferenceMethod`，返回 `Prediction`，获得整合结果反馈并保存 model-space 历史；见 [ASYNC_METHODS.md](ASYNC_METHODS.md)。Legato 协议骨架已提供。
- 新设备：实现 `spec/read/write/hold`；框架不管理 CAN 名称、URDF、使能流程。
- 新调度：实现 `ready(tick,end_tick,since_request)` 和 `result_start(requested_tick,arrival_tick)`。参考 `examples/custom_schedule.py`。
- 新平滑：在 Timeline 中新增明确的同 tick 融合规则及延迟/重置测试。
- 新实时后端：替换执行器并保留单写者、时钟、停止和遥测契约。不要在已有 runtime 下叠加第二层插值队列。

VLA RTC 的模型专用前缀屏蔽、未来状态注入、双缓冲与跨进程推理尚未实现；扩展接口不等于这些算法已经得到验证。
