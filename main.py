import os
import json
import requests
import traceback

from time import sleep
from datetime import date
from calendar import prmonth
from dotenv import load_dotenv

REPORT_FILE = "reports.json"

URL = "https://rest.method.me/api/v1"

load_dotenv(dotenv_path=".env")

report_types = {
    "Lost Time": "Accurate - Lost Time",
    "Rental": "Accurate Rental",
    "Service Warranty": "Accurate Service Warranty",
    "Vehicle Maintenance": "Accurate Vehicle Maintenance",
    "All" : None
}



API_KEY = os.getenv("MY_API_KEY")

if not API_KEY:
    raise RuntimeError("MY_API_KEY could not be found")

headers = {'Authorization': f'APIKey {API_KEY}'}
payload = {}

def get_technician_names() -> list:
    params = {"skip": 0,
              "top": 100,
              "select": "FullName"}
    response = requests.get(f"{URL}/tables/FieldTechnicians", params=params, headers=headers)
    data = response.json()
    names_list = [name["FullName"] for name in data["value"]]
    return names_list

def get_work_orders_by_range(start, end, customer_filter) -> list:
    work_order_dict_list = []
    if customer_filter is not None:
        customer_filter_string = (f" and (EntityCompanyName eq '{customer_filter}' "
                                  f"or ContactsName eq '{customer_filter}')")
    else:
        customer_filter_string = ""
    params = {"skip": 0,
              "top": 100,
              "select": "RecordID",
              "filter": f"ActualCompletedDate ge '{start}T00:00:00' "
                        f"and ActualCompletedDate lt '{end}T00:00:00'{customer_filter_string}"}
    try:
        while True:
            response = requests.get(f"{URL}/tables/Activity", params=params, headers=headers)
            if response.status_code != 200:
                print(response.status_code)
                print(response.content)
                sleep(20)
                continue
            data = response.json()
            work_order_dict_list.extend(data["value"])
            if data["count"] < 100:
                break
            params['skip'] += 100
    except Exception:
        print(traceback.format_exc())
    work_order_list = [item["RecordID"] for item in work_order_dict_list]
    return work_order_list


def get_labor_items(work_order_num_list) -> list:
    data_list = []
    filter_list = []
    for num in work_order_num_list:
        filter_list.append(f"ActivityNo eq '{num}'")
    total = len(work_order_num_list)
    slice_size = 10
    # Break large wo list into bite sized chunks to pass as filter params
    split_list = [filter_list[i: i+slice_size] for i in range(0, total, slice_size)]
    param_list = []
    for item in split_list:
        param_list.append(" or ".join(item))

    for parameter in param_list:
        params = {"skip": 0,
                  "top": 100,
                  "select": "Item, Qty",
                  "filter": f"contains(Item,'labor') and {parameter}"}
        try:
            while True:
                response = requests.get(f"{URL}/tables/ActivityJobItems", params=params, headers=headers)
                if response.status_code != 200:
                    print(response.status_code)
                    print(response.content)
                    continue
                data = response.json()
                if "value" in data:
                    data_list.extend(data["value"])
                    if data["count"] < 100:
                        break
                    params['skip'] += 100
                else:
                    data_list.extend(data)
                    break
        except Exception:
            print(traceback.format_exc())
    return data_list

def calulate_pplh(items: list, tech_names: dict) -> dict:
    pass

def tally_labor_hours(items: list, tech_names: dict) -> dict:
    labor_dict = {name: 0 for name in field_tech_list}
    for job_item in items:
        try:
            if 'labor' in job_item["Item"]:
                tech_name_key = job_item["Item"].lstrip('labor:')
                if tech_name_key in tech_names:
                    labor_dict[tech_name_key] += job_item["Qty"]
        except Exception:
            print(traceback.format_exc())
            print(job_item)
            continue
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
            print("Invalid entry! Try again!")
            continue
        try:
            day_int = int(day)
            date_input = date(year_int, month_int, day_int).isoformat()
            return date_input
        except ValueError:
            print("Invalid entry! Try again!")
            continue

def write_report(data: dict, report_file=REPORT_FILE) -> None:
    with open(report_file, "w") as f:
        json.dump(data, f)
    

if __name__ == '__main__':
    start_date = get_date("start")
    end_date = get_date("end")
    field_tech_list = get_technician_names()

    work_orders = get_work_orders_by_range(start_date, end_date, LOST_TIME_CUSTOMER)

    job_items = get_labor_items(work_orders)
    labor_hours_dict = tally_labor_hours(job_items)
    print(labor_hours_dict)


