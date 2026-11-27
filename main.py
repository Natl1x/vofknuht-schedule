"""Вебзастосунок для перегляду та адміністрування розкладу ВоФК НУХТ."""

import sqlite3
import subprocess
from datetime import UTC, date, datetime, time, timedelta
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from api import api
from api import error as api_error
from lesson_fields import LESSON_TYPES, SUBGROUPS, split_subject_name
from models import get_db, init_app

app = Flask(__name__)
app.config.update(
    SECRET_KEY="change-this-demo-secret-before-production",
    DATABASE=str(Path(app.root_path) / "instance" / "schedule.db"),
    UPLOAD_FOLDER=str(Path(app.root_path) / "instance" / "uploads"),
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,
)
app.register_blueprint(api)
init_app(app)
Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

DAYS = {1: "Понеділок", 2: "Вівторок", 3: "Середа", 4: "Четвер", 5: "П’ятниця"}
NAVIGATION = (("schedule", "Розклад"), ("feedback", "Відгуки"))


@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = (
        get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if user_id
        else None
    )


@app.context_processor
def shared_context():
    return {
        "navigation": NAVIGATION,
        "days": DAYS,
        "lesson_types": LESSON_TYPES,
        "subgroups": SUBGROUPS,
    }


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                flash("Увійдіть, щоб продовжити.", "error")
                return redirect(url_for("login", next=request.path))
            if g.user["role"] != role:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def schedule_query(where="", params=()):
    return (
        get_db()
        .execute(
            """SELECT e.*, gr.name AS group_name, s.name AS subject_name, u.full_name AS teacher_name,
                  c.name AS classroom_name, lc.body AS comment
           FROM schedule_entries e JOIN groups gr ON gr.id = e.group_id
           JOIN subjects s ON s.id = e.subject_id JOIN users u ON u.id = e.teacher_id
           JOIN classrooms c ON c.id = e.classroom_id
           LEFT JOIN lesson_comments lc ON lc.schedule_entry_id = e.id """
            + where
            + " ORDER BY e.day_of_week, e.pair_number",
            params,
        )
        .fetchall()
    )


@app.route("/")
def home():
    """Головний маршрут веде безпосередньо до вибору розкладу."""
    return redirect(url_for("schedule"))


@app.route("/schedule")
def schedule():
    groups = get_db().execute("SELECT * FROM groups ORDER BY name").fetchall()
    group_id = request.args.get("group", type=int)
    where, params = "WHERE e.is_published = 1 AND 1 = 0", []
    if group_id:
        where = "WHERE e.is_published = 1 AND e.group_id = ?"
        params.append(group_id)
    entries = schedule_query(where, params)
    week_start = date.today() - timedelta(days=date.today().weekday())
    schedule_days = []
    if group_id:
        for day_number, day_name in DAYS.items():
            day_entries = [
                entry for entry in entries if entry["day_of_week"] == day_number
            ]
            schedule_days.append(
                {
                    "name": day_name,
                    "date": week_start + timedelta(days=day_number - 1),
                    "entries": day_entries,
                }
            )
    return render_template(
        "schedule.html",
        entries=entries,
        schedule_days=schedule_days,
        groups=groups,
        selected_group=group_id,
        today=date.today(),
    )


def ical_escape(value):
    """Екранує текст відповідно до формату iCalendar."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def recognize_schedule_photo(image_path):
    """Повертає текст із фото через локальний Tesseract, якщо він доступний."""
    trained_data_dir = Path(app.root_path) / "instance" / "tessdata"
    command = [
        "tesseract",
        str(image_path),
        "stdout",
        "--tessdata-dir",
        str(trained_data_dir),
        "-l",
        "ukr",
        "--psm",
        "6",
    ]
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=45
        )
        return result.stdout.strip()
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        return ""


@app.route("/schedule/<int:group_id>/calendar.ics")
def calendar_export(group_id):
    """Віддає опублікований розклад групи як файл для календарних застосунків."""
    group = (
        get_db().execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
    )
    if group is None:
        abort(404)
    entries = schedule_query("WHERE e.is_published = 1 AND e.group_id = ?", (group_id,))
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//VoFK NUHT//Schedule//UK",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:" + ical_escape("Розклад " + group["name"]),
    ]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for entry in entries:
        lesson_date = monday + timedelta(days=entry["day_of_week"] - 1)
        starts = datetime.combine(
            lesson_date, time.fromisoformat(entry["starts_at"])
        ).strftime("%Y%m%dT%H%M%S")
        ends = datetime.combine(
            lesson_date, time.fromisoformat(entry["ends_at"])
        ).strftime("%Y%m%dT%H%M%S")
        description = (
            f"Викладач: {entry['teacher_name']}\nАудиторія: {entry['classroom_name']}"
        )
        if entry["comment"]:
            description += f"\nКоментар: {entry['comment']}"
        description += f"\nГрупа: {group['name']}\n{SUBGROUPS[entry['subgroup']]}"
        if entry["lesson_type"]:
            description += f"\nТип заняття: {LESSON_TYPES[entry['lesson_type']]}"
        lines.extend(
            (
                "BEGIN:VEVENT",
                f"UID:vofknuht-{entry['id']}@schedule.local",
                f"DTSTAMP:{stamp}",
                f"DTSTART;TZID=Europe/Kyiv:{starts}",
                f"DTEND;TZID=Europe/Kyiv:{ends}",
                "RRULE:FREQ=WEEKLY",
                f"SUMMARY:{ical_escape(entry['subject_name'])}",
                f"LOCATION:{ical_escape(entry['classroom_name'])}",
                f"DESCRIPTION:{ical_escape(description)}",
                "END:VEVENT",
            )
        )
    lines.append("END:VCALENDAR")
    return Response(
        "\r\n".join(lines) + "\r\n",
        mimetype="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="schedule-{group["name"]}.ics"'
        },
    )


@app.route("/feedback", methods=("GET", "POST"))
def feedback():
    if request.method == "POST":
        name, email, message = (
            request.form.get(key, "").strip() for key in ("name", "email", "message")
        )
        if not name or not email or not message:
            flash("Заповніть усі поля відгуку.", "error")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO feedback (name, email, message) VALUES (?, ?, ?)",
                (name, email, message),
            )
            db.commit()
            flash("Дякуємо! Відгук збережено.", "success")
            return redirect(url_for("feedback"))
    return render_template(
        "feedback.html",
        feedbacks=get_db()
        .execute("SELECT * FROM feedback ORDER BY created_at DESC")
        .fetchall(),
    )


@app.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        user = (
            get_db()
            .execute(
                "SELECT * FROM users WHERE email = ?",
                (request.form.get("email", "").strip().lower(),),
            )
            .fetchone()
        )
        if user and check_password_hash(
            user["password_hash"], request.form.get("password", "")
        ):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(
                request.args.get("next")
                or (
                    url_for("admin")
                    if user["role"] == "admin"
                    else url_for("teacher_dashboard")
                )
            )
        flash("Невірний email або пароль.", "error")
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    flash("Ви вийшли з облікового запису.", "success")
    return redirect(url_for("schedule"))


@app.route("/teacher")
@role_required("teacher")
def teacher_dashboard():
    return render_template(
        "teacher_dashboard.html",
        lessons=schedule_query("WHERE e.teacher_id = ?", (g.user["id"],)),
    )


@app.post("/teacher/lessons/<int:lesson_id>/comment")
@role_required("teacher")
def save_comment(lesson_id):
    body = request.form.get("body", "").strip()
    lesson = (
        get_db()
        .execute(
            "SELECT id FROM schedule_entries WHERE id = ? AND teacher_id = ?",
            (lesson_id, g.user["id"]),
        )
        .fetchone()
    )
    if lesson is None:
        abort(403)
    if not body:
        flash("Коментар не може бути порожнім.", "error")
    else:
        db = get_db()
        db.execute(
            """INSERT INTO lesson_comments (schedule_entry_id, teacher_id, body) VALUES (?, ?, ?)
            ON CONFLICT(schedule_entry_id, teacher_id) DO UPDATE SET body = excluded.body, updated_at = CURRENT_TIMESTAMP""",
            (lesson_id, g.user["id"], body),
        )
        db.commit()
        flash("Коментар до пари збережено.", "success")
    return redirect(url_for("teacher_dashboard"))


@app.post("/teacher/lessons/<int:lesson_id>/comment/delete")
@role_required("teacher")
def delete_comment(lesson_id):
    db = get_db()
    db.execute(
        "DELETE FROM lesson_comments WHERE schedule_entry_id = ? AND teacher_id = ?",
        (lesson_id, g.user["id"]),
    )
    db.commit()
    flash("Коментар видалено.", "success")
    return redirect(url_for("teacher_dashboard"))


@app.route("/admin")
@role_required("admin")
def admin():
    db = get_db()
    counts = {
        name: db.execute(f"SELECT COUNT(*) AS count FROM {name}").fetchone()["count"]
        for name in (
            "users",
            "groups",
            "subjects",
            "classrooms",
            "schedule_entries",
            "feedback",
        )
    }
    return render_template("admin.html", counts=counts)


@app.route("/admin/teachers", methods=("GET", "POST"))
@role_required("admin")
def admin_teachers():
    if request.method == "POST":
        name, email, password = (
            request.form.get(key, "").strip()
            for key in ("full_name", "email", "password")
        )
        if not name or not email or len(password) < 6:
            flash("Вкажіть ПІБ, email і пароль щонайменше з 6 символів.", "error")
        else:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, 'teacher')",
                    (name, email.lower(), generate_password_hash(password)),
                )
                db.commit()
                flash("Акаунт викладача створено.", "success")
            except sqlite3.IntegrityError:
                flash("Такий email уже зареєстровано.", "error")
        return redirect(url_for("admin_teachers"))
    return render_template(
        "admin_teachers.html",
        teachers=get_db()
        .execute("SELECT * FROM users WHERE role = 'teacher' ORDER BY full_name")
        .fetchall(),
    )


@app.post("/admin/teachers/<int:user_id>/delete")
@role_required("admin")
def delete_teacher(user_id):
    try:
        db = get_db()
        db.execute("DELETE FROM users WHERE id = ? AND role = 'teacher'", (user_id,))
        db.commit()
        flash("Викладача видалено.", "success")
    except sqlite3.IntegrityError:
        flash("Не можна видалити викладача, закріпленого за парами.", "error")
    return redirect(url_for("admin_teachers"))


@app.route("/admin/catalog/<kind>", methods=("GET", "POST"))
@role_required("admin")
def admin_catalog(kind):
    titles = {"groups": "Групи", "subjects": "Предмети", "classrooms": "Аудиторії"}
    if kind not in titles:
        abort(404)
    if request.method == "POST":
        name, course = (
            request.form.get("name", "").strip(),
            request.form.get("course", type=int),
        )
        if kind == "subjects":
            name, _, _ = split_subject_name(name)
            if any(
                row["name"].casefold() == name.casefold()
                for row in get_db().execute("SELECT name FROM subjects")
            ):
                flash(
                    "Ця дисципліна вже є. Тип заняття та підгрупу оберіть у розкладі.",
                    "error",
                )
                return redirect(url_for("admin_catalog", kind=kind))
        if not name or (kind == "groups" and course not in (1, 2, 3, 4)):
            flash("Перевірте введені дані.", "error")
        else:
            try:
                db = get_db()
                if kind == "groups":
                    db.execute(
                        "INSERT INTO groups (name, course) VALUES (?, ?)",
                        (name, course),
                    )
                else:
                    db.execute(f"INSERT INTO {kind} (name) VALUES (?)", (name,))
                db.commit()
                flash("Запис додано.", "success")
            except sqlite3.IntegrityError:
                flash("Такий запис уже існує.", "error")
        return redirect(url_for("admin_catalog", kind=kind))
    return render_template(
        "admin_catalog.html",
        kind=kind,
        title=titles[kind],
        rows=get_db().execute(f"SELECT * FROM {kind} ORDER BY name").fetchall(),
    )


@app.post("/admin/catalog/<kind>/<int:row_id>/delete")
@role_required("admin")
def delete_catalog(kind, row_id):
    if kind not in {"groups", "subjects", "classrooms"}:
        abort(404)
    try:
        db = get_db()
        db.execute(f"DELETE FROM {kind} WHERE id = ?", (row_id,))
        db.commit()
        flash("Запис видалено.", "success")
    except sqlite3.IntegrityError:
        flash("Не можна видалити запис, який використовується в розкладі.", "error")
    return redirect(url_for("admin_catalog", kind=kind))


@app.route("/admin/schedule", methods=("GET", "POST"))
@app.route("/admin/schedule/<int:entry_id>", methods=("GET", "POST"))
@role_required("admin")
def admin_schedule(entry_id=None):
    db = get_db()
    entry = (
        db.execute(
            "SELECT * FROM schedule_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if entry_id
        else None
    )
    if entry_id and entry is None:
        abort(404)
    if request.method == "POST":
        values = tuple(
            request.form.get(key, type=int)
            for key in (
                "group_id",
                "subject_id",
                "teacher_id",
                "classroom_id",
                "day_of_week",
                "pair_number",
            )
        )
        lesson_type = request.form.get("lesson_type", "")
        subgroup = request.form.get("subgroup", "")
        times = {
            1: ("08:00", "09:20"),
            2: ("09:30", "10:50"),
            3: ("11:20", "12:40"),
            4: ("12:50", "14:10"),
            5: ("14:20", "15:40"),
            6: ("15:50", "17:10"),
        }
        try:
            if lesson_type not in LESSON_TYPES or subgroup not in SUBGROUPS:
                raise ValueError("Оберіть коректний тип заняття та підгрупу.")
            payload = (
                values
                + times[values[5]]
                + (1 if request.form.get("is_published") else 0, lesson_type, subgroup)
            )
            if entry:
                db.execute(
                    "UPDATE schedule_entries SET group_id=?, subject_id=?, teacher_id=?, classroom_id=?, day_of_week=?, pair_number=?, starts_at=?, ends_at=?, is_published=?, lesson_type=?, subgroup=? WHERE id=?",
                    payload + (entry_id,),
                )
            else:
                db.execute(
                    "INSERT INTO schedule_entries (group_id, subject_id, teacher_id, classroom_id, day_of_week, pair_number, starts_at, ends_at, is_published, lesson_type, subgroup) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    payload,
                )
            db.commit()
            flash("Пару збережено.", "success")
            return redirect(url_for("admin_schedule"))
        except ValueError as error:
            flash(str(error), "error")
        except (sqlite3.IntegrityError, KeyError, TypeError):
            flash(
                "Конфлікт або некоректні дані: група, викладач чи аудиторія вже зайняті.",
                "error",
            )
    data = {
        "groups": db.execute("SELECT * FROM groups ORDER BY name").fetchall(),
        "subjects": db.execute("SELECT * FROM subjects ORDER BY name").fetchall(),
        "teachers": db.execute(
            "SELECT * FROM users WHERE role = 'teacher' ORDER BY full_name"
        ).fetchall(),
        "classrooms": db.execute("SELECT * FROM classrooms ORDER BY name").fetchall(),
    }
    return render_template(
        "admin_schedule.html", entries=schedule_query(), entry=entry, **data
    )


@app.post("/admin/schedule/<int:entry_id>/delete")
@role_required("admin")
def delete_schedule(entry_id):
    db = get_db()
    db.execute("DELETE FROM schedule_entries WHERE id = ?", (entry_id,))
    db.commit()
    flash("Пару видалено.", "success")
    return redirect(url_for("admin_schedule"))


@app.route("/admin/feedback")
@role_required("admin")
def admin_feedback():
    return render_template(
        "admin_feedback.html",
        feedbacks=get_db()
        .execute("SELECT * FROM feedback ORDER BY created_at DESC")
        .fetchall(),
    )


@app.post("/admin/feedback/<int:feedback_id>/delete")
@role_required("admin")
def delete_feedback(feedback_id):
    db = get_db()
    db.execute("DELETE FROM feedback WHERE id = ?", (feedback_id,))
    db.commit()
    flash("Відгук видалено.", "success")
    return redirect(url_for("admin_feedback"))


@app.route("/admin/import", methods=("GET", "POST"))
@role_required("admin")
def admin_import():
    """Приймає оригінал фото розкладу для наступного етапу розпізнавання."""
    if request.method == "POST":
        image = request.files.get("schedule_photo")
        allowed_extensions = {"png", "jpg", "jpeg", "webp"}
        extension = (
            image.filename.rsplit(".", 1)[-1].lower()
            if image and "." in image.filename
            else ""
        )
        if image is None or not image.filename or extension not in allowed_extensions:
            flash("Оберіть зображення у форматі PNG, JPG або WEBP.", "error")
        else:
            original_name = secure_filename(image.filename)
            stored_name = f"{uuid4().hex}.{extension}"
            image_path = Path(app.config["UPLOAD_FOLDER"]) / stored_name
            image.save(image_path)
            ocr_text = recognize_schedule_photo(image_path)
            db = get_db()
            db.execute(
                "INSERT INTO schedule_imports (original_name, stored_name, ocr_text) VALUES (?, ?, ?)",
                (original_name, stored_name, ocr_text),
            )
            db.commit()
            flash(
                "Фото збережено й текст розпізнано. Перевірте результат перед створенням пар.",
                "success",
            )
        return redirect(url_for("admin_import"))
    imports = (
        get_db()
        .execute("SELECT * FROM schedule_imports ORDER BY created_at DESC")
        .fetchall()
    )
    return render_template("admin_import.html", imports=imports)


@app.errorhandler(403)
def forbidden(_error):
    if request.path.startswith("/api/"):
        return api_error("Недостатньо прав.", 403)
    return render_template(
        "error.html",
        title="Доступ заборонено",
        message="У вас немає прав для цієї сторінки.",
    ), 403


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return api_error("Маршрут не знайдено.", 404)
    return render_template("404.html"), 404


@app.errorhandler(405)
def method_not_allowed(_error):
    if request.path.startswith("/api/"):
        return api_error("Метод не підтримується.", 405)
    return render_template(
        "error.html", title="Метод не підтримується", message="Спробуйте іншу дію."
    ), 405


@app.errorhandler(500)
def server_error(_error):
    if request.path.startswith("/api/"):
        return api_error("Внутрішня помилка сервера.", 500)
    return render_template(
        "error.html", title="Помилка сервера", message="Спробуйте пізніше."
    ), 500


@app.get("/apidocs/")
def api_docs():
    return render_template("apidocs.html")


@app.get("/openapi.json")
def openapi_spec():
    return Response(
        (Path(app.root_path) / "docs" / "openapi.json").read_text(encoding="utf-8"),
        mimetype="application/json",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
