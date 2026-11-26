"""Перевірки бази даних, ролей і формування розкладу."""
import os
import shutil
import tempfile
import unittest
from io import BytesIO

from main import app
from models import init_db, get_db


class ScheduleAppTests(unittest.TestCase):
    def setUp(self):
        self.database_fd, database_path = tempfile.mkstemp()
        self.upload_folder = tempfile.mkdtemp()
        app.config.update(TESTING=True, DATABASE=database_path, UPLOAD_FOLDER=self.upload_folder, SECRET_KEY="test-secret")
        with app.app_context():
            init_db()
        self.client = app.test_client()

    def tearDown(self):
        os.close(self.database_fd)
        os.unlink(app.config["DATABASE"])
        shutil.rmtree(self.upload_folder)

    def login(self, email, password):
        return self.client.post("/login", data={"email": email, "password": password}, follow_redirects=True)

    def test_schedule_is_start_page_and_feedback_crud(self):
        root = self.client.get("/", follow_redirects=False)
        self.assertEqual(root.status_code, 302)
        self.assertEqual(root.location, "/schedule")
        schedule = self.client.get("/schedule")
        self.assertIn("Оберіть свою групу", schedule.get_data(as_text=True))
        self.assertNotIn("Основи програмування", schedule.get_data(as_text=True))
        self.assertIn("Основи програмування", self.client.get("/schedule?group=1").get_data(as_text=True))
        for path in ("/schedule", "/feedback", "/login"):
            self.assertEqual(self.client.get(path).status_code, 200)
        response = self.client.post("/feedback", data={"name": "Максим", "email": "max@example.com", "message": "Зручний розклад"}, follow_redirects=True)
        self.assertIn("Відгук збережено", response.get_data(as_text=True))
        self.login("admin@vofknuht.local", "admin123")
        page = self.client.get("/admin/feedback")
        self.assertIn("Зручний розклад", page.get_data(as_text=True))

    def test_roles_protect_cabinets(self):
        self.assertEqual(self.client.get("/admin").status_code, 302)
        self.login("melnyk@vofknuht.local", "teacher123")
        self.assertEqual(self.client.get("/teacher").status_code, 200)
        self.assertEqual(self.client.get("/admin").status_code, 403)

    def test_teacher_can_comment_only_on_own_lesson(self):
        self.login("melnyk@vofknuht.local", "teacher123")
        page = self.client.get("/teacher")
        self.assertIn("Основи програмування", page.get_data(as_text=True))
        response = self.client.post("/teacher/lessons/1/comment", data={"body": "Взяти ноутбуки"}, follow_redirects=True)
        self.assertIn("Коментар до пари збережено", response.get_data(as_text=True))
        self.assertIn("Взяти ноутбуки", self.client.get("/schedule?group=1").get_data(as_text=True))
        self.assertEqual(self.client.post("/teacher/lessons/2/comment", data={"body": "Чужа пара"}).status_code, 403)

    def test_admin_creates_teacher_and_schedule_conflict_is_rejected(self):
        self.login("admin@vofknuht.local", "admin123")
        response = self.client.post("/admin/teachers", data={"full_name": "Ірина Тест", "email": "test@vofknuht.local", "password": "password"}, follow_redirects=True)
        self.assertIn("Акаунт викладача створено", response.get_data(as_text=True))
        conflict = self.client.post("/admin/schedule", data={"group_id": 1, "subject_id": 1, "teacher_id": 2, "classroom_id": 1, "day_of_week": 1, "pair_number": 1, "is_published": "on"}, follow_redirects=True)
        self.assertIn("Конфлікт", conflict.get_data(as_text=True))

    def test_calendar_export_and_photo_import_are_available_to_admin(self):
        calendar = self.client.get("/schedule/1/calendar.ics")
        self.assertEqual(calendar.status_code, 200)
        self.assertEqual(calendar.mimetype, "text/calendar")
        self.assertIn("BEGIN:VCALENDAR", calendar.get_data(as_text=True))
        self.assertIn("RRULE:FREQ=WEEKLY", calendar.get_data(as_text=True))
        self.login("admin@vofknuht.local", "admin123")
        imported = self.client.post("/admin/import", data={"schedule_photo": (BytesIO(b"not a real image"), "schedule.png")}, content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("Фото збережено й текст розпізнано", imported.get_data(as_text=True))
        self.assertIn("schedule.png", imported.get_data(as_text=True))

    def test_separate_lesson_parameters_create_edit_and_validate(self):
        self.login("admin@vofknuht.local", "admin123")
        data = dict(group_id=1, subject_id=1, teacher_id=2, classroom_id=1,
                    day_of_week=5, pair_number=1, is_published="on",
                    lesson_type="lab", subgroup="2")
        response = self.client.post("/admin/schedule", data=data)
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            row = get_db().execute("SELECT * FROM schedule_entries ORDER BY id DESC LIMIT 1").fetchone()
            entry_id = row["id"]
            self.assertEqual((row["lesson_type"], row["subgroup"]), ("lab", "2"))
            subject_count = get_db().execute("SELECT count(*) FROM subjects").fetchone()[0]
        for path in ("/schedule?group=1", "/admin/schedule"):
            html = self.client.get(path).get_data(as_text=True)
            self.assertIn("Лабораторна робота", html)
            self.assertIn("Підгрупа 2", html)
        calendar = self.client.get("/schedule/1/calendar.ics").get_data(as_text=True)
        self.assertIn("Лабораторна робота", calendar)
        self.assertIn("Підгрупа 2", calendar)
        data.update(lesson_type="lecture", subgroup="")
        self.client.post(f"/admin/schedule/{entry_id}", data=data)
        invalid = dict(data, lesson_type="unknown", subgroup="100")
        self.client.post(f"/admin/schedule/{entry_id}", data=invalid)
        self.client.post("/admin/catalog/subjects", data={"name": "Основи програмування (ЛР 2)"})
        with app.app_context():
            row = get_db().execute("SELECT * FROM schedule_entries WHERE id=?", (entry_id,)).fetchone()
            self.assertEqual((row["lesson_type"], row["subgroup"]), ("lecture", ""))
            self.assertEqual(get_db().execute("SELECT count(*) FROM subjects").fetchone()[0], subject_count)


if __name__ == "__main__":
    unittest.main()
