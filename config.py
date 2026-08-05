import os
from pathlib import Path

from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

# Токен бота в MAX
MAX_TOKEN = os.getenv("MAX_TOKEN")

# Прямая ссылка на файл с расписанием на Яндекс.Диске
YANDEX_DIRECT_URL = os.getenv("YANDEX_DIRECT_URL")

YANDEX_SHARE_URL = os.getenv("YANDEX_SHARE_URL")

# Время жизни кэша в секундах (по умолчанию 5 минут)
CACHE_TTL = int(os.getenv("CACHE_TTL", 300))

DB_PATH = Path(os.getenv("DB_PATH", "/app/data/users.db"))

# Проверяем, что все переменные загружены
if not MAX_TOKEN:
    raise ValueError("❌ MAX_TOKEN не найден в .env файле!")

if not YANDEX_DIRECT_URL:
    raise ValueError("❌ YANDEX_DIRECT_URL не найден в .env файле!")

print("✅ Конфигурация загружена успешно!")