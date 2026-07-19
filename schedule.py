import io
import os
import datetime
from urllib.parse import urlencode

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
    Использует кэширование для уменьшения количества запросов
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
           and str(row["Класс"]).upper() == class_name.upper()
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