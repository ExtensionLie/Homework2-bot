# database.py
import aiosqlite
from datetime import date, timedelta

DB_PATH = "homework.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username    TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS homeworks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                subject     TEXT NOT NULL,
                description TEXT NOT NULL,
                deadline    TEXT NOT NULL,
                added_by    INTEGER NOT NULL,
                file_id     TEXT,
                file_type   TEXT,
                created_at  TEXT DEFAULT (date('now'))
            )
        """)
        # Додаємо колонки якщо вже існує стара БД без них
        await db.execute("""
            CREATE TABLE IF NOT EXISTS done_marks (
                telegram_id INTEGER NOT NULL,
                hw_id       INTEGER NOT NULL,
                PRIMARY KEY (telegram_id, hw_id)
            )
        """)
        try:
            await db.execute("ALTER TABLE homeworks ADD COLUMN file_type TEXT")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE homeworks ADD COLUMN is_done INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE homeworks ADD COLUMN added_by_name TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN reminder_hour INTEGER DEFAULT 7")
        except Exception:
            pass
        await db.commit()

async def add_homework(subject: str, description: str, deadline: str, added_by: int,
                       file_id: str = None, file_type: str = None, added_by_name: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO homeworks (subject, description, deadline, added_by, file_id, file_type, added_by_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (subject, description, deadline, added_by, file_id, file_type, added_by_name),
        )
        await db.commit()

async def get_homeworks_by_subject_and_date(subject: str, date_from: str, date_to: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM homeworks WHERE subject = ? AND deadline BETWEEN ? AND ? ORDER BY deadline ASC",
            (subject, date_from, date_to),
        ) as cur:
            return await cur.fetchall()

async def get_subjects_with_homeworks(date_from: str, date_to: str) -> list[str]:
    """Повертає список предметів які мають ДЗ у діапазоні дат."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT DISTINCT subject FROM homeworks WHERE deadline BETWEEN ? AND ? ORDER BY subject ASC",
            (date_from, date_to),
        ) as cur:
            rows = await cur.fetchall()
            return [row[0] for row in rows]

async def get_homeworks_week(date_from: str, date_to: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM homeworks WHERE deadline BETWEEN ? AND ? ORDER BY deadline ASC, subject ASC",
            (date_from, date_to),
        ) as cur:
            return await cur.fetchall()

async def register_user(telegram_id: int, username: str):
    """Зберігає користувача для нагадувань."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)",
            (telegram_id, username),
        )
        await db.commit()

async def set_reminder_hour(telegram_id: int, hour: int):
    """Зберігає обраний час нагадування для користувача."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET reminder_hour = ? WHERE telegram_id = ?",
            (hour, telegram_id)
        )
        await db.commit()

async def get_users_by_reminder_hour(hour: int):
    """Повертає всіх користувачів з певним часом нагадування."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE reminder_hour = ?", (hour,)
        ) as cur:
            return await cur.fetchall()

async def get_all_users():
    """Повертає всіх користувачів які запускали бота."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users") as cur:
            return await cur.fetchall()

async def get_homeworks_today(today: str):
    """Повертає всі ДЗ з дедлайном на сьогодні."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM homeworks WHERE deadline = ? ORDER BY subject ASC",
            (today,),
        ) as cur:
            return await cur.fetchall()

async def check_duplicate(subject: str, deadline: str) -> bool:
    """Перевіряє чи є вже ДЗ з таким предметом і дедлайном."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM homeworks WHERE subject = ? AND deadline = ?",
            (subject, deadline)
        ) as cur:
            return await cur.fetchone() is not None

async def get_homework_by_id(hw_id: int):
    """Повертає одне ДЗ по ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM homeworks WHERE id = ?", (hw_id,)
        ) as cur:
            return await cur.fetchone()

async def update_homework(hw_id: int, telegram_id: int, description: str, deadline: str):
    """Оновлює текст і дедлайн ДЗ (лише своє)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE homeworks SET description = ?, deadline = ? WHERE id = ? AND added_by = ?",
            (description, deadline, hw_id, telegram_id)
        )
        await db.commit()

async def toggle_homework_done(hw_id: int, telegram_id: int) -> bool:
    """Перемикає особистий статус виконання. Повертає True якщо тепер виконано."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM done_marks WHERE telegram_id = ? AND hw_id = ?",
            (telegram_id, hw_id)
        ) as cur:
            exists = await cur.fetchone()
        if exists:
            await db.execute(
                "DELETE FROM done_marks WHERE telegram_id = ? AND hw_id = ?",
                (telegram_id, hw_id)
            )
            await db.commit()
            return False
        else:
            await db.execute(
                "INSERT INTO done_marks (telegram_id, hw_id) VALUES (?, ?)",
                (telegram_id, hw_id)
            )
            await db.commit()
            return True

async def get_done_ids(telegram_id: int) -> set[int]:
    """Повертає множину hw_id які користувач позначив як виконані."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT hw_id FROM done_marks WHERE telegram_id = ?",
            (telegram_id,)
        ) as cur:
            rows = await cur.fetchall()
            return {row[0] for row in rows}

async def delete_homework(hw_id: int, telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM homeworks WHERE id = ? AND added_by = ?",
            (hw_id, telegram_id),
        )
        await db.commit()

async def admin_delete_homework(hw_id: int):
    """Видаляє будь-яке ДЗ — тільки для адміна."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM homeworks WHERE id = ?", (hw_id,))
        await db.commit()
