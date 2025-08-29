import sqlite3

def init_db():
    """Инициализация базы данных."""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, tinkoff_api_key TEXT)''')
    conn.commit()
    conn.close()

def save_api_key(user_id, api_key):
    """Сохранение API-ключа пользователя."""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, tinkoff_api_key) VALUES (?, ?)",
              (user_id, api_key))
    conn.commit()
    conn.close()

def get_api_key(user_id):
    """Получение API-ключа пользователя."""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT tinkoff_api_key FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None