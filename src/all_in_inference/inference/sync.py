"""Synchronous chunk consumption mode."""


class SyncSchedule:
    """Consume one horizon, then infer. Rebase returned actions to arrival time.

    Robot holds its last command while policy is busy; the 200 Hz writer never blocks
    on predict(). Useful for policies whose first action is relative to a static state.
    """

    def ready(self, tick, end_tick, since_request):
        return tick >= end_tick

    def result_start(self, requested_tick, arrival_tick):
        return arrival_tick
