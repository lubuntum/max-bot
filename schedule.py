import io
import os
import datetime
from urllib.parse import urlencode
import io
import os
import re
import datetime
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import requests
import pandas as pd

# Глобальный кэш
_schedule_cache = None
_last_update = 0

# Разные написания дня недели -> короткий код, которым бот пользуется
# в кнопках (ПН, ВТ, СР, ...). Работает и с "Среда", и с "СР".
_DAY_ALIASES = {
    'ПОНЕДЕЛЬНИК': 'ПН', 'ПН': 'ПН',
    'ВТОРНИК': 'ВТ', 'ВТ': 'ВТ',
    'СРЕДА': 'СР', 'СР': 'СР',
    'ЧЕТВЕРГ': 'ЧТ', 'ЧТ': 'ЧТ',
    'ПЯТНИЦА': 'ПТ', 'ПТ': 'ПТ',
    'СУББОТА': 'СБ', 'СБ': 'СБ',
    'ВОСКРЕСЕНЬЕ': 'ВС', 'ВС': 'ВС',
}

# Заголовок колонки вида "1А - время" / "1А - урок"
_HEADER_RE = re.compile(r'^(?P<class>.+?)\s*-\s*(?P<field>время|урок)$', re.IGNORECASE)


def _normalize_day(day) -> str:
    day = str(day).strip().upper()
    return _DAY_ALIASES.get(day, day)


@dataclass
class Lesson:
    time: Optional[str]
    subject: Optional[str]


class Schedule:
    """
    Объединённое расписание (Основное + Измененное), уже разложенное
    по дням/классам/номерам уроков — быстро отдаёт нужный день без
    повторного парсинга.
    """

    def __init__(self):
        # {день: {класс: [Lesson, Lesson, ...]}}
        self._data = {}

    def get_day(self, day: str, class_name: str) -> list:
        day = _normalize_day(day)
        class_name = str(class_name).strip().upper()
        return self._data.get(day, {}).get(class_name, [])

    @classmethod
    def from_sheets(cls, df_base, df_changed):
        base = cls._parse_sheet(df_base)
        changed = cls._parse_sheet(df_changed)
        merged = cls._merge(base, changed)

        schedule = cls()
        for (day, class_name), lessons in merged.items():
            schedule._data.setdefault(day, {})[class_name] = lessons
        return schedule

    @staticmethod
    def _parse_sheet(df):
        """
        Превращает "широкую" таблицу с колонками вида
        "<класс> - время" / "<класс> - урок" в
        {(день, класс): [Lesson по порядку уроков]}.
        Номер урока — порядковый номер строки с этим днём
        (в порядке, в котором строки идут в файле).
        """
        if df is None or df.empty:
            return {}

        if 'День' not in df.columns:
            print("⚠️ В листе нет колонки 'День', пропускаю его.")
            return {}

        # какие классы есть в файле — определяем по заголовкам колонок
        classes = {}
        for col in df.columns:
            match = _HEADER_RE.match(str(col).strip())
            if not match:
                continue
            class_name = match.group('class').strip().upper()
            field = match.group('field').lower()
            classes.setdefault(class_name, {})[field] = col

        result = {}
        day_counters = {}

        for _, row in df.iterrows():
            day_raw = row.get('День')
            if pd.isna(day_raw):
                continue
            day = _normalize_day(day_raw)
            day_counters[day] = day_counters.get(day, 0) + 1
            period_index = day_counters[day]

            for class_name, cols in classes.items():
                time_val = row.get(cols.get('время'))
                subj_val = row.get(cols.get('урок'))

                time_val = None if pd.isna(time_val) else str(time_val).strip()
                subj_val = None if pd.isna(subj_val) else str(subj_val).strip()

                lessons = result.setdefault((day, class_name), [])
                while len(lessons) < period_index:
                    lessons.append(Lesson(time=None, subject=None))
                lessons[period_index - 1] = Lesson(time=time_val, subject=subj_val)

        return result

    @staticmethod
    def _merge(base_rows, changed_rows):
        """
        Время и урок берутся из "Измененное", а где там пусто —
        подставляются из "Основное" (время и урок проверяются
        независимо, по одному и тому же номеру урока). Если в
        "Измененное" такого дня/класса нет вообще — используется
        "Основное" целиком. "-" в ячейке — это явное "нет урока",
        оно не считается пустым и не заменяется на Основное.
        """
        merged = {}
        for key in set(base_rows) | set(changed_rows):
            base_lessons = base_rows.get(key, [])
            changed_lessons = changed_rows.get(key, [])
            length = max(len(base_lessons), len(changed_lessons))

            combined = []
            for i in range(length):
                base = base_lessons[i] if i < len(base_lessons) else Lesson(None, None)
                changed = changed_lessons[i] if i < len(changed_lessons) else Lesson(None, None)

                combined.append(Lesson(
                    time=changed.time if changed.time else base.time,
                    subject=changed.subject if changed.subject else base.subject,
                ))

            merged[key] = combined

        return merged


def get_real_direct_url(public_url):
    """
    Converts a standard Yandex.Disk sharing link into a true direct download URL.
    """
    base_url = "https://cloud-api.yandex.net/v1/disk/public/resources/download?"
    query_params = urlencode({'public_key': public_url})
    request_url = base_url + query_params

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }

    response = requests.get(request_url, headers=headers, timeout=15)

    if response.status_code != 200:
        try:
            error_info = response.json()
            print(f"❌ Yandex API Error: {error_info.get('message', 'Unknown Error')}")
        except:
            print(f"❌ HTML Response Received instead of API JSON.")
        response.raise_for_status()

    return response.json().get("href")


def _read_excel_sheet(file_stream, sheet_name, required=True):
    """
    Читает один лист Excel с fallback между движками calamine/xlrd.
    Если required=False и лист отсутствует — возвращает None вместо
    ошибки (так работает необязательный лист "Измененное").
    """
    last_error = None
    for engine in ('calamine', 'xlrd'):
        file_stream.seek(0)
        try:
            return pd.read_excel(file_stream, sheet_name=sheet_name, engine=engine)
        except Exception as e:
            last_error = e
            if not required and 'not found' in str(e).lower():
                return None

    if not required:
        print(f"⚠️ Лист '{sheet_name}' не найден или не читается — использую только 'Основное'.")
        return None

    raise ValueError(f"Не удалось прочитать лист '{sheet_name}': {last_error}")


def load_schedule(public_url, ttl=300):
    """
    Загружает расписание (листы 'Основное' и 'Измененное') из Excel-файла
    по публичной ссылке Яндекс.Диска, объединяет их в Schedule и кэширует.

    Вызывайте эту функцию каждый раз, когда нужно расписание — сама
    решит, вернуть кэш или скачать заново (см. проверку ttl ниже).
    Не оборачивайте результат во внешний "постоянный" кэш поверх неё,
    иначе обновление расписания перестанет работать.
    """
    global _schedule_cache, _last_update

    current_time = datetime.datetime.now().timestamp()

    if _schedule_cache is not None and (current_time - _last_update) < ttl:
        print("📦 Использую кэшированное расписание")
        return _schedule_cache

    try:
        print("🔗 Получение прямой ссылки с Яндекс.Диска...")
        direct_url = get_real_direct_url(public_url)

        print("📥 Скачиваю расписание...")
        response = requests.get(direct_url, timeout=30)
        response.raise_for_status()

        file_stream = io.BytesIO(response.content)

        df_base = _read_excel_sheet(file_stream, 'Основное', required=True)
        df_changed = _read_excel_sheet(file_stream, 'Измененное', required=False)

        _schedule_cache = Schedule.from_sheets(df_base, df_changed)
        _last_update = current_time

        print("✅ Расписание загружено и объединено")
        return _schedule_cache

    except Exception as e:
        print(f"❌ Ошибка загрузки расписания: {e}")
        # Возвращаем старый кэш, если есть
        return _schedule_cache


def get_cache_status():
    """
    Возвращает (загружен_ли_кэш, возраст_кэша_в_секундах).
    Используется, например, командой /ping в боте.
    """
    if _schedule_cache is None:
        return False, None
    age_seconds = datetime.datetime.now().timestamp() - _last_update
    return True, age_seconds


def get_schedule_for_day(schedule, day_ru, class_name):
    """
    Возвращает отформатированный текст расписания для дня и класса.
    schedule — объект Schedule, полученный из load_schedule().
    """
    if not schedule:
        return "❌ Расписание временно недоступно"

    lessons = schedule.get_day(day_ru, class_name)
    lessons = [l for l in lessons if l.subject and l.subject != '-']

    if not lessons:
        return f"📭 Нет занятий для {class_name} в {day_ru}"

    result = f"📚 *Расписание для {class_name} на {day_ru}*\n\n"
    for lesson in lessons:
        time_part = lesson.time or '—'
        result += f"🕐 *{time_part}* — {lesson.subject}\n"

    return result
import requests
import pandas as pd

# Глобальный кэш
_schedule_cache = None
_last_update = 0


def get_real_direct_url(public_url):
    """
    Converts a standard Yandex.Disk sharing link into a true direct download URL.
    """
    base_url = "https://cloud-api.yandex.net/v1/disk/public/resources/download?"
    query_params = urlencode({'public_key': public_url})
    request_url = base_url + query_params

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }

    response = requests.get(request_url, headers=headers, timeout=15)

    if response.status_code != 200:
        try:
            error_info = response.json()
            print(f"❌ Yandex API Error: {error_info.get('message', 'Unknown Error')}")
        except:
            print(f"❌ HTML Response Received instead of API JSON.")
        response.raise_for_status()

    return response.json().get("href")

def load_schedule(public_url, ttl=300):
    """
    Загружает расписание из Excel-файла по публичной ссылке Яндекс.Диска
    Использует кэширование для уменьшения количества запросов.

    Вызывайте эту функцию каждый раз, когда нужно расписание — сама
    решит, вернуть кэш или скачать заново (см. проверку ttl ниже).
    Не оборачивайте результат во внешний "постоянный" кэш поверх неё,
    иначе обновление расписания перестанет работать.
    """
    global _schedule_cache, _last_update

    current_time = datetime.datetime.now().timestamp()

    # Проверяем кэш
    if _schedule_cache is not None and (current_time - _last_update) < ttl:
        print("📦 Использую кэшированное расписание")
        return _schedule_cache

    try:
        # 1. Получаем реальную прямую ссылку из публичной
        print("🔗 Получение прямой ссылки с Яндекс.Диска...")
        direct_url = get_real_direct_url(public_url)

        # 2. Скачиваем сам файл
        print("📥 Скачиваю расписание...")
        response = requests.get(direct_url, timeout=30)
        response.raise_for_status()

        # 3. Загружаем файл прямо из RAM без сохранения на жесткий диск
        file_stream = io.BytesIO(response.content)

        try:
            # Сначала пробуем современный openpyxl движок
            df = pd.read_excel(file_stream, engine='calamine')
        except Exception as excel_err:
            print(f"⚠️ Ошибка openpyxl: {excel_err}. Пробую альтернативный движок...")

            try:
                # Перематываем поток обратно в начало перед повторным чтением
                file_stream.seek(0)
                df = pd.read_excel(file_stream, engine='xlrd')
            except Exception as xlrd_err:
                print(f"⚠️ Ошибка xlrd: {xlrd_err}.")
                # Не пытаемся читать двоичный ZIP (.xlsx) как CSV файл. Выбрасываем исключение.
                raise ValueError("Не удалось прочитать файл как Excel-таблицу. Проверьте установленные библиотеки.")

        # Сохраняем в кэш
        _schedule_cache = df.to_dict("records")
        _last_update = current_time

        print(f"✅ Расписание загружено, записей: {len(_schedule_cache)}")
        return _schedule_cache

    except Exception as e:
        print(f"❌ Ошибка загрузки расписания: {e}")
        # Возвращаем старый кэш, если есть
        return _schedule_cache


def get_cache_status():
    """
    Возвращает (загружен_ли_кэш, возраст_кэша_в_секундах).
    Используется, например, командой /ping в боте, чтобы показать
    реальное состояние кэша расписания.
    """
    if _schedule_cache is None:
        return False, None

    age_seconds = datetime.datetime.now().timestamp() - _last_update
    return True, age_seconds


def get_schedule_for_day(schedule_data, day_ru, class_name):
    """
    Возвращает расписание для конкретного дня и класса
    """
    if not schedule_data:
        return "❌ Расписание временно недоступно"

    # Фильтруем по дню и классу
    filtered = [
        row for row in schedule_data
        if str(row["День"]).upper() == day_ru.upper()
           and str(row["Класс"]).upper() == class_name.upper()#Error because now not formant for День and Class (not 1A but 1A-Урок and etc)
    ]

    if not filtered:
        return f"📭 Нет занятий для {class_name} в {day_ru}"

    # Сортируем по времени
    filtered.sort(key=lambda x: str(x["Время"]))

    result = f"📚 *Расписание для {class_name} на {day_ru}*\n\n"
    for row in filtered:
        result += f"🕐 *{row['Время']}* — {row['Предмет']}\n"
        result += f"👨‍🏫 {row['Учитель']} | 📍 {row['Кабинет']}\n\n"

    return result