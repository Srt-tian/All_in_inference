# 开发与验证

```bash
python -m pip install -e '.[dev]'
python -m ruff check src tests scripts examples
python -m ruff format --check src tests scripts examples
python -m unittest discover -s tests -v
```

新增设备放在独立模块/包，以模拟替身覆盖状态顺序、单位转换、I/O 超时和停止；禁止在 import、构造、异常退出时自动使能/回零/断扭矩。新增调度应测试延迟与过期结果；新增融合/插值应测试离散轴、边界、极值和连续性。

修改控制环时至少验证：一个命令写者、推理阻塞不阻塞发送、无补发 burst、停止后无迟到结果恢复运动、日志容量有界。

更新框架图：

```bash
python scripts/draw_architecture.py
# 若已安装 drawio-skill，可运行其中 scripts/validate.py 检查 XML
drawio -x -f png --width 1800 -o docs/assets/architecture.png docs/assets/architecture.drawio
# 检查 PNG 排版后导出可编辑 SVG
drawio -x -f svg -e --embed-svg-images -o docs/assets/architecture.svg docs/assets/architecture.drawio
```

CI 配置位于 `ci/github-actions-tests.yml`。初始发布所用 GitHub OAuth 授权不含 workflow 写权限，因此提供可审核模板；有权限的维护者将其移到 `.github/workflows/tests.yml` 即可启用，不宣称目前 GitHub Actions 已运行。

提交中不要出现认证、机器 IP、CAN 现场部署配置、模型权重或原内部仓库的大段源码。实机运行记录提交前需脱敏，并区分主机命令频率、总线接收频率、固件伺服频率。
