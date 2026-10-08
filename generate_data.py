"""Создаёт синтетический набор данных для лабораторной работы № 2.

Значения получаются с фиксированным seed, поэтому файл materials.json
можно заново построить и получить те же данные.
"""

import json
import random
from pathlib import Path


SEED = 2026
BUDGET = 95000

MATERIALS = [
    ("Бумага A4", "пач."),
    ("Ручки шариковые", "уп."),
    ("Карандаши", "уп."),
    ("Ластики", "шт."),
    ("Маркеры", "уп."),
    ("Скотч", "шт."),
    ("Клей-карандаш", "шт."),
    ("Скобы для степлера", "уп."),
    ("Файлы-вкладыши", "уп."),
    ("Папки-регистраторы", "шт."),
    ("Картриджи чёрные", "шт."),
    ("Картриджи цветные", "шт."),
    ("Батарейки AA", "уп."),
    ("Перчатки одноразовые", "уп."),
    ("Влажные салфетки", "уп."),
    ("Средство для мытья", "л"),
    ("Пакеты для мусора", "уп."),
    ("Тетради", "уп."),
    ("Степлеры", "шт."),
    ("Линейки", "шт."),
    ("Ножницы", "шт."),
    ("Блокноты", "шт."),
    ("Канцелярские ножи", "шт."),
    ("Корректоры", "шт."),
    ("Кисти", "уп."),
    ("Гуашь", "уп."),
    ("Пластилин", "уп."),
    ("Цветная бумага", "уп."),
    ("Бумажные полотенца", "уп."),
    ("Антисептик", "л")
]


def make_materials():
    """Генерирует 30 позиций: цена, текущий запас и уровни запаса."""
    random.seed(SEED)
    result = []

    for number, (name, unit) in enumerate(MATERIALS):
        price = random.randint(80, 550)
        if number in (10, 11):
            price = random.randint(1600, 2600)

        current_stock = random.randint(0, 4)
        minimum_stock = current_stock + random.randint(3, 7)
        desired_stock = minimum_stock + random.randint(3, 8)
        maximum_stock = desired_stock + random.randint(2, 5)

        result.append({
            "name": name,
            "unit": unit,
            "unit_price": price,
            "current_stock": current_stock,
            "minimum_stock": minimum_stock,
            "desired_stock": desired_stock,
            "maximum_stock": maximum_stock,
            "priority": random.randint(1, 10)
        })

    return result


def main():
    destination = Path("data/materials.json")
    destination.parent.mkdir(exist_ok=True)
    data = {
        "description": "Синтетические данные о месячных запасах расходных материалов.",
        "generation_seed": SEED,
        "budget": BUDGET,
        "materials": make_materials()
    }
    destination.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Создан файл {destination} ({len(data['materials'])} позиций).")


if __name__ == "__main__":
    main()
