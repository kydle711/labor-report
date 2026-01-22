import math

import matplotlib.pyplot as plt
import numpy as np


def _calculate_mean(data_set: dict, ignore_zero=True) -> float:
    return (sum(data_set.values())) / len(data_set)


def calculate_stand_dev(data_set: dict, mean: float | None = None) -> float:
    if not mean:
        mean = _calculate_mean(data_set)
    total = 0
    for value in data_set.values():
        total += (value - +mean) ** 2
    average_of_total = total / len(data_set)
    return math.sqrt(average_of_total)


def plot_report_data(*data_sets: dict, data_type="Hours", title="") -> None:
    width = 0.5
    multiplier = 0
    categories = list(data_sets[0].keys())
    x = np.arange(len(categories))
    fix, ax = plt.subplots(layout="constrained")

    for data_set in data_sets:
        hrs = list(data_set.values())
        offset = width * multiplier
        rects = ax.bar(x + offset, hrs, width, label=categories)
        ax.bar_label(rects, padding=3, labels=categories)
        multiplier += 1

    ax.set_ylabel(data_type)
    ax.set_title("Lost Time hours per Technician")
    plt.show()
