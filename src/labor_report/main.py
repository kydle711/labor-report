# TODO:
# Verify functions of all reports
# write tests

import time
import json
import logging
import os
import traceback
import asyncio
from calendar import prmonth
from datetime import date
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from rich import print, print_json
from rich.console import Console
from rich.progress import Progress, track
from rich.table import Table

from labor_report.plots import plot_report_data


def project_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    for p in [here, *here.parents]:
        if (p / "pyproject.toml").exists() or (p / ".git").exists():
            return p
    raise RuntimeError("Could not locate project root (pyproject.toml or .git)")


ROOT = project_root()
REPORTS_PATH = ROOT / "data" / "reports.json"
ENV_PATH = ROOT / ".env"

LOG_FILE_PATH = ROOT / "data" / "info.log"
if not os.path.exists(LOG_FILE_PATH):
    with open(LOG_FILE_PATH, "w") as f:
        pass


FORMAT = "%(asctime)s:%(levelname)s:%(message)s"
logger = logging.getLogger(__name__)
logging.basicConfig(filename=LOG_FILE_PATH, format=FORMAT, level=logging.ERROR)

REPORT_FILE_PATH = os.path.join("data", "reports.json")
api_key_file = ".env"

URL = "https://rest.method.me/api/v1"

report_types = {
    "Lost Time": {
        "customer": ("Accurate - Lost Time",),
        "item": "labor:",
        "ylabel": "Hours",
    },
    "Rental": {"customer": ("Accurate Rental",), "item": "labor:", "ylabel": "Hours"},
    "Service Warranty": {
        "customer": ("Accurate Service Warranty",),
        "item": "labor:",
        "ylabel": "Hours",
    },
    "Vehicle Maintenance": {
        "customer": ("Accurate Vehicle Maintenance",),
        "item": "labor:",
        "ylabel": "Hours",
    },
    "All Internals": {
        "customer": (
            "Accurate - Lost Time",
            "Accurate Rental",
            "Accurate Service Warranty",
            "Accurate Vehicle Maintenance",
        ),
        "item": "labor:",
        "ylabel": "Hours",
    },
    "All Customers": {
        "customer": (
            "Accurate - Lost Time",
            "Accurate Rental",
            "Accurate Service Warranty",
            "Accurate Vehicle Maintenance",
        ),
        "item": "labor:",
        "ylabel": "Hours",
    },
    "Brake cleaner sales": {
        "customer": (),
        "item": "brake cleaner",
        "ylabel": "Units Sold",
    },
    "Service Calls": {
        "customer": (),
        "item": "Service Call:Service Call - ",
        "ylabel": "Service Call Fees",
    },
    "Parts per labor hour": {
        "customer": (),
        "item": "PPLH",
        "ylabel": "($) Per Labor Hour",
    },
}

exclude_list = ["Toro", "Bobby Melton", "Rod Allie"]
headers = {"Authorization": ""}
payload = {}

console = Console()


def _display_sleep_progress():
    for _ in track(
        range(60),
        "API is unhappy with the number of requests 😠 sleeping...",
        transient=True,
    ):
        time.sleep(1)


def initialize_api_key(key_path) -> str:
    load_dotenv(dotenv_path=key_path)

    api_key = os.getenv("METHOD_API_KEY")

    if api_key is None:
        api_key = input("Please paste your API key and press enter('q' to exit): ")

        if api_key == "q":
            raise SystemExit()

        with open(key_path, "w") as api_file:
            key_variable = f"METHOD_API_KEY={api_key}"
            api_file.write(key_variable)

    return f"APIkey {api_key}"


def get_technician_names(exclusions: list) -> list:
    with Progress() as progress:
        progress_bar = progress.add_task("Checking technician names...", total=1)
        params = {"skip": 0, "top": 100, "select": "FullName"}

        response = httpx.get(
            f"{URL}/tables/FieldTechnicians", params=params, headers=headers, timeout=20
        )

        data = response.json()
        names_list = [
            name["FullName"]
            for name in data["value"]
            if name["FullName"] not in exclusions
        ]

        logger.info(
            f"Initialized with the following tech names: {
                [f'\t{name}\n' for name in names_list]
            }"
        )
        progress.update(progress_bar, advance=1)

    return names_list


def get_work_order_count(start: str, end: str, customer_filter: str) -> int:
    params = {
        "apply": f"filter(ActualCompletedDate ge '{start}T00:00:00' and "
        f"ActualCompletedDate lt '{end}T00:00:00'{customer_filter})"
        f"/aggregate($count as TotalWorkOrders)"
    }

    response = httpx.get(
        f"{URL}/tables/Activity", params=params, headers=headers, timeout=20
    )

    if response.status_code == 200:
        data = response.json()
        total = int(data["value"][0]["TotalWorkOrders"])
        print(f"[bold purple]Total Work Orders found:[/][bold orange] {total}[/]")

    else:
        logger.error("Failed request on get_work_order_count... returned '0' for total")
        total = 0

    return total


def generate_customer_filter(customers: tuple, exclude: bool) -> str:
    """method.me API docs for info on parameters"""
    if len(customers) == 0:
        customer_filter_string = ""

    else:
        if exclude is False:
            join_param = " or "
            comparator = "eq"
        else:
            join_param = " and "
            comparator = "ne"

        customer_filter_list = [
            f"(EntityCompanyName {comparator} '{customer}' "
            f"or ContactsName {comparator} '{customer}')"
            for customer in customers
        ]

        customer_filter_string = f" and ({join_param.join(customer_filter_list)})"

    return customer_filter_string


async def fetch_work_orders_by_range(
    client: httpx.AsyncClient, start: str, end: str, customer_filter: str
) -> list:
    work_order_dict_list = []

    params = {
        "skip": 0,
        "top": 100,
        "select": "RecordID",
        "filter": f"ActualCompletedDate ge '{start}T00:00:00' "
        f"and ActualCompletedDate lt '{end}T00:00:00'{customer_filter}",
        "orderby": "RecordID asc",
    }

    total_work_orders = get_work_order_count(start, end, customer_filter)

    with Progress() as progress:
        progress_bar = progress.add_task(
            "Getting work order numbers...", total=total_work_orders
        )

        attempts = 0
        while attempts < 5:
            try:
                response = await client.get(
                    f"{URL}/tables/Activity", params=params, headers=headers, timeout=20
                )

                if response.status_code != 200:
                    if response.status_code == 429:
                        _display_sleep_progress()
                    else:
                        attempts += 1
                        logger.error(
                            f"Failed request! {response.status_code}{response.content}"
                        )
                    continue

                data = response.json()

                work_order_dict_list = add_values(work_order_dict_list, data)
                params, count = paginate_parameters(params, data)

                progress.update(progress_bar, advance=count)

                if count < 100:
                    break

            except Exception:
                attempts += 1
                logger.error(
                    f"Error in get_work_orders_by_range with the"
                    f"following traceback{traceback.format_exc()}\n"
                    f"Response: {response.content}\n"
                    f"Params: {params}"
                )

        progress.update(progress_bar, completed=total_work_orders)

    work_order_list = [item["RecordID"] for item in work_order_dict_list]

    return work_order_list


def sort_items_by_work_order(items: list) -> dict[str, list]:
    """Will return a dict with str<Work Order num> as key
    and a list as the value. The list will contain the dict
    of each item for that work order. Items contain the following
    keys: ActivityNo, Item, ItemDescription, Qty, Amount"""

    wo_items = {}
    for item in items:
        if "ActivityNo" in item and item["ActivityNo"]:
            wo_num = item["ActivityNo"]
            if wo_num in wo_items.keys():
                wo_items[wo_num].append(item)
            else:
                wo_items[wo_num] = [item]

    return wo_items


def paginate_parameters(params: dict, data: dict) -> tuple[dict, int]:
    count = 0
    if "count" in data.keys():
        count = data["count"]
        params["skip"] += count
    return params, count


def add_values(cached_data: list, response_data: Any) -> list:
    if hasattr(response_data, "keys") and "value" in response_data.keys():
        cached_data.extend(response_data["value"])
    else:
        if len(response_data) == 1:
            cached_data.append(response_data)
        else:
            for item in response_data:
                cached_data.append(item)
    return cached_data


def parameterize_wo_list(wo_list: list) -> list:
    """Break large work order list into bite-sized chunks to pass as
    filter params"""
    filter_list = []

    for num in wo_list:
        filter_list.append(f"ActivityNo eq '{num}'")

    total = len(wo_list)
    slice_size = 70
    split_list = [filter_list[i : i + slice_size] for i in range(0, total, slice_size)]
    param_list = []

    for item in split_list:
        param_list.append(" or ".join(item))

    logger.debug(f"Parameterized wo_list: {param_list}")
    return param_list


async def fetch_items(
    client: httpx.AsyncClient,
    work_order_nums: list,
    item_filter: str | None = None,
) -> list[dict]:
    data_list = []
    param_list = parameterize_wo_list(work_order_nums)

    if item_filter:
        filter_string = f"contains(Item, '{item_filter}') and "
    else:
        filter_string = ""

    with Progress() as progress:
        progress_bar = progress.add_task("Fetching job items...", total=len(param_list))

        for work_orders_parameter in param_list:
            params = {
                "skip": 0,
                "top": 100,
                "select": "ActivityNo, Item, ItemDescription, Qty, Amount",
                "filter": f"{filter_string}{work_orders_parameter}",
                "orderby": "ActivityNo asc",
            }

            attempts = 0
            while attempts < 5:
                try:
                    response = await client.get(
                        f"{URL}/tables/ActivityJobItems",
                        params=params,
                        headers=headers,
                        timeout=20,
                    )

                    if response.status_code != 200:
                        if response.status_code == 429:
                            _display_sleep_progress()
                        else:
                            attempts += 1
                            logger.debug(
                                f"Failed request in get_items: {response.status_code}:"
                                f"{response.content}\n"
                                f"Params: {params}"
                            )
                        continue

                    data = response.json()

                    data_list = add_values(data_list, data)
                    params, count = paginate_parameters(params, data)

                    if count < 100:
                        break

                except Exception:
                    attempts += 1
                    logger.error(
                        f"Error get_items: {traceback.format_exc()}\nParams: {params}"
                    )

            progress.update(progress_bar, advance=1)

    if attempts == 5:
        logger.error("Scan incomplete after 5 failed attempts")
    print(f"[bold purple]Total job items:[/] [bold orange] {len(data_list)}[/]")
    return data_list


def _derive_pplh_per_work_order(tech_names: list, items: list[dict]) -> dict:
    """Helps calculate parts per labor hour for techs. Given work order 12345,
    if tech A has 5.0 hrs of labor, and tech B has 10.0 hrs of labor, tech B
    will receive credit for 2/3 of the value of non-labor items, while tech A
    will receive credit for 1/3. The full parts per labor hour is calculated
    in this function, and then the mean of all work hours will be calculated
    in the calling function.

    Each item is a dict containing the following keys:
        ActivityNo, Item, ItemDescription, Qty, Amount"""

    total_amount = 0
    total_hours = 0

    logger.debug(
        f"derive_pplh_per_work_order- ITEMS: {items}\nTECH NAMES: {tech_names}"
    )

    # track total labor hours per tech
    labor_dict = {name: 0 for name in tech_names}
    tag = "labor:"

    for item in items:
        item_name = item["Item"]

        if not item_name:
            continue

        # If 'labor:' in item name, extract tech name, then add
        # tech and hrs to dict
        if tag in item_name:
            total_hours += item["Qty"]
            tech_name = item_name.removeprefix(tag).strip()

            if tech_name in labor_dict:
                labor_dict[tech_name] += item["Qty"]

        # If not a labor item or service call fee, add amount to total for WO
        elif "Service Call" not in item_name:
            total_amount += item["Amount"]

    pplh_per_wo_dict = {name: 0.0 for name in labor_dict.keys()}

    # If total hours and hours for tech name are not 0
    if total_hours:
        for name in tech_names:
            if labor_dict[name]:
                # Divide each tech's hours by total hours for a percentage
                # Then calculate the parts per labor hour for this work order
                proportion = labor_dict[name] / total_hours
                pplh_per_wo_dict[name] = (total_amount * proportion) / labor_dict[name]

    return pplh_per_wo_dict


def calculate_parts_per_labor_hour(tech_names: list, job_items: list[dict]) -> dict:
    pplh_raw_dict = {name: {"total": 0, "divisor": 0} for name in tech_names}
    pplh_dict = {name: 0.0 for name in tech_names}
    sorted_items = sort_items_by_work_order(job_items)

    with Progress() as progress:
        progress_bar = progress.add_task(
            "Calculating parts per labor hour...", total=len(sorted_items)
        )

        for work_order in sorted_items.keys():
            try:
                pplh_per_work_order_dict = _derive_pplh_per_work_order(
                    tech_names, sorted_items[work_order]
                )

                for tech in tech_names:
                    if pplh_per_work_order_dict[tech] > 0:
                        pplh_raw_dict[tech]["total"] += pplh_per_work_order_dict[tech]
                        pplh_raw_dict[tech]["divisor"] += 1

            except Exception:
                logger.error(
                    f"calculate_parts_per_labor_hour error: {traceback.format_exc()}"
                )

            progress.update(progress_bar, advance=1)

    for name in tech_names:
        total = pplh_raw_dict[name]["total"]
        divisor = pplh_raw_dict[name]["divisor"]

        if total > 0 and divisor > 0:
            pplh = round(total / divisor, 2)

        else:
            pplh = 0

        pplh_dict[name] = pplh

    return pplh_dict


def tally_labor_items(tech_names: list, items: list, item_filter: str) -> dict:
    labor_dict = {name: 0 for name in tech_names}
    with Progress() as progress:
        progress_bar = progress.add_task(f"Counting {item_filter}...", total=len(items))
        logger.debug(f"Number of labor items: {len(items)}\n")
        for job_item in items:
            logger.debug(f"{job_item}\n")
            try:
                item_name = job_item["Item"]

                if item_filter in item_name:
                    tech_name_key = item_name.removeprefix(item_filter).strip()
                    logger.debug(f"\tItem: {item_name}\nTech: {tech_name_key}\n")

                    if tech_name_key in tech_names:
                        labor_dict[tech_name_key] += job_item["Qty"]

                        logger.debug(f"Adding: {job_item['Qty']}")

            except TypeError:
                logger.error(
                    f"Error: tally_labor_items: {traceback.format_exc()}\n"
                    f"Job Item: {job_item} -- Labor Filter: {item_filter}"
                )

            progress.update(progress_bar, advance=1)

    return labor_dict


def _divide_brake_cleaners_per_work_order(
    items: list, names: list, item_key: str
) -> dict:
    total = 0

    logger.debug(
        f"divide_brake_cleaners_per_work_order- ITEMS: {items}\nTECH NAMES: {names}\n"
    )

    labor_dict = {name: 0 for name in names}
    tag = "labor:"
    total_hours = 0

    for item in items:
        item_name = item["Item"]

        if not item_name:
            continue

        if tag in item_name:
            total_hours += item["Qty"]
            tech_name = item_name.removeprefix(tag).strip()

            if tech_name in labor_dict:
                labor_dict[tech_name] += item["Qty"]

        elif item_key == item["ItemDescription"].lower():
            total += item["Qty"]

    brake_cleaner_dict = {name: 0.0 for name in names}

    if total > 0:
        for name in labor_dict.keys():
            if labor_dict[name] > 0:
                brake_cleaner_dict[name] = total * (labor_dict[name] / total_hours)

    return brake_cleaner_dict


def count_brake_cleaners(
    tech_names: list, job_items: list[dict], item_key: str
) -> dict:
    """See calculate_parts_per_labor_hour docstring for more info on how this
    func calculates brake cleaners per tech. It follows a similar format
    except for calculating the mean per labor hour."""

    brake_cleaner_dict = {name: 0 for name in tech_names}
    sorted_list = sort_items_by_work_order(job_items)
    with Progress() as progress:
        progress_bar = progress.add_task(
            "Counting brake cleaners...", total=len(sorted_list)
        )

        for work_order in sorted_list.keys():
            try:
                brake_cleaner_per_work_order_dict = (
                    _divide_brake_cleaners_per_work_order(
                        sorted_list[work_order], tech_names, item_key
                    )
                )

                for tech in tech_names:
                    brake_cleaner_dict[tech] += brake_cleaner_per_work_order_dict[tech]

            except Exception:
                logger.error(f"count_brake_cleaners error: {traceback.format_exc()}")

            progress.update(progress_bar, advance=1)

    for name in brake_cleaner_dict.keys():
        brake_cleaner_dict[name] = round(brake_cleaner_dict[name])

    return brake_cleaner_dict


def get_date(date_type: str) -> str:
    while True:
        year = input(f"Please enter the {date_type} year: ")
        month = input(f"Please enter the {date_type} month: ")

        try:
            year_int, month_int = int(year), int(month)
            prmonth(year_int, month_int)
            day = input(f"Please enter the {date_type} day: ")

        except ValueError:
            print("[red bold]Invalid year or month! Try again![/]")
            continue

        try:
            day_int = int(day)
            date_input = date(year_int, month_int, day_int).isoformat()

            return date_input

        except ValueError:
            print("[red bold]Invalid day! Try again![/]")
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


def resolve_report_type(key: str, reports_dict: dict) -> tuple[tuple, str, bool, bool]:
    exclude_flag = False
    parts_per_labor_hour_flag = False
    report_type = reports_dict[key]

    if key == "All Customers":
        exclude_flag = True

    elif key == "Parts per labor hour":
        parts_per_labor_hour_flag = True

    return (
        report_type["customer"],
        report_type["item"],
        exclude_flag,
        parts_per_labor_hour_flag,
    )


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


def get_report(remove_names=exclude_list) -> None:
    """Main entry point to get reports. Gathers user inputs and applies logic
    based on those inputs to get the correct report"""

    start_date = get_date("start")
    end_date = get_date("end")

    field_tech_list = get_technician_names(exclusions=remove_names)

    # Get user input for report type
    report_title = get_report_type(report_types)

    report_params = resolve_report_type(key=report_title, reports_dict=report_types)

    customers = report_params[0]
    item = report_params[1]
    exclude_flag = report_params[2]
    PPLH_flag = report_params[3]

    customer_filter = generate_customer_filter(customers, exclude=exclude_flag)

    async def main_async_fetch(coroutine_object, *args, **kwargs):
        async with httpx.AsyncClient() as client:
            return await coroutine_object(
                client,
                *args,
                **kwargs,
            )

    work_orders = asyncio.run(
        main_async_fetch(
            fetch_work_orders_by_range, start_date, end_date, customer_filter
        )
    )

    if PPLH_flag:
        job_items = asyncio.run(main_async_fetch(fetch_items, work_orders))

        report_dict = calculate_parts_per_labor_hour(field_tech_list, job_items)

    elif item == "brake cleaner":
        job_items = asyncio.run(main_async_fetch(fetch_items, work_orders, item))
        report_dict = count_brake_cleaners(field_tech_list, job_items, item)

    else:
        job_items = asyncio.run(main_async_fetch(fetch_items, work_orders, item))
        report_dict = tally_labor_items(field_tech_list, job_items, item)

    report_name = create_report_name(start_date, end_date, report_title)
    write_report_to_file(report_dict, report_name)

    logger.debug(
        f"get_report local vars:\n "
        f"start date: {start_date}\n"
        f"end date: {end_date}\n"
        f"field_tech_list: {field_tech_list}\n"
        f"report_params: {report_params}\n"
        f"work_orders: {work_orders}\n"
        f"report_dict: {report_dict}\n"
        f"customers: {customers}\n"
        f"item: {item}\n"
        f"exclude_flag: {exclude_flag}\n"
        f"PPLH Flag: {PPLH_flag}\n"
        f"Customer filter: {customer_filter}\n"
    )


def get_stored_data(report_file=REPORT_FILE_PATH) -> tuple[dict | None, dict | None]:
    print("Displaying reports...")

    if not os.path.exists(report_file):
        print("[red bold]Sorry! No data has been found.[/]")
        return None, None

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
    if data and selection_dict:
        print("Which report would you like to print?\n")

        selection = get_user_selection(selection_dict)

        if selection in selection_dict.keys():
            print_json(data=data[selection_dict[selection]])

        else:
            print("[red bold]Invalid selection![/]\n")


def delete_report(report_file=REPORT_FILE_PATH) -> None:
    data, selection_dict = get_stored_data()
    if data and selection_dict:
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
    plot_title = ""

    while True:
        data, selection_dict = get_stored_data()

        print("Which report would you like to plot?\n")

        if data and selection_dict:
            selection = get_user_selection(selection_dict)

            if selection in selection_dict.keys():
                labels.append(selection_dict[selection])
                report_to_plot = data[selection_dict[selection]]
                if plot_title == "":
                    plot_title = selection_dict[selection].split("::")[1]

                print("[green bold]Adding to list: [/]")
                print_json(data=report_to_plot)
                plots_list.append(report_to_plot)

            if input("Do you want to add another report? (y/n): ") != "y":
                break

    print("\nPlotting data...\n\n")

    y_label = report_types[plot_title]["ylabel"]
    plot_report_data(
        *plots_list,
        data_labels=labels,
        title=plot_title,
        label=y_label,
    )


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


def main():
    headers["Authorization"] = initialize_api_key(ENV_PATH)

    if not os.path.exists("data/"):
        os.makedirs("data/")

    print("Welcome to Labor Report Downloader\n")

    while True:
        main_menu()


if __name__ == "__main__":
    main()
