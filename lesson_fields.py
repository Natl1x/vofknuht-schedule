"""Окремі характеристики заняття та розбір старих назв дисциплін."""
import re

LESSON_TYPES = {
    "": "Не вказано",
    "lecture": "Лекція",
    "practice": "Практичне заняття",
    "lab": "Лабораторна робота",
}
SUBGROUPS = {"": "Уся група", **{str(n): f"Підгрупа {n}" for n in range(1, 10)}}


def split_subject_name(name):
    """Виділяє лише відомі кінцеві позначення, зберігаючи інші дужки."""
    name = " ".join(name.split())
    match = re.fullmatch(
        r"(.+?)\s*\((лр|л\.?|пр\.?)\s*(\d|[iі]{1,3})?\)",
        name, flags=re.IGNORECASE,
    )
    if not match:
        return name, "", ""
    base, kind, subgroup = match.groups()
    kind = {"лр": "lab", "л": "lecture", "пр": "practice"}[kind.lower().rstrip(".")]
    subgroup = (subgroup or "").lower().replace("і", "i")
    subgroup = {"i": "1", "ii": "2", "iii": "3"}.get(subgroup, subgroup)
    if subgroup not in SUBGROUPS:
        return name, "", ""
    return base.strip(), kind, subgroup
