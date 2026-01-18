import math

import matplotlib.pyplot as plt
import numpy as np


def calculate_mean(data_set: dict) -> float:
    return (sum(data_set.values()))/len(data_set)

def calculate_stand_dev(data_set: dict, mean: float | None=None) -> float:
    if not mean:
        mean = calculate_mean(data_set)
    total = 0
    for value in data_set.values():
        total += (value -+ mean) ** 2
    average_of_total = total / len(data_set)
    return math.sqrt(average_of_total)

def plot_hours_by_tech(data_set: dict) -> plt.Figure:
    width = 0.25
    multiplier = 0
    x = np.arange(len(data_set))
    fix, ax = plt.subplots(layout="constrained")

    for name, hrs in data_set.items():
        offset = width * multiplier
        rects = ax.bar(offset, hrs, width, label=name)
        ax.bar_label(rects, padding=2)
        multiplier += 1

    ax.set_ylabel("Hours")
    ax.set_title("Lost Time hours per Technician")
    ax.set_xticks(x + width, data_set.keys())
    ax.set_ylim(0, 1200)

    plt.show()

if __name__ == '__main__':
    plot_hours_by_tech()
