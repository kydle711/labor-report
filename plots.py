import math

import matplotlib.pyplot as plt
import numpy as np


def _calculate_mean(data_set: dict, ignore_zero=True) -> float:
    sum = 0
    divisor = 0
    for value in data_set.values():
        if value > 0:
            sum += value
            divisor += 1
    if divisor == 0:
        return 0
    else:
        return sum / divisor


def calculate_stand_dev(data_set: dict, mean: float | None = None) -> float:
    if mean is None:
        mean = _calculate_mean(data_set)
    total = 0
    for value in data_set.values():
        total += (value - +mean) ** 2
    average_of_total = total / len(data_set)
    return math.sqrt(average_of_total)


def plot_report_data(
    *data_sets: dict, data_labels: list, data_type="Hours", title=""
) -> None:
    width = 0.75
    num_sets = len(data_sets)
    categories = list(data_sets[0].keys())
    bar_spacing = 2
    x = np.arange(len(categories)) * (1 + bar_spacing)
    fix, ax = plt.subplots(layout="constrained")

    for i, data_set in enumerate(data_sets):
        mean = _calculate_mean(data_set)
        hrs = list(data_set.values())
        offset = (i - (num_sets - 1) / 2) * width
        rects = ax.bar(x + offset, hrs, width, label=data_labels[i])
        bar_color = rects.patches[0].get_facecolor()
        ax.axhline(
            mean, color=bar_color, linestyle="--", linewidth=1, label=f"Avg: {mean:.2f}"
        )
        ax.bar_label(rects, padding=3)
        ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.10), ncol=2, frameon=False)

    ax.set_xticks(x, categories, rotation=70)

    ax.set_ylabel(data_type)
    ax.set_title("Lost Time hours per Technician")
    plt.show()
