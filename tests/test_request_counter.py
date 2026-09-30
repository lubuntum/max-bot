import asyncio
import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from maxapi.enums.update import UpdateType

from request_counter import DailyRequestCounter, RequestCounterMiddleware


class MutableClock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class DailyRequestCounterTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.logs_dir = Path(self.temp_dir.name) / "logs"
        self.timezone = ZoneInfo("Asia/Krasnoyarsk")
        self.clock = MutableClock(
            datetime(2026, 12, 31, 23, 59, tzinfo=self.timezone)
        )
        self.counter = DailyRequestCounter(
            self.logs_dir,
            now_provider=self.clock,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_writes_previous_day_to_year_and_month_file(self):
        self.counter.increment()
        self.counter.increment()

        self.clock.value = datetime(2027, 1, 1, 0, 1, tzinfo=self.timezone)
        self.counter.rollover()

        path = self.logs_dir / "2026" / "12.csv"
        with path.open(encoding="utf-8", newline="") as log_file:
            rows = list(csv.reader(log_file))

        self.assertEqual(
            [["date", "requests"], ["2026-12-31", "2"]],
            rows,
        )

    def test_restores_count_after_restart_without_duplicate_rows(self):
        self.counter.increment()
        restored_counter = DailyRequestCounter(
            self.logs_dir,
            now_provider=self.clock,
        )
        restored_counter.increment()

        self.clock.value = datetime(2027, 1, 1, 0, 1, tzinfo=self.timezone)
        restored_counter.rollover()
        restored_counter.rollover()

        path = self.logs_dir / "2026" / "12.csv"
        with path.open(encoding="utf-8", newline="") as log_file:
            rows = list(csv.reader(log_file))

        self.assertEqual(1, rows.count(["2026-12-31", "2"]))

    def test_middleware_counts_only_user_requests(self):
        counter = Mock()
        middleware = RequestCounterMiddleware(counter)

        async def handler(event, data):
            return "handled"

        result = asyncio.run(
            middleware(
                handler,
                SimpleNamespace(update_type=UpdateType.MESSAGE_CREATED),
                {},
            )
        )
        asyncio.run(
            middleware(
                handler,
                SimpleNamespace(update_type=UpdateType.BOT_REMOVED),
                {},
            )
        )

        self.assertEqual("handled", result)
        counter.increment.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
