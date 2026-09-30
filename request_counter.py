"""Ежедневный счётчик пользовательских обращений к боту."""

import asyncio
import csv
import json
import logging
import threading
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from maxapi.enums.update import UpdateType
from maxapi.filters.middleware import BaseMiddleware, HandlerCallable


logger = logging.getLogger(__name__)

COUNTED_UPDATE_TYPES = {
    UpdateType.MESSAGE_CREATED,
    UpdateType.MESSAGE_CALLBACK,
    UpdateType.BOT_STARTED,
}


class DailyRequestCounter:
    """Считает обращения и раз в сутки сохраняет итог в CSV-файл."""

    def __init__(
        self,
        logs_dir: Path,
        timezone_name: str = "Asia/Krasnoyarsk",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.logs_dir = Path(logs_dir)
        self.timezone = ZoneInfo(timezone_name)
        self._now_provider = now_provider
        self._state_path = self.logs_dir / ".request_counter_state.json"
        self._lock = threading.Lock()
        self._current_date: date | None = None
        self._count = 0

    def _now(self) -> datetime:
        if self._now_provider is not None:
            return self._now_provider()
        return datetime.now(self.timezone)

    def _load_state(self, today: date) -> None:
        if self._current_date is not None:
            return

        try:
            state = json.loads(self._state_path.read_text(encoding="utf-8"))
            self._current_date = date.fromisoformat(state["date"])
            self._count = int(state["count"])
        except FileNotFoundError:
            self._current_date = today
            self._count = 0
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            logger.warning(
                "Не удалось прочитать состояние счётчика %s; начинаю новый день",
                self._state_path,
            )
            self._current_date = today
            self._count = 0

    def _save_state(self) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = self._state_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(
                {"date": self._current_date.isoformat(), "count": self._count},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        temporary_path.replace(self._state_path)

    def _month_path(self, day: date) -> Path:
        return self.logs_dir / str(day.year) / f"{day.month:02d}.csv"

    def _append_day(self, day: date, count: int) -> None:
        path = self._month_path(day)
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            with path.open("r", encoding="utf-8", newline="") as log_file:
                rows = csv.reader(log_file)
                if any(row and row[0] == day.isoformat() for row in rows):
                    return

        is_new_file = not path.exists() or path.stat().st_size == 0
        with path.open("a", encoding="utf-8", newline="") as log_file:
            writer = csv.writer(log_file)
            if is_new_file:
                writer.writerow(["date", "requests"])
            writer.writerow([day.isoformat(), count])

    def _rollover_if_needed(self, today: date) -> None:
        self._load_state(today)
        if self._current_date >= today:
            return

        day_to_write = self._current_date
        count_to_write = self._count
        while day_to_write < today:
            self._append_day(day_to_write, count_to_write)
            day_to_write += timedelta(days=1)
            count_to_write = 0

        self._current_date = today
        self._count = 0
        self._save_state()

    def increment(self) -> None:
        """Учитывает одно пользовательское обращение."""
        with self._lock:
            today = self._now().date()
            self._rollover_if_needed(today)
            self._count += 1
            self._save_state()

    def rollover(self) -> None:
        """Записывает итоги завершившихся дней, включая дни простоя."""
        with self._lock:
            self._rollover_if_needed(self._now().date())

    async def run(self) -> None:
        """Фоновый цикл, фиксирующий итог вскоре после полуночи."""
        while True:
            try:
                self.rollover()
            except Exception:
                logger.exception("Не удалось записать суточную статистику запросов")

            now = self._now()
            next_midnight = datetime.combine(
                now.date() + timedelta(days=1),
                time.min,
                tzinfo=self.timezone,
            )
            await asyncio.sleep(max((next_midnight - now).total_seconds(), 1))


class RequestCounterMiddleware(BaseMiddleware):
    """Подключает счётчик ко всем пользовательским событиям MAX."""

    def __init__(self, counter: DailyRequestCounter) -> None:
        self.counter = counter

    async def __call__(
        self,
        handler: HandlerCallable,
        event_object: Any,
        data: dict[str, Any],
    ) -> Any:
        if getattr(event_object, "update_type", None) in COUNTED_UPDATE_TYPES:
            try:
                self.counter.increment()
            except Exception:
                logger.exception("Не удалось учесть обращение к боту")

        return await handler(event_object, data)
