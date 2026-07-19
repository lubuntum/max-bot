"""
Бот-расписание для школы в MAX
Запуск: python bot.py
"""

import asyncio
from maxapi import Bot
from message_handler import dp
from config import MAX_TOKEN


async def main():
    print("🤖 Бот запущен!")

    # Создаем экземпляр бота
    bot = Bot(token=MAX_TOKEN)

    # Удаляем вебхук, если он был установлен (для polling режима)
    await bot.delete_webhook()

    # Запускаем polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())