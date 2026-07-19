import re

import requests


def get_direct_link(share_url):
    """
    Получает прямую ссылку на скачивание файла с Яндекс.Диска
    Работает с публичными ссылками вида: https://disk.yandex.ru/i/...
    """
    try:
        # Получаем HTML-страницу
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(share_url, headers=headers, timeout=10)
        response.raise_for_status()

        # Ищем ссылку на скачивание в нескольких форматах
        patterns = [
            # Прямая ссылка downloader
            r'https://downloader\.disk\.yandex\.ru/disk/[^"\']+',
            # Ссылка через disk с параметрами
            r'https://disk\.yandex\.ru/disk/[^"\']+\.xlsx[^"\']*',
            # Любая ссылка с .xlsx
            r'https://[^"\']+\.yandex\.ru/[^"\']+\.xlsx[^"\']*',
        ]

        for pattern in patterns:
            match = re.search(pattern, response.text)
            if match:
                # Очищаем ссылку от HTML-сущностей
                url = match.group(0)
                url = url.replace('&amp;', '&')
                return url

        # Если не нашли, пробуем найти в window.__DATA__
        json_match = re.search(r'window\.__DATA__\s*=\s*({.+?});', response.text)
        if json_match:
            import json
            data = json.loads(json_match.group(1))

            # Рекурсивный поиск downloadUrl
            def find_download_url(obj):
                if isinstance(obj, dict):
                    if 'downloadUrl' in obj:
                        return obj['downloadUrl']
                    for key, value in obj.items():
                        result = find_download_url(value)
                        if result:
                            return result
                elif isinstance(obj, list):
                    for item in obj:
                        result = find_download_url(item)
                        if result:
                            return result
                return None

            return find_download_url(data)

        return None

    except Exception as e:
        print(f"Ошибка: {e}")
        return None

if __name__ == "__main__":
    url = input("Введите ссылку: ")
    print(get_direct_link(url))