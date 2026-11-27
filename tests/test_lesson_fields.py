"""Міграція назв дисциплін не повинна втрачати заняття або коментарі."""

import sqlite3
import unittest

from lesson_fields import split_subject_name
from models import migrate_lesson_fields


class LessonFieldMigrationTests(unittest.TestCase):
    def test_legacy_database_merges_subjects_and_preserves_comments(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        self.addCleanup(db.close)
        db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE subjects (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
            CREATE TABLE schedule_entries (
                id INTEGER PRIMARY KEY,
                subject_id INTEGER REFERENCES subjects(id)
            );
            CREATE TABLE comments (
                id INTEGER PRIMARY KEY,
                lesson_id INTEGER REFERENCES schedule_entries(id),
                body TEXT
            );
            INSERT INTO subjects VALUES
                (1, 'Програмування (ЛР 1)'), (2, 'Програмування (ЛР 2)'),
                (3, 'Програмування (л.)'), (4, 'Програмування'),
                (5, 'Англійська мова (пр. II)'), (6, 'Алгебра (поглиблена)');
            INSERT INTO schedule_entries VALUES (1,1), (2,2), (3,3), (4,5), (5,6);
            INSERT INTO comments VALUES (1,1,'Принести ноутбуки');
        """)
        with db:
            migrate_lesson_fields(db)
        rows = [
            tuple(row)
            for row in db.execute(
                "SELECT id, subject_id, lesson_type, subgroup FROM schedule_entries ORDER BY id"
            )
        ]
        self.assertEqual(
            rows[:4],
            [
                (1, 4, "lab", "1"),
                (2, 4, "lab", "2"),
                (3, 4, "lecture", ""),
                (4, 5, "practice", "2"),
            ],
        )
        self.assertEqual(db.execute("SELECT count(*) FROM subjects").fetchone()[0], 3)
        self.assertEqual(
            db.execute("SELECT body FROM comments").fetchone()[0], "Принести ноутбуки"
        )
        self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        with db:
            migrate_lesson_fields(db)
        self.assertEqual(
            rows,
            [
                tuple(row)
                for row in db.execute(
                    "SELECT id, subject_id, lesson_type, subgroup FROM schedule_entries ORDER BY id"
                )
            ],
        )

    def test_unknown_parenthetical_names_are_not_truncated(self):
        self.assertEqual(
            split_subject_name("Алгебра (поглиблена)"), ("Алгебра (поглиблена)", "", "")
        )
        self.assertEqual(
            split_subject_name("Програмування (ЛР 2)"), ("Програмування", "lab", "2")
        )
        self.assertEqual(split_subject_name("Мова (пр. ІІ)"), ("Мова", "practice", "2"))
