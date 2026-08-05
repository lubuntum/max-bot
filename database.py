import sqlite3
import datetime
from pathlib import Path

from config import DB_PATH


#DB_PATH = Path(__file__).parent / "users.db"


def get_connection():
    """Создает подключение к базе данных"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Чтобы получать доступ по именам колонок
    return conn


def init_db():
    """Создает таблицу пользователей, если её нет"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            class_name TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

init_db()
def save_user(user_id: int, class_name: str, first_name: str = None, last_name: str = None, username: str = None):
    """Сохраняет или обновляет пользователя в базе данных"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO users (user_id, class_name, first_name, last_name, username, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            class_name = excluded.class_name,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            username = excluded.username,
            updated_at = excluded.updated_at
    ''', (user_id, class_name, first_name, last_name, username, datetime.datetime.now()))

    conn.commit()
    conn.close()


def get_user_class(user_id: int):
    """Возвращает класс пользователя или None, если пользователь не найден"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT class_name FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()

    conn.close()
    return row['class_name'] if row else None


def get_all_users():
    """Возвращает всех пользователей (для административных команд)"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT user_id, class_name, first_name, username, updated_at FROM users ORDER BY updated_at DESC')
    rows = cursor.fetchall()

    conn.close()
    return [dict(row) for row in rows]


def delete_user(user_id: int):
    """Удаляет пользователя из базы данных"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()