"""Генетический алгоритм для плана закупки расходных материалов.

Хромосома -- список целых чисел. Число на позиции i означает,
сколько единиц i-го материала надо купить в этом месяце.
"""

import argparse
import copy
import json
import random
from pathlib import Path


def load_data(filename="data/materials.json"):
    """Читает входные данные и дописывает для каждой позиции границы заказа."""
    data = json.loads(Path(filename).read_text(encoding="utf-8"))
    for material in data["materials"]:
        material["min_order"] = max(0, material["minimum_stock"] - material["current_stock"])
        material["max_order"] = max(0, material["maximum_stock"] - material["current_stock"])
    return data


def quality_of_stock(material, ordered):
    """Возвращает пользу от запаса после покупки.

    До желаемого уровня каждая единица ценнее, чем запас сверх него.
    Это заставляет алгоритм сначала закрывать важные месячные потребности.
    """
    final_stock = material["current_stock"] + ordered
    minimum = material["minimum_stock"]
    desired = material["desired_stock"]
    priority = material["priority"]

    below_minimum = min(final_stock, minimum)
    useful_reserve = max(0, min(final_stock, desired) - minimum)
    extra_reserve = max(0, final_stock - desired)
    return priority * (5 * below_minimum + 10 * useful_reserve + extra_reserve)


def evaluate(chromosome, data, config, strategy):
    """Считает стоимость, полезность и нарушения ограничений особи."""
    total_cost = 0
    score = 0
    missing_units = 0
    materials = data["materials"]

    for ordered, material in zip(chromosome, materials):
        total_cost += ordered * material["unit_price"]
        score += quality_of_stock(material, ordered)
        missing_units += max(0, material["min_order"] - ordered)

    over_budget = max(0, total_cost - data["budget"])
    feasible = missing_units == 0 and over_budget == 0
    fitness = score
    if strategy == "penalty":
        fitness -= config["penalty_per_ruble"] * over_budget
        fitness -= config["penalty_per_missing_unit"] * missing_units

    return {
        "chromosome": chromosome,
        "score": score,
        "cost": total_cost,
        "missing_units": missing_units,
        "over_budget": over_budget,
        "feasible": feasible,
        "fitness": fitness
    }


def repair(chromosome, data):
    """Восстанавливает допустимость: границы, минимум запаса и бюджет."""
    materials = data["materials"]
    fixed = []
    for value, material in zip(chromosome, materials):
        value = int(round(value))
        value = max(material["min_order"], value)
        value = min(material["max_order"], value)
        fixed.append(value)

    minimum_cost = sum(m["min_order"] * m["unit_price"] for m in materials)
    if minimum_cost > data["budget"]:
        raise ValueError("Бюджета недостаточно даже для минимальных запасов.")

    # Убираем наименее полезные дополнительные единицы, пока план не войдёт в бюджет.
    while sum(x * m["unit_price"] for x, m in zip(fixed, materials)) > data["budget"]:
        candidates = []
        for index, material in enumerate(materials):
            if fixed[index] > material["min_order"]:
                loss = quality_of_stock(material, fixed[index]) - quality_of_stock(material, fixed[index] - 1)
                candidates.append((loss / material["unit_price"], index))
        if not candidates:
            break
        _, index = min(candidates)
        fixed[index] -= 1

    return fixed


def random_chromosome(data, rng, with_repair):
    """Создаёт случайную особь; для ремонта сразу делает её допустимой."""
    chromosome = []
    for material in data["materials"]:
        lower = material["min_order"] if with_repair else 0
        chromosome.append(rng.randint(lower, material["max_order"]))
    return repair(chromosome, data) if with_repair else chromosome


def random_feasible_chromosome(data, rng):
    """Простая случайная допустимая точка для базового сравнения."""
    chromosome = [m["min_order"] for m in data["materials"]]
    remaining_money = data["budget"] - sum(
        x * m["unit_price"] for x, m in zip(chromosome, data["materials"])
    )

    while True:
        possible = [
            i for i, m in enumerate(data["materials"])
            if chromosome[i] < m["max_order"] and m["unit_price"] <= remaining_money
        ]
        if not possible or rng.random() < 0.12:
            break
        index = rng.choice(possible)
        chromosome[index] += 1
        remaining_money -= data["materials"][index]["unit_price"]
    return chromosome


def tournament(population, rng, size):
    """Выбирает лучшего из нескольких случайных участников турнира."""
    participants = rng.sample(population, size)
    return max(participants, key=lambda item: item["fitness"])


def crossover(first, second, rng):
    """Равномерный кроссовер для вектора количеств."""
    return [a if rng.random() < 0.5 else b for a, b in zip(first, second)]


def redistribute_mutation(chromosome, data, rng, keep_minimum):
    """Переносит несколько единиц с одной позиции на другую.

    Это предметная мутация: меняется именно распределение закупки между
    материалами, а не все числа одновременно.
    """
    result = chromosome[:]
    materials = data["materials"]
    lower_bounds = [m["min_order"] if keep_minimum else 0 for m in materials]
    donors = [i for i in range(len(result)) if result[i] > lower_bounds[i]]
    receivers = [i for i in range(len(result)) if result[i] < materials[i]["max_order"]]
    if not donors or not receivers:
        return result

    donor = rng.choice(donors)
    receivers = [i for i in receivers if i != donor]
    if not receivers:
        return result
    receiver = rng.choice(receivers)
    amount = rng.randint(1, min(3, result[donor] - lower_bounds[donor]))
    result[donor] -= amount
    result[receiver] = min(materials[receiver]["max_order"], result[receiver] + amount)
    return result


def reset_mutation(chromosome, data, rng, keep_minimum):
    """Случайно задаёт новое количество только для одной позиции."""
    result = chromosome[:]
    index = rng.randrange(len(result))
    material = data["materials"][index]
    lower = material["min_order"] if keep_minimum else 0
    result[index] = rng.randint(lower, material["max_order"])
    return result


def mutate(chromosome, data, rng, mutation_name, keep_minimum):
    if mutation_name == "redistribute":
        return redistribute_mutation(chromosome, data, rng, keep_minimum)
    return reset_mutation(chromosome, data, rng, keep_minimum)


def make_child(parent1, parent2, data, config, rng, strategy, mutation_name):
    """Получает потомка от двух родителей и при необходимости ремонтирует его."""
    genes1 = parent1["chromosome"]
    genes2 = parent2["chromosome"]
    if rng.random() < config["crossover_probability"]:
        child = crossover(genes1, genes2, rng)
    else:
        child = genes1[:]

    if rng.random() < config["mutation_probability"]:
        child = mutate(child, data, rng, mutation_name, strategy == "repair")
    if strategy == "repair":
        child = repair(child, data)
    return child


def best_feasible(population):
    valid = [item for item in population if item["feasible"]]
    return max(valid, key=lambda item: item["score"]) if valid else None


def run_ga(data, config, seed, strategy="repair", mutation_name="redistribute"):
    """Выполняет один запуск ГА и возвращает лучший допустимый план."""
    rng = random.Random(seed)
    population = []
    # При штрафах одна допустимая точка нужна как ориентир для отбора.
    # Остальная популяция остаётся обычной случайной и может быть недопустимой.
    if strategy == "penalty":
        initial = random_feasible_chromosome(data, rng)
        population.append(evaluate(initial, data, config, strategy))
    while len(population) < config["population_size"]:
        chromosome = random_chromosome(data, rng, strategy == "repair")
        population.append(evaluate(chromosome, data, config, strategy))
    evaluations = len(population)
    best = best_feasible(population)
    history = [best["score"] if best else 0]

    for _ in range(config["generations"]):
        population.sort(key=lambda item: item["fitness"], reverse=True)
        next_population = [copy.deepcopy(item) for item in population[:config["elite_count"]]]

        while len(next_population) < config["population_size"]:
            parent1 = tournament(population, rng, config["tournament_size"])
            parent2 = tournament(population, rng, config["tournament_size"])
            child = make_child(parent1, parent2, data, config, rng, strategy, mutation_name)
            next_population.append(evaluate(child, data, config, strategy))

        population = next_population
        evaluations += config["population_size"] - config["elite_count"]
        current = best_feasible(population)
        if current and (best is None or current["score"] > best["score"]):
            best = copy.deepcopy(current)
        history.append(best["score"] if best else 0)

    return {
        "best": best,
        "history": history,
        "evaluations": evaluations,
        "final_feasible_share": sum(x["feasible"] for x in population) / len(population)
    }


def plan_rows(chromosome, data):
    """Преобразует хромосому в понятную таблицу плана закупки."""
    rows = []
    for ordered, material in zip(chromosome, data["materials"]):
        rows.append({
            "name": material["name"],
            "unit": material["unit"],
            "current_stock": material["current_stock"],
            "minimum_stock": material["minimum_stock"],
            "desired_stock": material["desired_stock"],
            "maximum_stock": material["maximum_stock"],
            "ordered": ordered,
            "final_stock": material["current_stock"] + ordered,
            "unit_price": material["unit_price"],
            "position_cost": ordered * material["unit_price"],
            "priority": material["priority"]
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Один запуск ГА для плана закупки")
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--strategy", choices=["repair", "penalty"], default="repair")
    parser.add_argument("--mutation", choices=["redistribute", "reset"], default="redistribute")
    args = parser.parse_args()

    data = load_data()
    config = json.loads(Path("config.json").read_text(encoding="utf-8"))
    result = run_ga(data, config, args.seed, args.strategy, args.mutation)
    best = result["best"]
    print(f"Лучший балл: {best['score']}")
    print(f"Стоимость: {best['cost']} / {data['budget']} руб.")
    print(f"Вычислений функции: {result['evaluations']}")
    print("План заказа:")
    for row in plan_rows(best["chromosome"], data):
        print(f"  {row['name']}: {row['ordered']} {row['unit']} ({row['position_cost']} руб.)")


if __name__ == "__main__":
    main()
