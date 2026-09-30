"""
Бот-расписание для школы в MAX
Запуск: python bot.py
"""

import asyncio
from contextlib import suppress

from maxapi import Bot
from message_handler import dp
from config import MAX_TOKEN, REQUEST_LOG_DIR, REQUEST_LOG_TIMEZONE
from request_counter import DailyRequestCounter, RequestCounterMiddleware


async def main():
    print("🤖 Бот запущен!")

    request_counter = DailyRequestCounter(
        REQUEST_LOG_DIR,
        timezone_name=REQUEST_LOG_TIMEZONE,
    )
    dp.register_outer_middleware(RequestCounterMiddleware(request_counter))

    # Создаем экземпляр бота
    bot = Bot(token=MAX_TOKEN)

    # Удаляем вебхук, если он был установлен (для polling режима)
    await bot.delete_webhook()

    # Запускаем polling и суточную запись статистики
    counter_task = asyncio.create_task(request_counter.run())
    try:
        await dp.start_polling(bot)
    finally:
        counter_task.cancel()
        with suppress(asyncio.CancelledError):
            await counter_task


if __name__ == "__main__":
    asyncio.run(main())
