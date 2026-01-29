import os
import json
from json import JSONDecodeError

import requests
import traceback

from time import sleep
from datetime import date
from calendar import prmonth
from dotenv import load_dotenv
from pathlib import Path

from rich.progress import Progress
from rich.console import Console
from rich.table import Table
from rich import print_json, print

from plots import plot_report_data

REPORT_FILE_PATH = os.path.join("data", "reports.json")

URL = "https://rest.method.me/api/v1"

load_dotenv(dotenv_path=".env")

API_KEY = os.getenv("MY_API_KEY")

if not API_KEY:
    raise RuntimeError("API key could not be found")

report_types = {
    "Lost Time": "Accurate - Lost Time",
    "Rental": "Accurate Rental",
    "Service Warranty": "Accurate Service Warranty",
    "Vehicle Maintenance": "Accurate Vehicle Maintenance",
    "All Internals": None,
    "Brake cleaner sales": "Brake cleaner",
    "Service Calls": "Service calls",
    "Parts per labor hour": "PPLH"
}

headers = {"Authorization": f"APIKey {API_KEY}"}
payload = {}

console = Console()

def get_technician_names() -> list:
    with Progress() as progress:
        tech_name_task = progress.add_task("Checking technician names...", total=None)
        params = {"skip": 0, "top": 100, "select": "FullName"}

        response = requests.get(
            f"{URL}/tables/FieldTechnicians", params=params, headers=headers
        )

        data = response.json()
        names_list = [name["FullName"] for name in data["value"]]
        progress.update(tech_name_task, advance=1)

    return names_list


def get_work_order_count(start: str, end: str, customer_filter: str | None) -> int | None:
    if customer_filter:
        customer_filter_string = (
            f" and (EntityCompanyName eq '{customer_filter}' "
            f"or ContactsName eq '{customer_filter}')"
        )

    else:
        customer_filter_string = ""

    params = {
        "apply": f"filter(ActualCompletedDate ge '{start}T00:00:00' and "
                 f"ActualCompletedDate lt '{end}T00:00:00'{customer_filter_string})"
                 f"/aggregate($count as TotalWorkOrders)"
    }

    response = requests.get(f"{URL}/tables/Activity", params=params, headers=headers)

    if response.status_code == 200:
        data = response.json()
        total = int(data["value"][0]["TotalWorkOrders"])
        print(f"[bold green]Total Work Orders found:[/bold green][bold yellow] {total}[/bold yellow]")

        return total

    else:
        return None


def get_work_orders_by_range(start: str, end: str, customer_filter: str) -> list:
    work_order_dict_list = []
    if customer_filter is not None:
        customer_filter_string = (
            f" and (EntityCompanyName eq '{customer_filter}' "
            f"or ContactsName eq '{customer_filter}')"
        )

    else:
        customer_filter_string = ""


    params = {
        "skip": 0,
        "top": 100,
        "select": "RecordID",
        "filter": f"ActualCompletedDate ge '{start}T00:00:00' "
        f"and ActualCompletedDate lt '{end}T00:00:00'{customer_filter_string}",
    }

    total_work_orders = get_work_order_count(start, end, customer_filter)

    with Progress() as progress:
        task = progress.add_task("Getting work order numbers...", total=total_work_orders)

        while True:
            progress.update(task, advance=100)
            try:
                response = requests.get(
                    f"{URL}/tables/Activity", params=params, headers=headers
                )

                if response.status_code != 200:
                    print(response.status_code)
                    print(response.content)
                    continue

                data = response.json()
                work_order_dict_list.extend(data["value"])

                if data["count"] < 100:
                    break

                params["skip"] += 100

            except Exception:
                print(traceback.format_exc())

    work_order_list = [item["RecordID"] for item in work_order_dict_list]

    return work_order_list


def parameterize_wo_list(wo_list: list) -> list:
    """Break large work order list into bite-sized chunks to pass as filter params"""
    filter_list = []

    for num in wo_list:
        filter_list.append(f"ActivityNo eq '{num}'")

    total = len(wo_list)
    slice_size = 10
    split_list = [filter_list[i : i + slice_size] for i in range(0, total, slice_size)]
    param_list = []

    for item in split_list:
        param_list.append(" or ".join(item))

    return param_list


def get_labor_items(work_order_num_list) -> list:
    data_list = []
    param_list = parameterize_wo_list(work_order_num_list)

    with Progress() as progress:
        task = progress.add_task("Getting labor items...", total=len(param_list))

        for parameter in param_list:
            progress.update(task, advance=1)

            params = {
                "skip": 0,
                "top": 100,
                "select": "Item, Qty",
                "filter": f"contains(Item,'labor') and {parameter}",
            }

            try:
                while True:
                    response = requests.get(
                        f"{URL}/tables/ActivityJobItems", params=params, headers=headers
                    )

                    if response.status_code != 200:
                        print(response.status_code)
                        print(response.content)
                        continue

                    data = response.json()

                    if "value" in data:
                        data_list.extend(data["value"])

                        if data["count"] < 100:
                            break

                        params["skip"] += 100

                    else:
                        data_list.extend(data)
                        break

            except Exception:
                print(traceback.format_exc())

    return data_list


def get_all_job_items(work_order_num_list, item_filter: str | None=None) -> list:
    data_list = []
    param_list = parameterize_wo_list(work_order_num_list)

    for parameter in param_list:
        if item_filter:
            item_filter = f" and contains(Item,'{item_filter}')"
            parameter = parameter + item_filter

        params = {
            "skip": 0,
            "top": 100,
            "select": "ActivityNo, Item, Qty, Amount",
            "filter": parameter,
        }

        try:
            while True:
                response = requests.get(
                    f"{URL}/tables/ActivityJobItems", params=params, headers=headers
                )

                if response.status_code != 200:
                    print(response.status_code)
                    print(response.content)
                    continue

                data = response.json()

                if "value" in data:
                    data_list.extend(data["value"])

                    if data["count"] < 100:
                        break

                    params["skip"] += 100

                else:
                    data_list.extend(data)
                    break

        except Exception:
            print(traceback.format_exc())

    return data_list


def calulate_pplh(wo_nums: list, job_items: list, tech_names: list) -> dict:
    pass


def tally_job_tems(items: list, tech_names: list) -> dict:
    labor_dict = {name: 0 for name in tech_names}
    with Progress() as progress:
        task = progress.add_task("Counting hours...", total=len(items))

        for job_item in items:
            progress.update(task, advance=1)

            try:
                item_name = job_item["Item"]

                if item_name and "labor" in item_name:
                    tech_name_key = item_name.lstrip("labor:")

                    if tech_name_key in tech_names:
                        labor_dict[tech_name_key] += job_item["Qty"]

            except TypeError:
                print(traceback.format_exc())
                print(job_item)

    return labor_dict


def get_date(date_type: str) -> str | None:
    while True:
        year = input(f"Please enter the {date_type} year: ")
        month = input(f"Please enter the {date_type} month: ")

        try:
            year_int, month_int = int(year), int(month)
            prmonth(year_int, month_int)
            day = input(f"Please enter the {date_type} day: ")

        except ValueError:
            print("[red bold]Invalid entry! Try again![/]")
            continue

        try:
            day_int = int(day)
            date_input = date(year_int, month_int, day_int).isoformat()

            return date_input

        except ValueError:
            print("[red bold]Invalid entry! Try again![/]")
            continue


def get_report_type(types: dict) -> str:
    while True:
        table = Table(title="Report Types")
        table.add_column("Index")
        table.add_column("Type")

        for index, key in enumerate(types.keys()):
            table.add_row(str(index), key)

        console.print(table)

        try:
            selected_index = int(input("Please select report number: "))
            report_key = list(types.keys())[selected_index]

            return types[report_key]

        except ValueError:
            print("[red bold]Please enter a number![/]\n\n")

        except IndexError:
            print("[red bold]Invalid index! Try again.[/]\n\n")


def write_report_to_file(
    new_data: dict, data_name: str, report_file=REPORT_FILE_PATH
) -> None:

    path = Path(report_file)

    if path.exists():
        try:
            with open(report_file, "r") as f:
                json_data = json.load(f)
                json_data[data_name] = new_data

        except JSONDecodeError:
            json_data = {}

    else:
        json_data = {}

    json_data[data_name] = new_data

    with open(report_file, "w") as f:
        json.dump(json_data, f, indent=4)


def create_report_name(start: str, end: str, report_type: str) -> str:
    return f"{start}:{end}::{report_type}"


def get_report() -> None:
    start_date = get_date("start")
    end_date = get_date("end")
    field_tech_list = get_technician_names()
    report_request_type = get_report_type(report_types)

    work_orders = get_work_orders_by_range(start_date, end_date, report_request_type)

    job_items = get_labor_items(work_orders)
    labor_hours_dict = tally_job_tems(job_items, field_tech_list)

    report_name = create_report_name(start_date, end_date, report_request_type)
    write_report_to_file(labor_hours_dict, report_name)


def get_stored_data(report_file=REPORT_FILE_PATH) -> tuple[dict, dict]:
    print("Displaying reports...")
    with open(report_file, "r") as f:
        data = json.load(f)
    return data, {index: item for index, item in (enumerate(data.keys()))}


def get_user_selection(selection_menu: dict) -> int | None:
    table = Table(title="Stored Reports")
    table.add_column("Index")
    table.add_column("Start Date")
    table.add_column("End Date")
    table.add_column("Report Type")

    for key, value in selection_menu.items():
        index = str(key)
        title = value

        date_range, report_type = title.split("::")
        start_date, end_date = date_range.split(":")

        table.add_row(index, start_date, end_date, report_type)

    console.print(table)

    try:
        report_selection = int(input("Enter a report number: "))

    except ValueError:
        print("[bold red]Invalid input![/]\n")
        return None

    except IndexError:
        print("[bold red]Invalid selection![/]\n")
        return None

    return report_selection


def list_report() -> None:
    data, selection_dict = get_stored_data()

    print("Which report would you like to print?\n")

    selection = get_user_selection(selection_dict)

    if selection in selection_dict.keys():
        print_json(data=data[selection_dict[selection]])

    else:
        print("[red bold]Invalid selection![/]\n")


def delete_report(report_file=REPORT_FILE_PATH) -> None:
    data, selection_dict = get_stored_data()

    print("Which report would you like to delete?\n")

    selection = get_user_selection(selection_dict)

    if selection in selection_dict.keys():
        data.pop(selection_dict[selection])

        print("[red bold]Deleting the following report:[/]")
        print(f"[red]{selection_dict[selection]}[/]")

        with open(report_file, "w") as f:
            json.dump(data, f, indent=4)

    else:
        print("[red bold]Invalid selection![/]\n")


def plot_data() -> None:
    plots_list = []
    labels = []

    while True:
        data, selection_dict = get_stored_data()
        print("Which report would you like to plot?\n")
        selection = get_user_selection(selection_dict)

        if selection in selection_dict.keys():

            labels.append(selection_dict[selection])
            report_to_plot = data[selection_dict[selection]]

            print("[green bold]Adding to list: [/]")
            print_json(data=report_to_plot)
            plots_list.append(report_to_plot)

        if input("Do you want to add another report? (y/n): ") != "y":
            break

    print("\nPlotting data...\n\n")
    plot_report_data(*plots_list, data_labels=labels)


def quit_program() -> None:
    quit()


def main_menu() -> None:
    menu_items = {
        0: "Get Report",
        1: "List Report",
        2: "Delete Report",
        3: "Plot Data",
        4: "Quit Program",
    }
    selection_functions = {
        0: get_report,
        1: list_report,
        2: delete_report,
        3: plot_data,
        4: quit_program,
    }

    table = Table(title="MAIN MENU")
    table.add_column("Index")
    table.add_column("Options")

    for key, value in menu_items.items():
        table.add_row(str(key), value)

    console.print(table)

    try:
        menu_selection = int(input("Please select an option: "))

    except ValueError:
        print("[bold red]Invalid input![/]")
        return

    if menu_selection in selection_functions.keys():
        selection_functions[menu_selection]()

    else:
        print("[bold red]Invalid selection![/]")
        return



if __name__ == "__main__":

    if not os.path.exists("data/"):
        os.makedirs("data/")

    print("Welcome to Labor Report Downloader\n")

    while True:
        main_menu()
