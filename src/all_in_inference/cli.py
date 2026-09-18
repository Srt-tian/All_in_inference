"""Simulation-only CLI. Hardware integration is an explicit Python API decision."""

import argparse
import json
from pathlib import Path

from .adapters import SimRobot, SinePolicy
from .report import export_run
from .runtime import Runtime, RuntimeConfig, RuntimeFault
from .scheduling import AsyncSchedule, SyncSchedule
from .types import Joint, RobotSpec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--output", type=Path, default=Path("outputs/demo"))
    args = parser.parse_args()
    data = json.loads(args.config.read_text(encoding="utf-8"))
    unknown = set(data) - {"robot", "initial", "runtime", "schedule", "demo_policy"}
    if unknown:
        parser.error(f"Unknown config fields: {sorted(unknown)}")
    spec = RobotSpec(data["robot"]["name"], tuple(Joint(**j) for j in data["robot"]["joints"]))
    schedule_config = dict(data.get("schedule", {}))
    kind = schedule_config.pop("kind", "async")
    if kind not in {"sync", "async"}:
        parser.error("schedule.kind must be sync or async")
    schedule = AsyncSchedule(**schedule_config) if kind == "async" else SyncSchedule()
    if kind == "sync" and schedule_config:
        parser.error("SyncSchedule takes no options")
    robot = SimRobot(spec, data["initial"])
    policy = SinePolicy(spec, data["initial"], **data.get("demo_policy", {}))
    runtime = Runtime(robot, policy, RuntimeConfig(**data.get("runtime", {})), schedule)
    status = 0
    try:
        runtime.run(args.duration)
    except KeyboardInterrupt:
        runtime.stop()
        status = 130
    except RuntimeFault as exc:
        print(f"Runtime fault: {exc}")
        status = 1
    finally:
        export_run(runtime, args.output)
    summary = runtime.summary()
    print(json.dumps({k: v for k, v in summary.items() if k != "inference_events"}, indent=2))
    print(f"Post-run report: {args.output.resolve()}")
    raise SystemExit(status)


if __name__ == "__main__":
    main()
