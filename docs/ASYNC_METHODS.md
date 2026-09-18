# 异步方法扩展：Legato、RTC 与其他协议

## 模式入口与插件注册

```python
from all_in_inference.inference import create_runtime, register_async_method

# 同步：没有异步方法选项
runtime = create_runtime(robot, policy=policy, inference={"mode": "sync"})

# 基础异步：普通 Policy
runtime = create_runtime(robot, policy=policy, inference={
    "mode": "async", "async": {"method": "basic", "inference_hz": 5},
})

# Legato：方法插件负责请求构造和解码，transport 负责通信
runtime = create_runtime(robot, transport=client.infer, inference={
    "mode": "async", "async": {
        "method": "legato", "inference_hz": 5,
        "options": {"chunk_size": 50, "ramp_down": 22},
    },
})

# MyRTCMethod 由应用实现，继承 InferenceMethod；不代表内置 RTC 已实现
register_async_method("my_rtc", MyRTCMethod)
```

CLI 的示例配置统一改用 `inference.mode` 和 `inference.async`，旧的顶层 `schedule` 配置需迁移。同步模式带 async 配置会报错，未知异步方法也会报错，绝不静默回退。CLI 仍只运行模拟 Basic/Sync；带服务器的方法由 Python API 显式注入 transport。

方法插件可在 options 中接收自定义编解码回调（Python API）；配置文件不能自动导入或执行任意插件代码。需要自定义底层调度器时，仍可显式组合 `Runtime`，但推荐业务入口使用上述模式层级。

公开入口先选择同步 / 异步模式，再在异步模式下选择 Basic、Legato 或注册的方法。内部调度器负责请求时机，方法插件负责协议与历史，均不拥有机器人写权限。

```text
Schedule.ready
  → Request（request_tick / pending / generation）
  → MethodPolicy → InferenceMethod.build_payload(request, history)
  → transport（SDK / HTTP / WebSocket，自带 timeout）
  → InferenceMethod.decode → Prediction(positions, actions_model)
  → Schedule.result_start → Timeline.integrate
  → IntegrationFeedback → InferenceMethod.on_integrated
```

接口实现位于 `inference/contracts.py`，异步插件位于 `inference/async_methods/`；旧 `methods.py` 保留导入兼容：

| 接口 | 用途 |
| --- | --- |
| `reset(generation)` | 清除方法内部缓存及延迟估计，避免跨 episode 泄漏 |
| `build_payload(request, history)` | 注入模型前缀、延迟、future state 或自定义参数 |
| `decode(output, request)` | 分开解码 robot-space 执行动作和 model-space 原始动作 |
| `on_integrated(request, prediction, feedback)` | 获得真实接受/丢弃数量、原因、到达时间和输出起点 |
| `MethodHistory` | 最近一次被接受结果及其完整时间归属，保留原始 model-space horizon |

已有 `Policy.predict -> ndarray` 仍兼容；方法插件可返回 `Prediction`。`positions` 的维数必须符合 RobotSpec；`actions_model` 的 H/D 可以不同，不被机械臂 codec 重排或截断。MethodPolicy 仅在接受至少一个 action 后更新历史；整包过期、乱序或 generation 失效不会替换历史。所有 hook 在策略 worker 执行，慢 hook 仍受 runtime 推理 deadline 约束。

## Legato 协议接线

```python
from all_in_inference import Runtime, AsyncSchedule
from all_in_inference.methods import LegatoProtocol, MethodPolicy

method = LegatoProtocol(
    chunk_size=50,
    ramp_down=22,
    expected_model_shape=(50, model_action_dim),
    encode_observation=lambda req: {
        "state": req.observation.position.copy(),
        "images": req.observation.sensors.get("images", {}),
    },
    decode_actions=lambda out, req: codec.decode(out["actions"], req),
)
policy = MethodPolicy(client.infer, method)
runtime = Runtime(robot, policy, schedule=AsyncSchedule(inference_hz=5))
```

`LegatoProtocol` 是**客户端协议接线骨架**，不是 Legato 算法、模型或服务端实现，也未声称完成 Legato 真机复现。它参照本地 inference 镜像的 `LegatoMode` 字段约定；该镜像未被认定为当前远程工作树的权威版本。实际接入前必须核对所部署服务器的协议。

- `inference_delay`：最近一次完成推理的耗时乘 action_hz 向上取整，截断到 chunk_size；首次为零。
- `execute_horizon`：上一次被接受 chunk 从其 output_start_tick 起到本次请求时已过去的 action tick 数，加估计 delay，再截断。这里是**时间轴进度**，不是机械臂实际到达点数，也不是原系统队列 pop 计数；有不同语义的服务器需覆盖 build_payload。
- `prev_action_chunk_model`：上一次被接受结果的完整 model-space action，保留被丢弃前缀，配合原始起点表达进度。不能用 robot-space pending 冒充。
- `ramp_down`：客户端协议参数，原样传递；本地 smoothing 不实现服务端 ramp 算法。
- `expected_model_shape` 配置后严格验证，缺失或不符会报错；未配置时允许服务端不返回 actions_model。

Legato/RTC 可能已在模型侧处理连续性，接入时先对照 `smoothing="replace"`，避免与本地 temporal 再次融合产生额外滞后。应基于服务端语义和实验选择，框架不自动切换。

## 其他方法

RTC 的模型前缀 masking、future-conditioned 的未来状态、TT-RTC 的原子前缀提交，可各自实现 InferenceMethod，再搭配 Schedule。当前只有一个在途请求；多在途乱序合并、服务端取消和带前缀承诺的原子事务**仍需专门实现与测试**。接口预留不代表这些算法已经实现。

停止后的迟到结果不会触发新整合；插件不得启动脱离 runtime 生命周期的硬件写线程，也不能修改控制时钟。
