"""One command writer, one observer, one policy worker. No I/O logging in the control loop."""

import math
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass

import numpy as np

from .control import SlewLimiter
from .methods import IntegrationFeedback, Prediction
from .scheduling import AsyncSchedule, Schedule
from .timeline import Timeline
from .types import ActionChunk, Observation, Policy, Request, RobotAdapter


class RuntimeFault(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeConfig:
    action_hz: float = 25.0
    control_hz: float = 200.0
    observation_hz: float = 50.0
    interpolation: str = "cubic"
    lead_steps: int = 1
    buffer_capacity: int = 512
    state_timeout: float = 0.25
    policy_timeout: float = 3.0
    underrun_timeout: float = 4.0
    worker_join_timeout: float = 1.0
    trace_capacity: int = 120_000

    def __post_init__(self):
        for key in (
            "action_hz",
            "control_hz",
            "observation_hz",
            "state_timeout",
            "policy_timeout",
            "underrun_timeout",
            "worker_join_timeout",
        ):
            value = getattr(self, key)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be finite and positive")
        for key in ("lead_steps", "buffer_capacity", "trace_capacity"):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ValueError(f"{key} must be a positive integer")
        if self.control_hz < self.action_hz:
            raise ValueError("control_hz must be >= action_hz")
        if self.interpolation not in {"linear", "cubic"}:
            raise ValueError("Unknown interpolation")


class Runtime:
    def __init__(
        self,
        robot: RobotAdapter,
        policy: Policy,
        config=None,
        schedule: Schedule | None = None,
        *,
        fusion=None,
    ):
        self.robot, self.policy = robot, policy
        self.config = config or RuntimeConfig()
        self.schedule = schedule or AsyncSchedule()
        self.timeline = Timeline(robot.spec, capacity=self.config.buffer_capacity, fusion=fusion)
        self.inference_label = {"mode": "custom", "method": None}
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._observation: Observation | None = None
        self._inflight: float | None = None
        self._faults: list[str] = []
        self._used = False
        self._trace = deque(maxlen=self.config.trace_capacity)
        self._events = deque(maxlen=2048)
        self._dropped_trace = 0
        self._dropped_events = 0
        self._commands = 0
        self._missed = 0
        self._limited = 0

    def stop(self):
        """Signal only. run() owns joining, buffer invalidation and the final hold."""
        self._stop.set()

    def _fault(self, message):
        with self._lock:
            self._faults.append(message)
        self._stop.set()

    def _checked_observation(self, obs):
        if self.robot.spec.validate(obs.position).ndim != 1:
            raise ValueError("Observation position must be a vector")
        age = time.monotonic() - obs.timestamp
        if not math.isfinite(age) or age < -0.001 or age > self.config.state_timeout:
            raise RuntimeFault("State is stale or uses a different clock")
        return obs

    def _observe(self):
        try:
            while not self._stop.is_set():
                obs = self._checked_observation(self.robot.read())
                with self._lock:
                    self._observation = obs
                self._stop.wait(1 / self.config.observation_hz)
        except Exception as exc:
            self._fault(f"observation: {type(exc).__name__}: {exc}")

    def _infer(self, epoch):
        request_id, last_request = 0, -math.inf
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                tick = (now - epoch) * self.config.action_hz
                if not self.schedule.ready(tick, self.timeline.end_tick(), now - last_request):
                    self._stop.wait(0.002)
                    continue
                with self._lock:
                    obs = self._observation
                    if self._stop.is_set():
                        return
                    self._inflight = now
                self._checked_observation(obs)
                start_tick = math.floor(tick) + self.config.lead_steps
                req = Request(
                    obs,
                    request_id,
                    self.timeline.generation,
                    start_tick,
                    self.config.action_hz,
                    self.timeline.pending(tick),
                    request_tick=tick,
                )
                last_request = now
                output = self.policy.predict(req)
                prediction = output if isinstance(output, Prediction) else Prediction(output)
                arrived = time.monotonic()
                if self._stop.is_set():
                    return  # late network response can never resurrect motion
                if arrived - now > self.config.policy_timeout:
                    raise RuntimeFault("Policy deadline exceeded")
                arrival_tick = (arrived - epoch) * self.config.action_hz
                output_start = self.schedule.result_start(start_tick, math.floor(arrival_tick) + 1)
                result = self.timeline.integrate(
                    ActionChunk(prediction.positions, output_start, request_id, req.generation),
                    arrival_tick,
                )
                hook = getattr(self.policy, "on_integrated", None)
                if hook is not None and not self._stop.is_set():
                    hook(
                        req,
                        prediction,
                        IntegrationFeedback(
                            output_start,
                            arrival_tick,
                            arrived - now,
                            result.accepted,
                            result.dropped,
                            result.reason,
                        ),
                    )
                event = {
                    "request_id": request_id,
                    "latency_s": arrived - now,
                    "requested_tick": start_tick,
                    "output_start_tick": output_start,
                    "arrival_tick": arrival_tick,
                    **asdict(result),
                }
                with self._lock:
                    if len(self._events) == self._events.maxlen:
                        self._dropped_events += 1
                    self._events.append(event)
                    self._inflight = None
                request_id += 1
        except Exception as exc:
            self._fault(f"policy: {type(exc).__name__}: {exc}")

    def run(self, duration: float):
        """Blocking finite run; caller thread is the only command writer.

        Adapters must bound driver calls. Python cannot preempt a blocked CAN/SDK call.
        A runtime is single-use; create a new one after correcting a fault.
        """
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("duration must be finite and positive")
        if self._used:
            raise RuntimeError("Runtime is single-use")
        self._used = True
        if self._stop.is_set():
            return self.summary()
        initial = self._checked_observation(self.robot.read())
        self._observation = initial
        self.timeline.reset(initial.position)
        limiter = SlewLimiter(self.robot.spec, initial.position)
        epoch = time.monotonic()
        observer = threading.Thread(target=self._observe, name="aii-observer", daemon=True)
        worker = threading.Thread(target=self._infer, args=(epoch,), name="aii-policy", daemon=True)
        period = 1 / self.config.control_hz
        deadline = epoch
        last_send = epoch - period
        starved_since = None
        observer.start()
        worker.start()
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                if now - epoch >= duration:
                    break
                if self._stop.wait(max(0, deadline - now)):
                    break
                now = time.monotonic()
                with self._lock:
                    obs, inflight = self._observation, self._inflight
                self._checked_observation(obs)
                if inflight is not None and now - inflight > self.config.policy_timeout:
                    raise RuntimeFault("Policy deadline exceeded")
                target, starved = self.timeline.sample(
                    (now - epoch) * self.config.action_hz, self.config.interpolation
                )
                if starved:
                    starved_since = now if starved_since is None else starved_since
                    if now - starved_since > self.config.underrun_timeout:
                        raise RuntimeFault("Action horizon exhausted beyond underrun_timeout")
                    # Underrun means hold the last SENT command, not catch up to an old target.
                    target = limiter.position.copy()
                else:
                    starved_since = None
                # Do not take a large jump after an OS scheduling stall.
                dt = min(period, max(1e-9, now - last_send))
                command = limiter.step(target, dt)
                if self._stop.is_set():
                    break
                self.robot.write(command)
                sent = time.monotonic()
                self._commands += 1
                if len(self._trace) == self._trace.maxlen:
                    self._dropped_trace += 1
                self._trace.append(
                    (
                        sent - epoch,
                        max(0, now - deadline),
                        starved,
                        command.copy(),
                        obs.position.copy(),
                    )
                )
                last_send = now
                deadline += period
                if deadline <= sent:
                    skipped = math.floor((sent - deadline) / period) + 1
                    self._missed += skipped
                    deadline += skipped * period  # skip missed slots; never send a catch-up burst
        except Exception as exc:
            self._fault(f"control: {type(exc).__name__}: {exc}")
        finally:
            self._stop.set()
            # No worker may write hardware. Only this owner performs the final hold.
            observer.join(self.config.worker_join_timeout)
            worker.join(self.config.worker_join_timeout)
            if observer.is_alive() or worker.is_alive():
                self._fault("Worker did not exit; transport timeout contract was violated")
            with self._lock:
                latest = self._observation
            self.timeline.reset(limiter.position)
            try:
                # Read once after observer has exited; otherwise rely on the freshness gate.
                if not observer.is_alive():
                    latest = self.robot.read()
                latest = self._checked_observation(latest)
                self.robot.hold(latest.position.copy())
            except Exception as exc:
                self._fault(f"Final measured hold unavailable: {type(exc).__name__}: {exc}")
            self._limited = limiter.limited_steps
        if self._faults:
            raise RuntimeFault("; ".join(self._faults))
        return self.summary()

    def summary(self):
        """Read after run(); percentiles cover the retained trace window."""
        times = np.array([row[0] for row in self._trace])
        intervals = np.diff(times)
        with self._lock:
            events, faults = list(self._events), list(self._faults)
        return {
            "config": asdict(self.config),
            "robot": self.robot.spec.name,
            "schedule": type(self.schedule).__name__,
            "inference": dict(self.inference_label),
            "chunk_fusion": asdict(self.timeline.fusion),
            "commands": self._commands,
            "retained_samples": len(times),
            "dropped_trace_samples": self._dropped_trace,
            "dropped_events": self._dropped_events,
            "skipped_control_slots": self._missed,
            "velocity_limited_steps": self._limited,
            "measured_hz": float(1 / intervals.mean()) if len(intervals) else None,
            "interval_p99_ms": float(np.percentile(intervals, 99) * 1000)
            if len(intervals)
            else None,
            "interval_max_ms": float(intervals.max() * 1000) if len(intervals) else None,
            "underrun_samples": sum(int(r[2]) for r in self._trace),
            "faults": faults,
            "inference_events": events,
        }

    def trace(self):
        """Post-run copy for reporting. Never call concurrently with run()."""
        return [
            (t, lateness, starved, q.copy(), obs.copy())
            for t, lateness, starved, q, obs in self._trace
        ]
