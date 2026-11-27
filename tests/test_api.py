"""Integration checks for API data, roles, validation, and versioning."""

import os
import tempfile
import unittest

from main import app
from models import get_db, init_db


class ApiTests(unittest.TestCase):
    def setUp(self):
        fd, self.database = tempfile.mkstemp()
        os.close(fd)
        app.config.update(
            TESTING=True, DATABASE=self.database, SECRET_KEY="api-test-secret"
        )
        with app.app_context():
            init_db()
        self.client = app.test_client()

    def tearDown(self):
        os.unlink(self.database)

    def login(self, role="admin"):
        email = "admin@vofknuht.local" if role == "admin" else "melnyk@vofknuht.local"
        password = "admin123" if role == "admin" else "teacher123"
        response = self.client.post(
            "/api/v1/session", json={"email": email, "password": password}
        )
        self.assertEqual(response.status_code, 200)

    def test_public_versions_and_json_errors(self):
        self.assertEqual(
            self.client.get("/api/v1/groups").json["groups"][0]["name"], "ІПЗ-21"
        )
        self.assertTrue(self.client.get("/api/v1/subjects").json["subjects"])
        v1 = self.client.get("/api/v1/groups/1/lessons").json["lessons"][0]
        v2 = self.client.get("/api/v2/lessons/1").json["lesson"]
        self.assertNotIn("date", v1)
        self.assertIn("date", v2)
        self.assertEqual(self.client.get("/api/v1/groups/999/lessons").status_code, 404)
        for path, method in (
            ("/api/v8/groups", "get"),
            ("/api/v1/missing", "get"),
            ("/api/v1/groups", "post"),
        ):
            response = getattr(self.client, method)(path)
            self.assertIn("error", response.json)
        self.assertEqual(self.client.get("/apidocs/").status_code, 200)
        self.assertIn("paths", self.client.get("/openapi.json").json)

    def test_feedback_validation_and_admin_access(self):
        self.assertEqual(self.client.get("/api/v1/feedback").json["feedback"], [])
        self.assertEqual(
            self.client.post("/api/v1/feedback", json={"name": "A"}).status_code, 400
        )
        created = self.client.post(
            "/api/v1/feedback",
            json={
                "name": "Марія",
                "email": "m@example.com",
                "message": "Уточніть пару",
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertNotIn(
            "email", self.client.get("/api/v1/feedback").json["feedback"][0]
        )
        self.login("teacher")
        self.assertNotIn(
            "email", self.client.get("/api/v1/feedback").json["feedback"][0]
        )
        self.login("admin")
        self.assertEqual(
            self.client.get("/api/v1/feedback").json["feedback"][0]["message"],
            "Уточніть пару",
        )
        self.assertEqual(
            self.client.get("/api/v1/feedback").json["feedback"][0]["email"],
            "m@example.com",
        )

    def test_admin_lesson_crud_conflicts_and_publication(self):
        payload = {
            "group_id": 1,
            "subject_id": 1,
            "teacher_id": 2,
            "classroom_id": 1,
            "day_of_week": 5,
            "pair_number": 4,
            "lesson_type": "lab",
            "subgroup": "2",
            "is_published": True,
        }
        self.assertEqual(
            self.client.post("/api/v1/lessons", json=payload).status_code, 401
        )
        self.login()
        self.assertEqual(
            self.client.post(
                "/api/v1/lessons", json={**payload, "pair_number": "4"}
            ).status_code,
            400,
        )
        created = self.client.post("/api/v2/lessons", json=payload)
        self.assertEqual(created.status_code, 201)
        entry_id = created.json["lesson"]["id"]
        self.assertEqual(created.json["lesson"]["lesson_type"], "lab")
        self.assertEqual(
            self.client.post("/api/v1/lessons", json=payload).status_code, 409
        )
        changed = self.client.patch(
            f"/api/v2/lessons/{entry_id}",
            json={"is_published": False, "pair_number": 5},
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json["lesson"]["starts_at"], "14:20")
        self.assertEqual(
            self.client.get(f"/api/v2/lessons/{entry_id}").status_code, 200
        )
        self.client.delete("/api/v1/session")
        self.assertEqual(
            self.client.get(f"/api/v2/lessons/{entry_id}").status_code, 404
        )
        self.login()
        self.assertEqual(
            self.client.delete(f"/api/v1/lessons/{entry_id}").status_code, 204
        )
        self.assertEqual(
            self.client.delete(f"/api/v1/lessons/{entry_id}").status_code, 404
        )

    def test_teacher_comments_are_limited_to_own_lessons(self):
        self.login("teacher")
        self.assertEqual(
            self.client.put(
                "/api/v1/lessons/2/comment", json={"body": "Чуже"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.put("/api/v1/lessons/1/comment", json={"body": ""}).status_code,
            400,
        )
        created = self.client.put(
            "/api/v1/lessons/1/comment", json={"body": "Візьміть ноутбуки"}
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(
            self.client.get("/api/v2/lessons/1").json["lesson"]["comment"],
            "Візьміть ноутбуки",
        )
        self.assertEqual(
            self.client.put(
                "/api/v1/lessons/1/comment", json={"body": "Новий текст"}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.delete("/api/v1/lessons/1/comment").status_code, 204
        )
        with app.app_context():
            self.assertIsNone(
                get_db()
                .execute("SELECT 1 FROM lesson_comments WHERE schedule_entry_id=1")
                .fetchone()
            )


if __name__ == "__main__":
    unittest.main()
