import sqlite3
import os
import hashlib

DB_PATH = "database.db"

def get_db_connection():
    """Создает подключение к БД. Строки возвращаются как словари dict."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Создает таблицы, если они еще не созданы."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Таблица игровых сессий
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        status TEXT NOT NULL DEFAULT 'waiting',
        current_round TEXT DEFAULT 'E1',
        riichi_sticks INTEGER DEFAULT 0,
        honba INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Таблица участников матча
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS game_players (
        game_id INTEGER,
        user_id INTEGER,
        seat_order INTEGER,
        initial_score INTEGER DEFAULT 25000,
        final_score INTEGER DEFAULT NULL,
        final_place INTEGER DEFAULT NULL,
        PRIMARY KEY(game_id, user_id),
        FOREIGN KEY(game_id) REFERENCES games(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    conn.commit()
    conn.close()
    print("База данных успешно инициализирована!")

def hash_password(password: str) -> str:
    """Хэширует пароль для безопасного хранения в БД."""
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username: str, password_raw: str) -> bool:
    """Регистрирует нового пользователя. Возвращает False, если имя занято."""
    conn = get_db_connection()
    cursor = conn.cursor()
    pwd_hash = hash_password(password_raw)
    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, pwd_hash)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Имя пользователя уже существует
    finally:
        conn.close()

def check_user_credentials(username: str, password_raw: str) -> dict:
    """Проверяет логин/пароль. Возвращает dict игрока или None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    pwd_hash = hash_password(password_raw)
    
    cursor.execute(
        "SELECT id, username FROM users WHERE username = ? AND password_hash = ?",
        (username, pwd_hash)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {"id": row["id"], "username": row["username"]}
    return None

def save_match_results(game_id: int, current_round: str, players_list: list):
    """Сохраняет финальное состояние игры и распределяет места."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE games SET status = 'finished', current_round = ? WHERE id = ?",
        (current_round, game_id)
    )
    
    sorted_players = sorted(players_list, key=lambda x: x["score"], reverse=True)
    
    for place, player in enumerate(sorted_players, start=1):
        cursor.execute('''
            INSERT INTO game_players (game_id, user_id, seat_order, final_score, final_place)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(game_id, user_id) DO UPDATE SET
                final_score = excluded.final_score,
                final_place = excluded.final_place
        ''', (game_id, player["user_id"], player["seat"], player["score"], place))
        
    conn.commit()
    conn.close()
    print(f"Результаты игры {game_id} успешно сохранены в SQLite!")

def get_user_stats(user_id: int) -> dict:
    """Возвращает количество сыгранных матчей и распределение мест."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            COUNT(*) as total_games,
            SUM(CASE WHEN final_place = 1 THEN 1 ELSE 0 END) as first_places,
            SUM(CASE WHEN final_place = 2 THEN 1 ELSE 0 END) as second_places,
            SUM(CASE WHEN final_place = 3 THEN 1 ELSE 0 END) as third_places,
            SUM(CASE WHEN final_place = 4 THEN 1 ELSE 0 END) as fourth_places,
            AVG(final_score) as avg_score
        FROM game_players
        WHERE user_id = ? AND final_place IS NOT NULL
    ''', (user_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row or row["total_games"] == 0:
        return {"total_games": 0, "places": [], "avg_score": 0}
        
    return {
        "total_games": row["total_games"],
        "places": [row["first_places"], row["second_places"], row["third_places"], row["fourth_places"]],
        "avg_score": round(row["avg_score"], 2)
    }
