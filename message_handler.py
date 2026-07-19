import re
import datetime
from maxapi import Dispatcher
from maxapi.types import MessageCreated
from maxapi.filters.command import Command

from config import MAX_TOKEN, CACHE_TTL, YANDEX_DIRECT_URL, YANDEX_SHARE_URL
from database import get_user_class, save_user, delete_user
from schedule import load_schedule, get_schedule_for_day

# Хранилище классов пользователей
user_classes = {}

# Создаем диспетчер для обработки сообщений
dp = Dispatcher()


@dp.message_created(Command("start"))
async def cmd_start(event: MessageCreated):
    """Обработчик команды /start"""
    await event.message.answer(
        text=(
            "🎓 *Привет! Я бот-расписание для школы*\n\n"
            "📌 Чтобы начать, напиши свой класс:\n"
            "`1А`, `1Б`, `2А`, `2Б`, `3А`, `3Б`, `4А`, `4Б`, `5А`, `5Б`, `6А`, `6Б`, `7А`, `7Б`, `8А`, `8Б`, `9А`, `9Б`, `10`, `11`\n\n"
            "После этого можно запрашивать расписание:\n"
            "📅 `сегодня` — расписание на сегодня\n"
            "📅 `завтра` — расписание на завтра\n"
            "📅 `ПН`, `ВТ`, `СР`... — на конкретный день\n"
            "📅 `неделя` — на всю неделю\n\n"
            "🔧 Команды:\n"
            "`/myclass` — показать мой класс\n"
            "`/changeclass 5А` — изменить класс\n"
            "`/deleteclass` — удалить мой класс"
        )
    )


@dp.message_created(Command("myclass"))
async def cmd_myclass(event: MessageCreated):
    """Показывает текущий класс пользователя"""
    user_id = event.from_user.user_id
    user_class = get_user_class(user_id)

    if user_class:
        await event.message.answer(
            text=f"📚 Твой текущий класс: *{user_class}*\n\n"
                 "Чтобы изменить класс, напиши `/changeclass 5А`"
        )
    else:
        await event.message.answer(
            text="❌ Ты ещё не выбрал класс.\n"
                 "Напиши свой класс, например: `5А`"
        )


@dp.message_created(Command("changeclass"))
async def cmd_changeclass(event: MessageCreated):
    """Изменяет класс пользователя"""
    user_id = event.from_user.user_id
    # Получаем аргумент команды
    parts = event.message.body.text.split()

    if len(parts) != 2:
        await event.message.answer(
            text="❌ Использование: `/changeclass 5А`\n"
                 "Пример: `/changeclass 5А`"
        )
        return

    new_class = parts[1].upper()
    class_pattern = r'^([1-9][А-Я]|10|11)$'

    if not re.match(class_pattern, new_class):
        await event.message.answer(
            text=f"❌ Некорректный класс: `{new_class}`\n"
                 "Допустимые форматы: `5А`, `5Б`, `6А`, `6Б`, `7А`, `7Б`, `8А`, `8Б`, `9А`, `9Б`, `10`, `11`"
        )
        return

    # Получаем данные пользователя из события
    first_name = event.from_user.first_name if hasattr(event.from_user, 'first_name') else None
    last_name = event.from_user.last_name if hasattr(event.from_user, 'last_name') else None
    username = event.from_user.username if hasattr(event.from_user, 'username') else None

    save_user(user_id, new_class, first_name, last_name, username)

    await event.message.answer(
        text=f"✅ Класс изменён на: *{new_class}*"
    )


@dp.message_created(Command("deleteclass"))
async def cmd_deleteclass(event: MessageCreated):
    """Удаляет класс пользователя"""
    user_id = event.from_user.user_id
    user_class = get_user_class(user_id)

    if not user_class:
        await event.message.answer(
            text="❌ У тебя ещё нет сохранённого класса."
        )
        return

    delete_user(user_id)
    await event.message.answer(
        text=f"🗑️ Класс *{user_class}* удалён.\n"
             "Чтобы выбрать новый, напиши свой класс, например: `5А`"
    )
@dp.message_created(Command("ping"))
async def cmd_ping(event: MessageCreated):
    """Простая проверка, что бот работает"""
    cache_status = "✅ загружен" if hasattr(dp, '_schedule_cache') and dp._schedule_cache else "❌ не загружен"
    await event.message.answer(
        text=(
            f"🏓 *Pong!*\n\n"
            f"✅ Бот работает\n"
            f"📅 Текущее время: {datetime.datetime.now().strftime('%H:%M:%S')}\n"
            f"💾 Кэш расписания: {cache_status}\n"
            f"👥 Пользователей в памяти: {len(user_classes)}"
        )  # <-- Убрал parse_mode
    )


@dp.message_created()
async def handle_text(event: MessageCreated):
    """Обработчик всех текстовых сообщений"""
    user_text = event.message.body.text.strip()
    user_id = event.from_user.user_id

    # Проверяем, не вводит ли пользователь класс
    class_pattern = r'^([1-9][А-Я]|10|11)$'
    if re.match(class_pattern, user_text.upper()):
        class_name = user_text.upper()

        # Сохраняем пользователя в базу
        first_name = event.from_user.first_name if hasattr(event.from_user, 'first_name') else None
        last_name = event.from_user.last_name if hasattr(event.from_user, 'last_name') else None
        username = event.from_user.username if hasattr(event.from_user, 'username') else None

        save_user(user_id, class_name, first_name, last_name, username)

        await event.message.answer(
            text=f"✅ Запомнил! Твой класс: *{class_name}*\n"
                 "Теперь пиши день недели, чтобы узнать расписание.\n\n"
                 "🔧 Команды:\n"
                 "`/myclass` — показать мой класс\n"
                 "`/changeclass 5А` — изменить класс"
        )
        return

    # Проверяем, есть ли класс у пользователя в базе
    user_class = get_user_class(user_id)

    if not user_class:
        await event.message.answer(
            text="❌ Сначала напиши свой класс.\nНапример: `5А`"
        )
        return

    # Загружаем расписание (с кэшированием)
    if not hasattr(dp, '_schedule_cache') or not dp._schedule_cache:
        dp._schedule_cache = load_schedule(YANDEX_SHARE_URL, CACHE_TTL)

    schedule = dp._schedule_cache

    # Обработка команд
    days_map = {
        "сегодня": datetime.datetime.now().weekday(),
        "завтра": (datetime.datetime.now().weekday() + 1) % 7,
    }
    days_ru = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]

    if user_text.lower() in ["сегодня", "завтра"]:
        day_num = days_map[user_text.lower()]
        day_ru = days_ru[day_num]
        result = get_schedule_for_day(schedule, day_ru, user_class)
        await event.message.answer(text=result)

    elif user_text.upper() in days_ru:
        result = get_schedule_for_day(schedule, user_text.upper(), user_class)
        await event.message.answer(text=result)

    elif user_text.lower() == "неделя":
        result = f"📅 *Расписание для {user_class} на неделю*\n\n"
        for day in days_ru:
            day_schedule = get_schedule_for_day(schedule, day, user_class)
            if "Нет занятий" not in day_schedule and "недоступно" not in day_schedule:
                result += day_schedule + "\n"
        await event.message.answer(text=result)

    else:
        await event.message.answer(
            text="❌ Не понял команду.\nНапиши `/start` для помощи."
        )