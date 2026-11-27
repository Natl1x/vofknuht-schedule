"""Консольний звіт за пасажирськими перевезеннями, варіант 10."""

import json
from pathlib import Path

from analyzer import (
    average_occupancy,
    median_passengers,
    most_popular_direction,
    occupancy_category,
    read_flights,
    revenue_by_direction,
    sort_by_revenue,
)


def main() -> None:
    """Прочитати рейси, показати показники та зберегти оброблені дані в JSON."""
    directory = Path(__file__).resolve().parent
    flights, warnings = read_flights(directory / "flights.csv")
    for warning in warnings:
        print(warning)
    if not flights:
        print("Коректних рейсів немає.")
        return

    revenues = revenue_by_direction(flights)
    popular = most_popular_direction(flights)
    print(f"Оброблено рейсів: {len(flights)}")
    print("Виручка за напрямками:")
    for direction, amount in sorted(revenues.items()):
        print(f"  {direction}: {amount:.2f} грн")
    print(f"Загальна виручка: {sum(revenues.values()):.2f} грн")
    print(f"Середня заповненість: {average_occupancy(flights):.1%}")
    print(f"Найпопулярніший напрямок: {popular[0]} ({popular[1]} пасажирів)")
    print(f"Медіана пасажирів на рейс: {median_passengers(flights):g}")

    processed = []
    for flight in sort_by_revenue(flights):
        # JSON містить похідні показники, тому первинний CSV залишається без змін.
        processed.append({
            **flight,
            "revenue": round(flight["passengers"] * flight["ticket_price"], 2),
            "occupancy_percent": round(100 * flight["passengers"] / flight["capacity"], 1),
            "occupancy_category": occupancy_category(flight),
        })
    output = directory / "processed_flights.json"
    output.write_text(json.dumps(processed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Оброблені дані збережено: {output.name}")


if __name__ == "__main__":
    main()
