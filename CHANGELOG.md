# Changes

## 0.2.0

- 异步方法分类为 `naive`、`temporal_smoothing`、`temporal_ensemble`、`legato` 与显式注册插件。
- 跨 chunk 融合由方法选择；同步、Naive、Legato 和自定义插件默认替换。连续插值和 200 Hz 执行仍为公共层。
- 删除 RuntimeConfig 中 `smoothing` / `ensemble_new_weight`。配置迁移到 `inference.async.method` 与 `options.new_weight`。
- 工厂默认异步方法为 `temporal_smoothing`。`basic` 为带告警的 `naive` 别名，旧配置若需渐变必须显式迁移。
- 低层 Runtime / Timeline 默认不融合，高级调用可显式注入 `ChunkFusion`。保留旧 Python 导入路径。
- 报告记录方法名称及实际融合规则；更新模拟配置、测试与 editable draw.io 框架图。

本次不包含真机验证，Legato 仍为客户端协议骨架，RTC 尚需实现。
