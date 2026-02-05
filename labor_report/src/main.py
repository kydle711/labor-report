import os
import sys
import json
from json import JSONDecodeError

import requests
import traceback

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
api_key_file = ".env"

URL = "https://rest.method.me/api/v1"

report_types = {
    "Lost Time": {
        "customer": "Accurate - Lost Time",
        "item": "labor:"
    },
    "Rental": {
        "customer": "Accurate Rental",
        "item": "labor:"
    },
    "Service Warranty": {
        "customer": "Accurate Service Warranty",
    "item": "labor:"
    },
    "Vehicle Maintenance": {
        "customer": "Accurate Vehicle Maintenance",
        "item": "labor:",
    },
    "All Internals": {
        "customer": (
            "Accurate - Lost Time",
            "Accurate Rental",
            "Accurate Service Warranty",
            "Accurate Vehicle Maintenance",
        ),
        "item": "labor:",
    },
    "Brake cleaner sales": {
        "customer": "",
        "item": "BRAKE CLEANER"
    },
    "Service Calls": {
        "customer": "",
        "item": "Service call:"
    },
    "Parts per labor hour": {
        "customer": "",
        "item": "PPLH"
    },
}

headers = {"Authorization": ""}
payload = {}

console = Console()

def initialize_api_key(key_path) -> str:
    load_dotenv(dotenv_path=key_path)

    api_key = os.getenv("MY_API_KEY")

    if api_key is None:
        api_key = input(
            "Please paste your API key and press enter('q' to exit): "
        )

        if api_key == "q":
            quit()

        with open(".env", "w") as api_file:
            key_variable = f"MY_API_KEY={api_key}"
            api_file.write(key_variable)

    return f"APIkey {api_key}"


def get_technician_names() -> list:
    with Progress() as progress:
        tech_name_task = progress.add_task(
            "Checking technician names...", total=1
        )
        params = {"skip": 0, "top": 100, "select": "FullName"}

        response = requests.get(
            f"{URL}/tables/FieldTechnicians",
            params=params, headers=headers
        )

        data = response.json()
        names_list = [name["FullName"] for name in data["value"]]
        progress.update(tech_name_task, advance=1)

    return names_list


def get_work_order_count(
    start: str, end: str, customer_filter: str | None
) -> int | None:

    params = {
        "apply": f"filter(ActualCompletedDate ge '{start}T00:00:00' and "
        f"ActualCompletedDate lt '{end}T00:00:00'{customer_filter})"
        f"/aggregate($count as TotalWorkOrders)"
    }

    response = requests.get(f"{URL}/tables/Activity",
                            params=params, headers=headers
                            )

    if response.status_code == 200:
        data = response.json()
        total = int(data["value"][0]["TotalWorkOrders"])
        print(
            f"[bold green]Total Work Orders found:[/bold green][bold yellow] {total}[/bold yellow]"
        )

        return total

    else:
        return None

def generate_customer_filter(*customers, exclude) -> str:
    if exclude is False:
        join_param = " or "
        comparator = "eq"
    else:
        join_param = " and "
        comparator = "ne"

    customer_filter_list = [
        f"(EntityCompanyName {comparator} '{customer}' "
        f"or ContactsName {comparator} '{customer}')" for customer in customers
    ]

    customer_filter_string = join_param.join(customer_filter_list)
    customer_filter_string = f" and {customer_filter_string}"

    return customer_filter_string


def get_work_orders_by_range(start: str, end: str, customer_filter: str) -> list:
    work_order_dict_list = []

    params = {
        "skip": 0,
        "top": 100,
        "select": "RecordID",
        "filter": f"ActualCompletedDate ge '{start}T00:00:00' "
        f"and ActualCompletedDate lt '{end}T00:00:00'{customer_filter}",
    }

    total_work_orders = get_work_order_count(start, end, customer_filter)

    with Progress() as progress:
        task = progress.add_task(
            "Getting work order numbers...", total=total_work_orders
        )

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
    """Break large work order list into bite-sized chunks to pass as
    filter params"""
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

def get_items_per_work_order(work_order_num: int) -> list[dict]:
        params = {
            "skip": 0,
            "top": 100,
            "select": "Item, Qty, Amount",
            "filter": f"ActivityNo eq '{work_order_num}'"
        }

        response = requests.get(
            f"{URL}/tables/ActivityJobItems",
            params=params, headers=headers
        )

        data = response.json()
        if "value" in data:
            data = data["value"]

        return data


def get_job_items(work_order_num_list, item_filter) -> list[dict]:
    data_list = []
    param_list = parameterize_wo_list(work_order_num_list)

    with Progress() as progress:
        task = progress.add_task("Getting work order items...", total=len(param_list))

        for work_order_parameter in param_list:
            progress.update(task, advance=1)

            params = {
                "skip": 0,
                "top": 100,
                "select": "Item, Qty",
                "filter": f"contains(Item, '{item_filter}') and {work_order_parameter}",
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


def get_all_job_items(work_order_num_list, item_filter: str | None = None) -> list:
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

def divide_item_amounts_per_tech(items: list, tech_names: list) -> dict:
    total_amount = 0

    #track total labor hours per tech
    labor_dict = {name: 0 for name in tech_names}
    tag = "labor:"

    for item in items:
        item_name = item["Item"]

        if not item_name: continue

        # If 'labor' in item name, extract tech name, then add tech and hrs to dict
        if tag in item_name:
            tech_name = item_name.lstrip(tag)
            if tech_name in labor_dict:
                labor_dict[tech_name] += item["Qty"]

        # If not a labor item or service call fee, add amount to total for WO
        elif "Service Call" not in item_name:
            total_amount += item["Amount"]

    total_hours = sum(labor_dict.values())

    proportion_dict = {name: 0 for name in labor_dict.keys()}

    for name in proportion_dict.keys():
        if proportion_dict[name] > 0 and total_hours > 0:
            # Divide each tech's hours by total hours for a percentage
            proportion_dict[name] = labor_dict[name] / total_hours

    pplh_per_wo_dict = {
        name: total_amount * proportion_dict[name] for name in proportion_dict.keys()
    }

    return pplh_per_wo_dict


def calculate_parts_per_labor_hour(
        work_orders: list, tech_names: list
) -> dict:
    pplh_dict = {name: 0 for name in tech_names}

    with Progress() as progress:
        task = progress.add_task(
            "Calculating parts per labor hour...", total=len(work_orders))

        for work_order in work_orders:
            try:
                # Get all job items from a single WO
                job_items = get_items_per_work_order(work_order)
                pplh_per_work_order_dict = divide_item_amounts_per_tech(job_items, tech_names)

                for tech in pplh_per_work_order_dict.keys():

                    if pplh_dict[tech] == 0: first_value = True

                    pplh_dict[tech] += pplh_per_work_order_dict[tech]
                    if not first_value:
                        pplh_dict[tech] /= 2
            except Exception:
                print(traceback.format_exc())

            progress.update(task, advance=1)

    return pplh_dict



def tally_labor_items(items: list, labor_filter: str, tech_names: list) -> dict:
    labor_dict = {name: 0 for name in tech_names}
    with Progress() as progress:
        task = progress.add_task(f"Counting {labor_filter}...", total=len(items))

        for job_item in items:
            progress.update(task, advance=1)

            try:
                item_name = job_item["Item"]

                if item_name and labor_filter in item_name:
                    tech_name_key = item_name.lstrip(labor_filter)

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
            
            return report_key

        except ValueError:
            print("[red bold]Please enter a number![/]\n\n")

        except IndexError:
            print("[red bold]Invalid index! Try again.[/]\n\n")


def resolve_report_type(key: str, reports_dict: dict) -> tuple[str, str, bool, bool]:
    exclude_flag = False
    parts_per_labor_hour_flag = False
    report_type = reports_dict[key]

    if key == "All Internals":
        exclude_flag = True

    if key == "Parts per labor hour":
        parts_per_labor_hour_flag = True

    return (report_type["customer"],
            report_type["item"],
            exclude_flag,
            parts_per_labor_hour_flag)


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
    
    # Get user input for report type
    report_title = get_report_type(report_types)

    customers, item, exclude_flag, PPLH_flag = resolve_report_type(
        key=report_title, reports_dict=report_types
    )

    customer_filter = generate_customer_filter(customers, exclude=exclude_flag)

    work_orders = get_work_orders_by_range(start_date, end_date, customer_filter)

    if PPLH_flag:
        report_dict = calculate_parts_per_labor_hour(work_orders, field_tech_list)
    elif item == 'BRAKE CLEANER':
        pass
    else:
        job_items = get_job_items(work_orders, item)
        report_dict = tally_labor_items(job_items, item, field_tech_list)

    report_name = create_report_name(start_date, end_date, report_title)
    write_report_to_file(report_dict, report_name)


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
    headers["Authorization"] = initialize_api_key(api_key_file)

    if not os.path.exists("data/"):
        os.makedirs("data/")

    print("Welcome to Labor Report Downloader\n")

    while True:
        main_menu()
