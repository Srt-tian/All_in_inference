# 来源、差异与证据边界

2026-09-18 只读核对了推理机正在使用的 inference 工作树。基准 Git commit 为：

```text
0cd690a4f02bba4f611e7e1aedc3f7eeee8ed315
```

该工作树包含未提交修改，不能用 commit 单独代表实机文件。以下是本次比对的文件 SHA-256，分别与本地保存的运行参考快照一致：

| 相对路径 | SHA-256 |
| --- | --- |
| `client/inference/action_buffers.py` | `1f44a85c2570a4d4794e9ef4dabcb04230f19779aac823a77305b2d98fa1ab30` |
| `client/inference/robot_io.py` | `8727832976b4968d12283c8cb6cdef945f1eace8e472c080c6272c464514a782` |
| `client/inference/runtime.py` | `396d6d5a2898aa54de3c7e4f45deeff055c19310e7e7f72a98adc98a512468c9` |

新仓库是接口与核心算法的重新组织实现，没有复制整个内部仓库、SDK、模型权重或私有部署配置。

| 源实现经验 | 本仓库处理 |
| --- | --- |
| `StreamActionBuffer` 重叠线性渐变 | 保留同 tick 新权重 0→1 的约定；显式 tick 对齐代替执行计数猜测 |
| 原始 `TemporalEnsemblingBuffer` 按预测次序指数加权 | 未直接移植；其正系数偏向更早预测。本仓库 ensemble 为新权重明确的 EMA |
| 某些 stream 版本的单次新旧 EMA | 整理为 `ensemble_new_weight`，明确不等价于全部历史预测的指数归一化 |
| 无重叠时扩展旧末值做 transition | 不仿造旧 horizon，改由锚点插值与速度限制衔接；数值不完全相同 |
| Piper 独立 200 Hz high-follow worker | 提炼单一命令写者、独立时钟与错过时槽处理 |
| 固定 14D 及固定 arm/gripper 索引 | 改为任意 D 的 `RobotSpec` 和具名 `JointCodec` |
| 原始 centripetal Hermite waypoint 插值 | 改为动作时间坐标下逐轴单调 Hermite；不是原实现逐点等价复刻 |
| 原控制器估算 waypoint 时长 | 新 runtime 保持策略 action_hz，通过命令速度限制保守下发；暂不动态拉伸动作时基 |
| 容易与执行耦合的日志 | 控制环仅记录有界内存，运行结束后导出 |

[RoboRSI_v1](https://github.com/Srt-tian/RoboRSI_v1) 保存了此前 Piper 连续抓取的整理结果。其真机成功不等于本仓库新抽象层已完成真机验证，也不作为新框架的通用机器人基准结果。

本仓库的验证由可运行测试和模拟测量支撑；具体结果见 [VALIDATION.md](VALIDATION.md)。第三方依赖按各自许可证使用；项目所有者尚未指定本仓库软件许可证。
