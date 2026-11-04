"""Перевірки доступності сторінок, навігації та навчального вмісту."""
import unittest
from html.parser import HTMLParser
from main import app


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.active = []
        self.headings = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.links.append(attrs.get("href", ""))
            if attrs.get("aria-current") == "page":
                self.active.append(attrs["href"])
        if tag == "h1":
            self.headings += 1


class SiteTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_pages_navigation_and_links(self):
        for path in ("/", "/schedule", "/about", "/help"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                parser = PageParser()
                parser.feed(html)
                self.assertEqual(parser.active, [path])
                self.assertEqual(parser.headings, 1)
                self.assertIn('lang="uk"', html)
                self.assertIn('name="viewport"', html)
                for target in ("/", "/schedule", "/about", "/help"):
                    self.assertIn(target, parser.links)
                for link in parser.links:
                    if link.startswith("/"):
                        self.assertEqual(self.client.get(link).status_code, 200)

    def test_schedule_is_labeled_and_complete(self):
        html = self.client.get("/schedule").get_data(as_text=True)
        self.assertIn("Демонстраційні дані", html)
        self.assertEqual(html.count('class="day-card"'), 5)
        self.assertEqual(html.count('class="pair"'), 15)
        for time in ("08:00–09:20", "09:30–10:50", "11:20–12:40"):
            self.assertIn(time, html)
        self.assertEqual(html.count("10 хв"), 5)
        self.assertEqual(html.count("30 хв — велика перерва"), 5)

    def test_home_and_help_show_schedule_times_and_breaks(self):
        home = self.client.get("/").get_data(as_text=True)
        help_page = self.client.get("/help").get_data(as_text=True)
        self.assertIn("08:00–09:20", home)
        self.assertIn("09:30–10:50", home)
        self.assertIn("11:20–12:40", home)
        self.assertIn("Велика перерва · 30 хв", home)
        normalized_help = " ".join(help_page.split())
        self.assertIn("починається о 08:00", normalized_help)
        self.assertIn("після другої — велика перерва 30 хвилин", normalized_help)

    def test_styles_and_not_found(self):
        with self.client.get("/static/css/style.css") as stylesheet:
            self.assertEqual(stylesheet.status_code, 200)
        response = self.client.get("/missing")
        self.assertEqual(response.status_code, 404)
        self.assertIn("На головну", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
