"""Обробка даних пасажирських рейсів для лабораторної роботи №1."""

import csv
import math
from datetime import date
from pathlib import Path
from statistics import median


def read_flights(path: Path) -> tuple[list[dict], list[str]]:
    """Зчитати коректні рейси з CSV та повернути повідомлення про пропущені рядки."""
    flights = []
    warnings = []
    required = {"flight_number", "date", "direction", "passengers", "capacity", "ticket_price"}

    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"CSV має містити колонки: {', '.join(sorted(required))}")

        for line_number, row in enumerate(reader, start=2):
            try:
                number = (row["flight_number"] or "").strip()
                direction = (row["direction"] or "").strip()
                flight_date = date.fromisoformat((row["date"] or "").strip())
                passengers = int((row["passengers"] or "").strip())
                capacity = int((row["capacity"] or "").strip())
                price = float((row["ticket_price"] or "").strip())
                if not number or not direction:
                    raise ValueError("порожній номер рейсу або напрямок")
                if (
                    capacity <= 0
                    or passengers < 0
                    or passengers > capacity
                    or not math.isfinite(price)
                    or price < 0
                ):
                    raise ValueError("пасажири, місткість або ціна поза допустимими межами")
            except (ValueError, TypeError, OverflowError) as error:
                warnings.append(f"Рядок {line_number} пропущено: {error}")
                continue

            flights.append({
                "flight_number": number,
                "date": flight_date.isoformat(),
                "direction": direction,
                "passengers": passengers,
                "capacity": capacity,
                "ticket_price": price,
            })

    return flights, warnings


def revenue_by_direction(flights: list[dict]) -> dict[str, float]:
    """Підрахувати сумарну виручку за кожним напрямком."""
    revenue = {}
    for flight in flights:
        direction = flight["direction"]
        revenue[direction] = revenue.get(direction, 0.0) + (
            flight["passengers"] * flight["ticket_price"]
        )
    return revenue


def average_occupancy(flights: list[dict]) -> float:
    """Обчислити частку зайнятих місць серед усіх місць на всіх рейсах."""
    total_capacity = sum(flight["capacity"] for flight in flights)
    if total_capacity == 0:
        return 0.0
    return sum(flight["passengers"] for flight in flights) / total_capacity


def most_popular_direction(flights: list[dict]) -> tuple[str, int] | None:
    """Знайти напрямок із найбільшою сумарною кількістю пасажирів."""
    totals = {}
    for flight in flights:
        direction = flight["direction"]
        totals[direction] = totals.get(direction, 0) + flight["passengers"]
    return max(totals.items(), key=lambda item: item[1]) if totals else None


def median_passengers(flights: list[dict]) -> float:
    """Знайти медіанну кількість пасажирів одного рейсу."""
    return float(median(flight["passengers"] for flight in flights)) if flights else 0.0


def occupancy_category(flight: dict) -> str:
    """Віднести рейс до категорії за часткою зайнятих місць."""
    occupancy = flight["passengers"] / flight["capacity"]
    if occupancy >= 0.9:
        return "висока"
    if occupancy >= 0.7:
        return "середня"
    return "низька"


def sort_by_revenue(flights: list[dict]) -> list[dict]:
    """Повернути рейси за спаданням виручки, не змінюючи початковий список."""
    return sorted(
        flights,
        key=lambda flight: flight["passengers"] * flight["ticket_price"],
        reverse=True,
    )
