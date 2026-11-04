"""Вебзастосунок розкладу ВоФК НУХТ."""
from flask import Flask, render_template

app = Flask(__name__)
NAVIGATION = (("home", "Головна"), ("schedule", "Розклад"),
              ("about", "Про нас"), ("help_page", "Довідка"))


@app.context_processor
def navigation_context():
    """Спільна навігація доступна в усіх шаблонах."""
    return {"navigation": NAVIGATION}


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/schedule")
def schedule():
    # Вигадані навчальні дані, не офіційний розклад коледжу.
    days = (
        ("Понеділок", ("Основи програмування", "Математика", "Українська мова")),
        ("Вівторок", ("Іноземна мова", "Інформатика", "Фізична культура")),
        ("Середа", ("Математика", "Основи програмної інженерії", "Історія України")),
        ("Четвер", ("Основи програмування", "Іноземна мова", "Інформатика")),
        ("П’ятниця", ("Українська мова", "Основи програмної інженерії", "Фізична культура")),
    )
    return render_template("schedule.html", days=days,
                           times=("08:30–09:50", "10:00–11:20", "11:40–13:00"))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/help")
def help_page():
    return render_template("help.html")


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
