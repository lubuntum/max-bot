import asyncio
import re
import datetime
from maxapi import Dispatcher
from maxapi.types import MessageCreated, MessageCallback, CallbackButton
from maxapi.filters.command import Command
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from config import MAX_TOKEN, CACHE_TTL, YANDEX_DIRECT_URL, YANDEX_SHARE_URL
from database import get_user_class, save_user, delete_user
from schedule import load_schedule, get_schedule_for_day

# Создаем диспетчер для обработки сообщений
dp = Dispatcher()

CLASS_PATTERN = r'^([1-9][А-Я]|10|11)$'

# Классы в порядке отображения на клавиатуре (по 4 кнопки в ряд)
CLASSES = [
    '1А', '1Б', '2А', '2Б',
    '3А', '3Б', '4А', '4Б',
    '5А', '5Б', '6А', '6Б',
    '7А', '7Б', '8А', '8Б',
    '9А', '9Б', '10', '11',
]

DAYS_RU = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]


# ---------- Клавиатуры (заменяют ручной ввод кнопками) ----------

def classes_keyboard() -> InlineKeyboardBuilder:
    """Клавиатура выбора класса вместо ввода текста."""
    kb = InlineKeyboardBuilder()
    for i in range(0, len(CLASSES), 4):
        row = [CallbackButton(text=c, payload=f'class:{c}') for c in CLASSES[i:i + 4]]
        kb.row(*row)
    return kb


def days_keyboard() -> InlineKeyboardBuilder:
    """Клавиатура выбора дня расписания вместо ввода текста."""
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text='📅 Сегодня', payload='day:today'),
        CallbackButton(text='📅 Завтра', payload='day:tomorrow'),
    )
    kb.row(*[CallbackButton(text=d, payload=f'day:{d}') for d in DAYS_RU[:4]])
    kb.row(*[CallbackButton(text=d, payload=f'day:{d}') for d in DAYS_RU[4:]])
    kb.row(CallbackButton(text='🗓 На неделю', payload='day:week'))
    kb.row(CallbackButton(text='◀️ В меню', payload='menu:back'))
    return kb


def menu_keyboard() -> InlineKeyboardBuilder:
    """Главное меню после того, как класс выбран."""
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text='📅 Расписание', payload='menu:schedule'))
    kb.row(
        CallbackButton(text='🔄 Сменить класс', payload='menu:changeclass'),
        CallbackButton(text='🗑 Удалить класс', payload='menu:deleteclass'),
    )
    return kb


def menu_text(user_class: str) -> str:
    return f"📚 Твой класс: *{user_class}*\n\nВыбери, что нужно 👇"


def get_user_info(user):
    """Достаёт first_name/last_name/username, если они есть у объекта пользователя."""
    return (
        getattr(user, 'first_name', None),
        getattr(user, 'last_name', None),
        getattr(user, 'username', None),
    )


async def get_cached_schedule():
    """
    Расписание кэшируется и обновляется по TTL внутри load_schedule
    (schedule.py) — вызываем её каждый раз, она сама решает, вернуть
    кэш или скачать заново. load_schedule синхронная (requests),
    поэтому уводим её в отдельный поток, чтобы не блокировать бота
    во время обновления.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, load_schedule, YANDEX_SHARE_URL, CACHE_TTL)


async def build_schedule_text(day_code: str, user_class: str) -> str:
    """Текст расписания по коду дня ('today', 'tomorrow', 'week' или 'ПН'..'ВС')."""
    schedule = await get_cached_schedule()

    if day_code in ("today", "tomorrow"):
        weekday = datetime.datetime.now().weekday()
        if day_code == "tomorrow":
            weekday = (weekday + 1) % 7
        return get_schedule_for_day(schedule, DAYS_RU[weekday], user_class)

    if day_code == "week":
        result = f"📅 *Расписание для {user_class} на неделю*\n\n"
        for day in DAYS_RU:
            day_schedule = get_schedule_for_day(schedule, day, user_class)
            if "Нет занятий" not in day_schedule and "недоступно" not in day_schedule:
                result += day_schedule + "\n"
        return result

    return get_schedule_for_day(schedule, day_code, user_class)


# ---------- Команды ----------

@dp.message_created(Command("start"))
async def cmd_start(event: MessageCreated):
    """/start — сразу показывает кнопки, а не список команд для ввода."""
    user_class = get_user_class(event.from_user.user_id)

    if user_class:
        await event.message.answer(
            text=menu_text(user_class),
            attachments=[menu_keyboard().as_markup()],
        )
    else:
        await event.message.answer(
            text="🎓 *Привет! Я бот-расписание для школы*\n\n📌 Выбери свой класс кнопкой ниже 👇",
            attachments=[classes_keyboard().as_markup()],
        )


@dp.message_created(Command("myclass"))
async def cmd_myclass(event: MessageCreated):
    """Показывает текущий класс пользователя."""
    user_class = get_user_class(event.from_user.user_id)

    if user_class:
        await event.message.answer(text=menu_text(user_class), attachments=[menu_keyboard().as_markup()])
    else:
        await event.message.answer(
            text="❌ Ты ещё не выбрал класс. Выбери его кнопкой ниже 👇",
            attachments=[classes_keyboard().as_markup()],
        )


@dp.message_created(Command("changeclass"))
async def cmd_changeclass(event: MessageCreated):
    """Оставлено для тех, кто печатает вручную: /changeclass 5А"""
    parts = event.message.body.text.split()

    if len(parts) != 2 or not re.match(CLASS_PATTERN, parts[1].upper()):
        await event.message.answer(
            text="📌 Выбери новый класс кнопкой ниже 👇",
            attachments=[classes_keyboard().as_markup()],
        )
        return

    new_class = parts[1].upper()
    first_name, last_name, username = get_user_info(event.from_user)
    save_user(event.from_user.user_id, new_class, first_name, last_name, username)

    await event.message.answer(text=menu_text(new_class), attachments=[menu_keyboard().as_markup()])


@dp.message_created(Command("deleteclass"))
async def cmd_deleteclass(event: MessageCreated):
    """Удаляет класс пользователя."""
    user_class = get_user_class(event.from_user.user_id)

    if not user_class:
        await event.message.answer(text="❌ У тебя ещё нет сохранённого класса.")
        return

    delete_user(event.from_user.user_id)
    await event.message.answer(
        text=f"🗑️ Класс *{user_class}* удалён.\n📌 Выбери новый класс 👇",
        attachments=[classes_keyboard().as_markup()],
    )


@dp.message_created(Command("ping"))
async def cmd_ping(event: MessageCreated):
    """Простая проверка, что бот работает."""
    cache_status = "✅ загружен" if hasattr(dp, '_schedule_cache') and dp._schedule_cache else "❌ не загружен"
    await event.message.answer(
        text=(
            f"🏓 Pong!\n\n"
            f"✅ Бот работает\n"
            f"📅 Текущее время: {datetime.datetime.now().strftime('%H:%M:%S')}\n"
            f"💾 Кэш расписания: {cache_status}\n"
            f"👥 Пользователей всего: 0"
        )
    )


# ---------- Обработчик нажатий на кнопки ----------

@dp.message_callback()
async def handle_callback(event: MessageCallback):
    """Единый обработчик всех кнопок. payload вида 'class:5А', 'day:ПН', 'menu:schedule' и т.п."""
    if event.message is None:
        return

    payload = event.callback.payload
    user_id = event.callback.user.user_id

    if payload.startswith('class:'):
        new_class = payload.split(':', 1)[1]
        first_name, last_name, username = get_user_info(event.callback.user)
        save_user(user_id, new_class, first_name, last_name, username)

        await event.answer(
            new_text=f"✅ Класс сохранён: *{new_class}*\n\n" + menu_text(new_class),
            attachments=[menu_keyboard().as_markup()],
        )
        return

    if payload == 'menu:schedule':
        user_class = get_user_class(user_id)
        if not user_class:
            await event.answer(new_text="❌ Сначала выбери класс 👇", attachments=[classes_keyboard().as_markup()])
            return
        await event.answer(
            new_text=f"📅 Расписание для *{user_class}*. Выбери день 👇",
            attachments=[days_keyboard().as_markup()],
        )
        return

    if payload == 'menu:changeclass':
        await event.answer(new_text="📌 Выбери новый класс 👇", attachments=[classes_keyboard().as_markup()])
        return

    if payload == 'menu:deleteclass':
        delete_user(user_id)
        await event.answer(
            new_text="🗑️ Класс удалён. Выбери новый класс 👇",
            attachments=[classes_keyboard().as_markup()],
        )
        return

    if payload == 'menu:back':
        user_class = get_user_class(user_id)
        if not user_class:
            await event.answer(new_text="📌 Выбери свой класс 👇", attachments=[classes_keyboard().as_markup()])
            return
        await event.answer(new_text=menu_text(user_class), attachments=[menu_keyboard().as_markup()])
        return

    if payload.startswith('day:'):
        user_class = get_user_class(user_id)
        if not user_class:
            await event.answer(new_text="❌ Сначала выбери класс 👇", attachments=[classes_keyboard().as_markup()])
            return

        day_code = payload.split(':', 1)[1]
        text = await build_schedule_text(day_code, user_class)

        kb = InlineKeyboardBuilder()
        kb.row(CallbackButton(text='◀️ Другой день', payload='menu:schedule'))
        kb.row(CallbackButton(text='🏠 В меню', payload='menu:back'))

        await event.answer(new_text=text, attachments=[kb.as_markup()])
        return


# ---------- Резерв для тех, кто всё же печатает текст ----------

@dp.message_created()
async def handle_text(event: MessageCreated):
    """Резервный обработчик: если ввели класс текстом — принимаем, иначе подсказываем кнопки."""
    user_text = event.message.body.text.strip()
    user_id = event.from_user.user_id

    if re.match(CLASS_PATTERN, user_text.upper()):
        class_name = user_text.upper()
        first_name, last_name, username = get_user_info(event.from_user)
        save_user(user_id, class_name, first_name, last_name, username)

        await event.message.answer(text=menu_text(class_name), attachments=[menu_keyboard().as_markup()])
        return

    user_class = get_user_class(user_id)
    if not user_class:
        await event.message.answer(
            text="❌ Сначала выбери класс кнопкой ниже 👇",
            attachments=[classes_keyboard().as_markup()],
        )
        return

    await event.message.answer(
        text="Удобнее пользоваться кнопками 🙂",
        attachments=[menu_keyboard().as_markup()],
    )