# 验证记录：2026-09-18

本页记录的是本仓库新框架的**软件与模拟验证**，没有本次真机执行结果。

模式层级调整后：共 37 项测试通过，新增 Sync / Basic Async / Legato 构造、自定义方法注册与非法组合拒绝覆盖；迁移后的同步、异步 JSON 示例 CLI 均完成模拟冒烟验证。历史 timing 表不作为此次重构后的重新测量。

后续接口迭代：加入方法生命周期和 Legato 协议骨架，新增 5 项模型空间隔离、时间字段、过期结果不更新历史、generation 重置、runtime 接线测试；Python 3.10 环境共 32 项通过。下列四构型 timing 表保留初始版本的原始测量，不冒充接口迭代后的新 benchmark。

## 安装与测试

- 独立 Python 3.10 环境完成 editable 构建/安装，NumPy 2.2.6；已安装的 `all-in-inference` CLI 成功运行。
- 27 项 unittest 全部通过；核心 24 项还在 Python 3.14.6 / NumPy 2.5.2 环境通过。后追加的 3 项故障测试在 Python 3.10 环境通过。
- Ruff lint 和 format 检查通过。
- 模型客户端桥接示例运行通过，无网络/硬件访问。
- draw.io XML 验证 0 error / 0 warning；PNG 人工视觉检查后导出 SVG。

测试涵盖同 tick 渐变与 EMA、过期前缀与整包丢弃、乱序/跨 generation 拒绝、已消费点不可覆写、旧尾部移除、离散轴事件、三次极值与内部切线连续性、单位和关节顺序、速度步长、任意维数、单写者、同步/异步时间语义、慢策略、过期反馈、推理超时、缺 action 超时、worker 未及时退出、停止后迟到结果不能恢复下发、有界日志及慢写跳过时槽。

## 已安装入口的模拟测量

四组分别运行 3 秒，配置目标 control_hz=200、action_hz=25、observation_hz=50。模拟器是理想位置回写，不模拟动力学、CAN 或真实固件。运行在普通共享工作站上，不是实时内核基准。

| 配置 | 动作维数 | 调度 | 实测主机 Hz | 周期间隔 P99 ms | 最大间隔 ms | 跳过时槽 | fault |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| single6_async | 7 | async | 200.015 | 5.447 | 5.794 | 0 | 无 |
| dual6_async | 14 | async | 200.037 | 5.315 | 5.787 | 0 | 无 |
| single7_sync | 8 | sync | 200.051 | 5.305 | 5.527 | 0 | 无 |
| mixed_async | 5 | async | 200.010 | 5.312 | 7.497 | 0 | 无 |

可审阅的完整配置、各次推理延迟/丢弃和统计：[simulation_20260918.json](validation/simulation_20260918.json)。单次均记录 601 条主机命令，包含起始时刻；频率以实际相邻发送完成时刻计算，不用 command_count / 请求时长估算。

存在启动/切换期 velocity-limited steps，说明速度 guard 实际参与，不代表跟踪误差为零。同步模式推理间隙出现 underrun 是设计内的保持行为。即使平均频率接近 200 Hz，最大间隔仍可超过 5 ms；这些数据不证明硬实时保证。

## 复现命令

```bash
python -m unittest discover -s tests -v
python -m ruff check src tests scripts examples
python -m ruff format --check src tests scripts examples
all-in-inference --config examples/dual6_async.json --duration 3 --output outputs/check
python examples/policy_bridge.py
```

不同机器和负载会产生不同 jitter；应保留自身 summary 与设备侧反馈时间戳。碰撞、加速度/jerk、设备看门狗、抓取成功率和跨机械臂实机迁移未在此验证。
