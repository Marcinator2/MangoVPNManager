from types import SimpleNamespace

from gui.main_window import (
    MainWindow,
    NORMAL_STATUS_INTERVAL_MS,
    STARTUP_STATUS_POLL_COUNT,
)


class FakeTimer:
    def __init__(self) -> None:
        self.intervals: list[int] = []

    def setInterval(self, interval: int) -> None:
        self.intervals.append(interval)


def test_runtime_poll_switches_to_normal_interval_after_ten_startup_checks() -> None:
    refreshes: list[bool] = []
    window = SimpleNamespace(
        _startup_status_checks_remaining=STARTUP_STATUS_POLL_COUNT,
        status_timer=FakeTimer(),
        _refresh_runtime_status=lambda: refreshes.append(True),
    )

    for _ in range(STARTUP_STATUS_POLL_COUNT - 1):
        MainWindow._poll_runtime_status(window)

    assert len(refreshes) == 9
    assert window.status_timer.intervals == []

    MainWindow._poll_runtime_status(window)

    assert len(refreshes) == 10
    assert window._startup_status_checks_remaining == 0
    assert window.status_timer.intervals == [NORMAL_STATUS_INTERVAL_MS]
