"""Перевірки розрахунків та обробки помилкових даних лабораторної №1."""

import tempfile
import unittest
from pathlib import Path

from lab01.analyzer import (
    average_occupancy,
    median_passengers,
    most_popular_direction,
    occupancy_category,
    read_flights,
    revenue_by_direction,
    sort_by_revenue,
)


class FlightAnalysisTests(unittest.TestCase):
    """Перевірити показники на контрольному наборі та стійкість до хибного CSV."""

    def test_metrics_on_sample(self):
        """Порівняти результати зі значеннями, обчисленими з навчального CSV."""
        flights, warnings = read_flights(Path(__file__).with_name("flights.csv"))
        self.assertEqual(len(flights), 10)
        self.assertEqual(warnings, [])
        self.assertEqual(sum(revenue_by_direction(flights).values()), 132440)
        self.assertAlmostEqual(average_occupancy(flights), 358 / 410)
        self.assertEqual(most_popular_direction(flights), ("Луцьк — Київ", 185))
        self.assertEqual(median_passengers(flights), 38)
        self.assertEqual(sort_by_revenue(flights)[0]["flight_number"], "109")
        self.assertEqual(occupancy_category(flights[6]), "низька")

    def test_invalid_rows_are_skipped(self):
        """Пропустити порожнє, нечислове та завелике значення без падіння."""
        csv_text = (
            "flight_number,date,direction,passengers,capacity,ticket_price\n"
            "1,2026-11-01,Луцьк — Київ, 8 ,10,100\n"
            "2,2026-11-02,Луцьк — Київ,,10,100\n"
            "3,2026-11-03,Луцьк — Київ,abc,10,100\n"
            "4,2026-11-04,Луцьк — Київ,11,10,100\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "flights.csv"
            path.write_text(csv_text, encoding="utf-8")
            flights, warnings = read_flights(path)
        self.assertEqual(len(flights), 1)
        self.assertEqual(flights[0]["passengers"], 8)
        self.assertEqual(len(warnings), 3)


if __name__ == "__main__":
    unittest.main()
