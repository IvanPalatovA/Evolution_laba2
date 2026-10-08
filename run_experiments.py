"""Проводит серию запусков и сохраняет результаты лабораторной работы."""

import csv
import json
import random
import statistics
from html import escape
from pathlib import Path

from ga_procurement import (
    evaluate,
    load_data,
    random_feasible_chromosome,
    run_ga,
    plan_rows,
)


SCENARIOS = [
    ("repair_redistribute", "Ремонт + перераспределение", "repair", "redistribute"),
    ("penalty_redistribute", "Штрафы + перераспределение", "penalty", "redistribute"),
    ("repair_reset", "Ремонт + сброс одной позиции", "repair", "reset"),
    ("random_search", "Случайный допустимый поиск", None, None),
]


def random_search(data, config, seed, evaluations):
    """Базовый метод: много раз создаёт случайный допустимый план."""
    rng = random.Random(seed)
    best = None
    history = []
    made = 0
    batches = [config["population_size"]] + [
        config["population_size"] - config["elite_count"]
    ] * config["generations"]

    for batch_size in batches:
        for _ in range(batch_size):
            if made >= evaluations:
                break
            chromosome = random_feasible_chromosome(data, rng)
            candidate = evaluate(chromosome, data, config, "repair")
            if best is None or candidate["score"] > best["score"]:
                best = candidate
            made += 1
        history.append(best["score"])

    return {
        "best": best,
        "history": history,
        "evaluations": made,
        "final_feasible_share": 1.0,
    }


def write_csv(filename, rows, fieldnames):
    with filename.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_svg(filename, histories, labels):
    """Строит простой SVG-график средней лучшей оценки без matplotlib."""
    width, height = 960, 520
    left, right, top, bottom = 75, 30, 35, 70
    values = [value for history in histories.values() for value in history]
    minimum, maximum = min(values), max(values)
    if minimum == maximum:
        maximum += 1

    colors = ["#2166ac", "#b2182b", "#4d9221", "#7b3294"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text { font-family: Arial, sans-serif; font-size: 13px; } .axis { stroke: #333; stroke-width: 1; } .grid { stroke: #ddd; stroke-width: 1; }</style>',
        f'<text x="{width / 2}" y="22" text-anchor="middle">Средняя лучшая оценка по 20 запускам</text>',
        f'<line class="axis" x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}"/>',
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}"/>'
    ]

    for step in range(6):
        value = minimum + (maximum - minimum) * step / 5
        y = height - bottom - (height - top - bottom) * step / 5
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end">{value:.0f}</text>')

    first_history = next(iter(histories.values()))
    last_generation = len(first_history) - 1
    for step in range(5):
        generation = round(last_generation * step / 4)
        x = left + (width - left - right) * step / 4
        parts.append(f'<text x="{x:.1f}" y="{height - bottom + 22}" text-anchor="middle">{generation}</text>')

    for color, (key, history) in zip(colors, histories.items()):
        points = []
        for index, value in enumerate(history):
            x = left + (width - left - right) * index / max(1, len(history) - 1)
            y = height - bottom - (value - minimum) * (height - top - bottom) / (maximum - minimum)
            points.append(f"{x:.1f},{y:.1f}")
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(points)}"/>')

    for index, (key, label) in enumerate(labels.items()):
        x = left + index * 215
        y = height - 25
        parts.append(f'<line x1="{x}" y1="{y - 4}" x2="{x + 22}" y2="{y - 4}" stroke="{colors[index]}" stroke-width="3"/>')
        parts.append(f'<text x="{x + 28}" y="{y}">{escape(label)}</text>')

    parts.append(f'<text x="{width / 2}" y="{height - 44}" text-anchor="middle">Поколение</text>')
    parts.append(f'<text x="17" y="{height / 2}" transform="rotate(-90 17 {height / 2})" text-anchor="middle">Балл качества запаса</text>')
    parts.append("</svg>")
    filename.write_text("\n".join(parts), encoding="utf-8")


def make_examples(data, config, best):
    """Готовит два допустимых и два недопустимых примера для отчёта."""
    minimum_plan = [m["min_order"] for m in data["materials"]]
    random_plan = random_feasible_chromosome(data, random.Random(77))
    too_little = minimum_plan[:]
    too_little[0] -= 1
    too_expensive = [m["max_order"] for m in data["materials"]]

    examples = [
        ("Минимальный допустимый", minimum_plan),
        ("Допустимый случайный", random_plan),
        ("Недопустимый: не хватает бумаги A4", too_little),
        ("Недопустимый: превышен бюджет", too_expensive),
    ]
    rows = []
    for name, chromosome in examples:
        result = evaluate(chromosome, data, config, "repair")
        rows.append({
            "example": name,
            "cost": result["cost"],
            "budget_overrun": result["over_budget"],
            "missing_units": result["missing_units"],
            "feasible": "да" if result["feasible"] else "нет",
            "chromosome": ";".join(map(str, chromosome)),
        })
    return rows


def main():
    data = load_data()
    config = json.loads(Path("config.json").read_text(encoding="utf-8"))
    output = Path("outputs")
    output.mkdir(exist_ok=True)

    results = []
    all_histories = {key: [] for key, _, _, _ in SCENARIOS}
    best_overall = None
    ga_evaluations = config["population_size"] + config["generations"] * (
        config["population_size"] - config["elite_count"]
    )

    for run_number in range(1, config["runs"] + 1):
        seed = config["base_seed"] + run_number - 1
        print(f"Запуск {run_number}/{config['runs']}")
        for key, label, strategy, mutation in SCENARIOS:
            if key == "random_search":
                result = random_search(data, config, seed, ga_evaluations)
            else:
                result = run_ga(data, config, seed, strategy, mutation)

            best = result["best"]
            all_histories[key].append(result["history"])
            results.append({
                "scenario": key,
                "scenario_name": label,
                "run": run_number,
                "seed": seed,
                "best_score": best["score"],
                "best_cost": best["cost"],
                "budget": data["budget"],
                "is_feasible": best["feasible"],
                "fitness_evaluations": result["evaluations"],
                "final_feasible_share": f"{result['final_feasible_share']:.3f}",
            })
            if best_overall is None or best["score"] > best_overall["best"]["score"]:
                best_overall = {"scenario": label, "seed": seed, "best": best}

    write_csv(output / "experiment_results.csv", results, list(results[0].keys()))

    summary = []
    average_histories = {}
    labels = {}
    for key, label, _, _ in SCENARIOS:
        group = [row for row in results if row["scenario"] == key]
        scores = [row["best_score"] for row in group]
        costs = [row["best_cost"] for row in group]
        summary.append({
            "scenario": key,
            "scenario_name": label,
            "best_score": max(scores),
            "mean_score": f"{statistics.mean(scores):.2f}",
            "median_score": f"{statistics.median(scores):.2f}",
            "std_score": f"{statistics.stdev(scores):.2f}",
            "worst_score": min(scores),
            "mean_cost": f"{statistics.mean(costs):.2f}",
            "all_runs_feasible": all(row["is_feasible"] for row in group),
        })
        runs_history = all_histories[key]
        average_histories[key] = [statistics.mean(values) for values in zip(*runs_history)]
        labels[key] = label

    write_csv(output / "summary.csv", summary, list(summary[0].keys()))
    write_svg(output / "convergence.svg", average_histories, labels)

    plan = plan_rows(best_overall["best"]["chromosome"], data)
    for row in plan:
        row["scenario"] = best_overall["scenario"]
        row["seed"] = best_overall["seed"]
    write_csv(output / "best_plan.csv", plan, list(plan[0].keys()))
    examples = make_examples(data, config, best_overall["best"])
    write_csv(output / "solution_examples.csv", examples, list(examples[0].keys()))

    run_information = {
        "data_generation_seed": data["generation_seed"],
        "experiment_config": config,
        "ga_evaluations_per_run": ga_evaluations,
        "random_search_evaluations_per_run": ga_evaluations,
        "best_scenario": best_overall["scenario"],
        "best_seed": best_overall["seed"],
    }
    (output / "run_information.json").write_text(
        json.dumps(run_information, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Готово: результаты находятся в папке outputs.")


if __name__ == "__main__":
    main()
