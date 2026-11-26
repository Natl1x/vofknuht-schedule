"""JSON API for the college schedule. Both versions share the same database."""
from datetime import date, timedelta
import sqlite3

from flask import Blueprint, current_app, g, jsonify, request, session, url_for
from werkzeug.security import check_password_hash

from lesson_fields import LESSON_TYPES, SUBGROUPS
from models import get_db

api = Blueprint("api", __name__, url_prefix="/api/<version>")
TIMES = {1: ("08:00", "09:20"), 2: ("09:30", "10:50"), 3: ("11:20", "12:40"),
         4: ("12:50", "14:10"), 5: ("14:20", "15:40"), 6: ("15:50", "17:10")}
FIELDS = {"group_id", "subject_id", "teacher_id", "classroom_id", "day_of_week", "pair_number",
          "lesson_type", "subgroup", "is_published"}


def error(message, status):
    return jsonify(error={"message": message, "status": status}), status


@api.url_value_preprocessor
def check_version(_endpoint, values):
    if values["version"] not in {"v1", "v2"}:
        values["version"] = "invalid"


@api.before_request
def reject_unknown_version():
    if request.view_args["version"] == "invalid":
        return error("Версію API не знайдено.", 404)


def user_with_role(role):
    if g.user is None:
        return error("Потрібен вхід у систему.", 401)
    if g.user["role"] != role:
        return error("Недостатньо прав.", 403)
    return None


def json_body():
    if not request.is_json:
        return None, error("Очікується JSON (Content-Type: application/json).", 415)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, error("Тіло запиту має бути JSON-об’єктом.", 400)
    return data, None


def lesson_row(entry_id, *, published_only=False):
    clause = " AND e.is_published = 1" if published_only else ""
    return get_db().execute("""SELECT e.*, gr.name AS group_name, s.name AS subject_name,
           u.full_name AS teacher_name, c.name AS classroom_name, lc.body AS comment
           FROM schedule_entries e JOIN groups gr ON gr.id=e.group_id
           JOIN subjects s ON s.id=e.subject_id JOIN users u ON u.id=e.teacher_id
           JOIN classrooms c ON c.id=e.classroom_id
           LEFT JOIN lesson_comments lc ON lc.schedule_entry_id=e.id
           WHERE e.id=?""" + clause, (entry_id,)).fetchone()


def lesson_json(row, version):
    data = {"id": row["id"], "group_id": row["group_id"], "group": row["group_name"],
            "subject_id": row["subject_id"], "subject": row["subject_name"],
            "teacher_id": row["teacher_id"], "teacher": row["teacher_name"],
            "classroom_id": row["classroom_id"], "classroom": row["classroom_name"],
            "day_of_week": row["day_of_week"], "pair_number": row["pair_number"],
            "starts_at": row["starts_at"], "ends_at": row["ends_at"]}
    if version == "v2":
        monday = date.today() - timedelta(days=date.today().weekday())
        data.update(date=(monday + timedelta(days=row["day_of_week"] - 1)).isoformat(),
                    lesson_type=row["lesson_type"], subgroup=row["subgroup"],
                    comment=row["comment"], is_published=bool(row["is_published"]))
    return data


def validate_lesson(data, existing=None):
    if set(data) - FIELDS:
        return None, "Невідомі поля: " + ", ".join(sorted(set(data) - FIELDS))
    values = {key: (bool(existing[key]) if key == "is_published" else existing[key]) for key in FIELDS} if existing else {}
    values.update(data)
    if set(values) != FIELDS:
        return None, "Потрібні поля: " + ", ".join(sorted(FIELDS - set(values)))
    for key in ("group_id", "subject_id", "teacher_id", "classroom_id", "day_of_week", "pair_number"):
        if type(values[key]) is not int or values[key] < 1:
            return None, f"{key} має бути додатним цілим числом."
    if values["day_of_week"] not in range(1, 6) or values["pair_number"] not in TIMES:
        return None, "День має бути 1–5, номер пари 1–6."
    if values["lesson_type"] not in LESSON_TYPES or values["subgroup"] not in SUBGROUPS:
        return None, "Некоректний тип заняття або підгрупа."
    if type(values["is_published"]) is not bool:
        return None, "is_published має бути true або false."
    db = get_db()
    for table, key, extra in (("groups", "group_id", ""), ("subjects", "subject_id", ""),
                              ("classrooms", "classroom_id", ""), ("users", "teacher_id", " AND role='teacher'")):
        if db.execute(f"SELECT 1 FROM {table} WHERE id=?" + extra, (values[key],)).fetchone() is None:
            return None, f"{key} не знайдено."
    return values, None


@api.post("/session")
def login(version):
    data, failure = json_body()
    if failure: return failure
    if set(data) != {"email", "password"} or not all(isinstance(data[k], str) for k in data):
        return error("Потрібні рядкові email і password.", 400)
    user = get_db().execute("SELECT * FROM users WHERE email=?", (data["email"].strip().lower(),)).fetchone()
    if not user or not check_password_hash(user["password_hash"], data["password"]):
        return error("Невірний email або пароль.", 401)
    session.clear()
    session["user_id"] = user["id"]
    return jsonify(user={"id": user["id"], "name": user["full_name"], "role": user["role"]})


@api.delete("/session")
def logout(version):
    session.clear()
    return "", 204


@api.get("/groups")
def groups(version):
    return jsonify(groups=[dict(row) for row in get_db().execute("SELECT id,name,course FROM groups ORDER BY name")])


@api.get("/subjects")
def subjects(version):
    return jsonify(subjects=[dict(row) for row in get_db().execute("SELECT id,name FROM subjects ORDER BY name")])


@api.get("/groups/<int:group_id>/lessons")
def group_lessons(version, group_id):
    db = get_db()
    if db.execute("SELECT 1 FROM groups WHERE id=?", (group_id,)).fetchone() is None:
        return error("Групу не знайдено.", 404)
    rows = db.execute("""SELECT e.id FROM schedule_entries e WHERE e.group_id=? AND e.is_published=1
                         ORDER BY e.day_of_week,e.pair_number""", (group_id,)).fetchall()
    return jsonify(lessons=[lesson_json(lesson_row(row["id"]), version) for row in rows])


@api.get("/lessons/<int:entry_id>")
def get_lesson(version, entry_id):
    row = lesson_row(entry_id, published_only=not (g.user and g.user["role"] == "admin"))
    return jsonify(lesson=lesson_json(row, version)) if row else error("Пару не знайдено.", 404)


@api.post("/feedback")
def create_feedback(version):
    data, failure = json_body()
    if failure: return failure
    if set(data) != {"name", "email", "message"} or any(not isinstance(v, str) or not v.strip() for v in data.values()):
        return error("Потрібні непорожні рядки name, email і message.", 400)
    if (len(data["name"].strip()) < 2 or len(data["name"]) > 100 or
            "@" not in data["email"] or len(data["email"]) > 254 or
            len(data["message"]) > 5000):
        return error("Перевірте ім’я, email і довжину повідомлення.", 400)
    db = get_db()
    cursor = db.execute("INSERT INTO feedback(name,email,message) VALUES(?,?,?)", tuple(data[k].strip() for k in ("name", "email", "message")))
    db.commit()
    return jsonify(feedback={"id": cursor.lastrowid, **{k: data[k].strip() for k in data}}), 201


@api.get("/feedback")
def list_feedback(version):
    if g.user and g.user["role"] == "admin":
        rows = get_db().execute("SELECT * FROM feedback ORDER BY id DESC")
    else:
        rows = get_db().execute("SELECT id,name,message,created_at FROM feedback ORDER BY id DESC")
    return jsonify(feedback=[dict(row) for row in rows])


@api.post("/lessons")
def create_lesson(version):
    if failure := user_with_role("admin"): return failure
    data, failure = json_body()
    if failure: return failure
    values, issue = validate_lesson(data)
    if issue: return error(issue, 400)
    db = get_db()
    try:
        cursor = db.execute("""INSERT INTO schedule_entries
            (group_id,subject_id,teacher_id,classroom_id,day_of_week,pair_number,starts_at,ends_at,lesson_type,subgroup,is_published)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", tuple(values[k] for k in ("group_id", "subject_id", "teacher_id", "classroom_id", "day_of_week", "pair_number")) + TIMES[values["pair_number"]] + (values["lesson_type"], values["subgroup"], int(values["is_published"])))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return error("Конфлікт групи, викладача або аудиторії.", 409)
    return jsonify(lesson=lesson_json(lesson_row(cursor.lastrowid), version)), 201, {"Location": url_for("api.get_lesson", version=version, entry_id=cursor.lastrowid)}


@api.patch("/lessons/<int:entry_id>")
def update_lesson(version, entry_id):
    if failure := user_with_role("admin"): return failure
    old = lesson_row(entry_id)
    if old is None: return error("Пару не знайдено.", 404)
    data, failure = json_body()
    if failure: return failure
    if not data: return error("Передайте хоча б одне поле.", 400)
    values, issue = validate_lesson(data, old)
    if issue: return error(issue, 400)
    db = get_db()
    try:
        db.execute("""UPDATE schedule_entries SET group_id=?,subject_id=?,teacher_id=?,classroom_id=?,
            day_of_week=?,pair_number=?,starts_at=?,ends_at=?,lesson_type=?,subgroup=?,is_published=? WHERE id=?""",
            tuple(values[k] for k in ("group_id", "subject_id", "teacher_id", "classroom_id", "day_of_week", "pair_number")) + TIMES[values["pair_number"]] + (values["lesson_type"], values["subgroup"], int(values["is_published"]), entry_id))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return error("Конфлікт групи, викладача або аудиторії.", 409)
    return jsonify(lesson=lesson_json(lesson_row(entry_id), version))


@api.delete("/lessons/<int:entry_id>")
def delete_lesson(version, entry_id):
    if failure := user_with_role("admin"): return failure
    db = get_db()
    cursor = db.execute("DELETE FROM schedule_entries WHERE id=?", (entry_id,))
    if not cursor.rowcount: return error("Пару не знайдено.", 404)
    db.commit()
    return "", 204


@api.put("/lessons/<int:entry_id>/comment")
def put_comment(version, entry_id):
    if failure := user_with_role("teacher"): return failure
    row = lesson_row(entry_id)
    if row is None: return error("Пару не знайдено.", 404)
    if row["teacher_id"] != g.user["id"]: return error("Ця пара закріплена за іншим викладачем.", 403)
    data, failure = json_body()
    if failure: return failure
    if set(data) != {"body"} or not isinstance(data["body"], str) or not data["body"].strip() or len(data["body"]) > 2000:
        return error("body має бути непорожнім рядком до 2000 символів.", 400)
    db = get_db()
    existed = row["comment"] is not None
    db.execute("""INSERT INTO lesson_comments(schedule_entry_id,teacher_id,body) VALUES(?,?,?)
        ON CONFLICT(schedule_entry_id,teacher_id) DO UPDATE SET body=excluded.body,updated_at=CURRENT_TIMESTAMP""",
        (entry_id, g.user["id"], data["body"].strip()))
    db.commit()
    return jsonify(comment={"lesson_id": entry_id, "body": data["body"].strip()}), 200 if existed else 201


@api.delete("/lessons/<int:entry_id>/comment")
def remove_comment(version, entry_id):
    if failure := user_with_role("teacher"): return failure
    row = lesson_row(entry_id)
    if row is None: return error("Пару не знайдено.", 404)
    if row["teacher_id"] != g.user["id"]: return error("Ця пара закріплена за іншим викладачем.", 403)
    db = get_db()
    cursor = db.execute("DELETE FROM lesson_comments WHERE schedule_entry_id=? AND teacher_id=?", (entry_id, g.user["id"]))
    if not cursor.rowcount: return error("Коментар не знайдено.", 404)
    db.commit()
    return "", 204
