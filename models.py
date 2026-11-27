"""Робота з SQLite для застосунку розкладу."""

import sqlite3
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash

from lesson_fields import split_subject_name


def get_db():
    """Повертає одне з'єднання з БД для поточного HTTP-запиту."""
    if "db" not in g:
        db = sqlite3.connect(current_app.config["DATABASE"])
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        g.db = db
    return g.db


def close_db(_error=None):
    """Закриває з'єднання після завершення запиту."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Створює таблиці та початкові демонстраційні записи."""
    db = get_db()
    with current_app.open_resource("schema.sql") as schema:
        db.executescript(schema.read().decode("utf8"))
    # Невелика міграція для БД, створених до появи OCR-імпорту.
    columns = {row["name"] for row in db.execute("PRAGMA table_info(schedule_imports)")}
    if "ocr_text" not in columns:
        db.execute(
            "ALTER TABLE schedule_imports ADD COLUMN ocr_text TEXT NOT NULL DEFAULT ''"
        )
    with db:
        migrate_lesson_fields(db)
    _seed_data(db)
    db.commit()


def migrate_lesson_fields(db):
    """Зберігає пари та коментарі, об'єднуючи варіанти однієї дисципліни."""
    columns = {row["name"] for row in db.execute("PRAGMA table_info(schedule_entries)")}
    if "lesson_type" not in columns:
        db.execute("""ALTER TABLE schedule_entries ADD COLUMN lesson_type TEXT NOT NULL
                      DEFAULT '' CHECK (lesson_type IN ('', 'lecture', 'practice', 'lab'))""")
    if "subgroup" not in columns:
        db.execute("""ALTER TABLE schedule_entries ADD COLUMN subgroup TEXT NOT NULL
                      DEFAULT '' CHECK (subgroup IN ('', '1', '2', '3', '4', '5', '6', '7', '8', '9'))""")
    canonical = {}
    for subject in db.execute("SELECT id, name FROM subjects ORDER BY id").fetchall():
        name, kind, subgroup = split_subject_name(subject["name"])
        key = name.casefold()
        if key not in canonical:
            # Prefer an existing plain name if it already exists.
            existing = db.execute(
                "SELECT id FROM subjects WHERE name = ?", (name,)
            ).fetchone()
            canonical[key] = existing["id"] if existing else subject["id"]
        target = canonical[key]
        db.execute(
            """UPDATE schedule_entries SET subject_id = ?,
               lesson_type = CASE WHEN lesson_type = '' THEN ? ELSE lesson_type END,
               subgroup = CASE WHEN subgroup = '' THEN ? ELSE subgroup END
               WHERE subject_id = ?""",
            (target, kind, subgroup, subject["id"]),
        )
        if target != subject["id"]:
            db.execute("DELETE FROM subjects WHERE id = ?", (subject["id"],))
        elif name != subject["name"]:
            db.execute("UPDATE subjects SET name = ? WHERE id = ?", (name, target))


def _seed_data(db):
    if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        return
    db.execute(
        "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        (
            "Адміністратор розкладу",
            "admin@vofknuht.local",
            generate_password_hash("admin123"),
            "admin",
        ),
    )
    teachers = (
        ("Олена Мельник", "melnyk@vofknuht.local", "teacher123"),
        ("Андрій Коваль", "koval@vofknuht.local", "teacher123"),
    )
    for name, email, password in teachers:
        db.execute(
            "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, 'teacher')",
            (name, email, generate_password_hash(password)),
        )
    db.execute("INSERT INTO groups (name, course) VALUES ('ІПЗ-21', 2)")
    for subject in (
        "Основи програмування",
        "Математика",
        "Українська мова",
        "Інформатика",
    ):
        db.execute("INSERT INTO subjects (name) VALUES (?)", (subject,))
    for room in ("203", "305", "Спортзал"):
        db.execute("INSERT INTO classrooms (name) VALUES (?)", (room,))
    teacher_ids = [
        row["id"]
        for row in db.execute("SELECT id FROM users WHERE role = 'teacher' ORDER BY id")
    ]
    subject_ids = [
        row["id"] for row in db.execute("SELECT id FROM subjects ORDER BY id")
    ]
    room_ids = [
        row["id"] for row in db.execute("SELECT id FROM classrooms ORDER BY id")
    ]
    lessons = (
        (1, subject_ids[0], teacher_ids[0], room_ids[0], 1, 1, "08:00", "09:20"),
        (1, subject_ids[1], teacher_ids[1], room_ids[1], 1, 2, "09:30", "10:50"),
        (1, subject_ids[2], teacher_ids[0], room_ids[0], 1, 3, "11:20", "12:40"),
        (1, subject_ids[3], teacher_ids[1], room_ids[1], 2, 1, "08:00", "09:20"),
    )
    db.executemany(
        """INSERT INTO schedule_entries (group_id, subject_id, teacher_id, classroom_id, day_of_week, pair_number, starts_at, ends_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        lessons,
    )


def init_app(app):
    """Реєструє lifecycle БД і створює файл БД за потреби."""
    app.teardown_appcontext(close_db)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    with app.app_context():
        init_db()
