import os
import pytest
import json
import httpx
import respx

from unittest.mock import patch, MagicMock

from labor_report.main import (
    generate_customer_filter,
    initialize_api_key,
    get_technician_names,
    get_work_order_count,
    URL,
    headers,
    sort_items_by_work_order,
    paginate_parameters,
    add_values,
    parameterize_wo_list,
    _divide_item_amounts_per_tech,
    calculate_parts_per_labor_hour,
)


class TestInitializeApiKey:
    def test_returns_key_from_env(self, monkeypatch):
        monkeypatch.setenv("METHOD_API_KEY", "my-secret-key")
        result = initialize_api_key(".env")
        assert result == "APIkey my-secret-key"

    def test_prompts_user_when_no_env_key(self, monkeypatch, tmp_path):
        monkeypatch.delenv("METHOD_API_KEY", raising=False)
        monkeypatch.setattr("builtins.input", lambda _: "manually-entered-key")
        key_path = tmp_path / ".env"
        result = initialize_api_key(key_path)
        assert result == "APIkey manually-entered-key"
        assert key_path.read_text() == "METHOD_API_KEY=manually-entered-key"

    def test_quits_when_user_enters_q(self, monkeypatch):
        monkeypatch.delenv("METHOD_API_KEY", raising=False)
        monkeypatch.setattr("builtins.input", lambda _: "q")
        monkeypatch.setattr("labor_report.main.load_dotenv", lambda **kwargs: None)
        with pytest.raises(SystemExit):
            initialize_api_key(".env")


class TestGetTechnicianNames:
    @pytest.fixture()
    def exclusions_list(self):
        return ["ExcludeJohn", "ExcludeJoe", "", None, 0, 1, True, []]

    @pytest.fixture()
    def names_response(self):
        return {
            "value": [
                {"FullName": "ExcludeJohn"},
                {"FullName": "ExcludeJoe"},
                {"FullName": "Harry"},
                {"FullName": "Margaret"},
            ]
        }

    def test_get_technician_names_with_respx(self, names_response, exclusions_list):
        with respx.mock:
            respx.get(f"{URL}/tables/FieldTechnicians").mock(
                return_value=httpx.Response(200, json=names_response)
            )

            result = get_technician_names(exclusions=exclusions_list)
            assert result == ["Harry", "Margaret"]


class TestGetWorkOrderCount:
    def _mock_response(self, count: int, status_code: int = 200):
        mock = MagicMock()
        mock.status_code = status_code
        mock.json.return_value = {"value": [{"TotalWorkOrders": str(count)}]}
        return mock

    def test_returns_correct_count(self):
        with patch("labor_report.main.httpx.get", return_value=self._mock_response(42)):
            result = get_work_order_count("2024-01-01", "2024-02-01", "")
            assert result == 42

    def test_returns_zero_work_orders(self):
        with patch("labor_report.main.httpx.get", return_value=self._mock_response(0)):
            result = get_work_order_count("2024-01-01", "2024-02-01", "")
            assert result == 0

    def test_passes_correct_params(self):
        with patch(
            "labor_report.main.httpx.get", return_value=self._mock_response(5)
        ) as mock_get:
            get_work_order_count("2024-01-01", "2024-02-01", " and CustomerID eq '123'")

            call_params = mock_get.call_args.kwargs["params"]
            assert "2024-01-01T00:00:00" in call_params["apply"]
            assert "2024-02-01T00:00:00" in call_params["apply"]
            assert "CustomerID eq '123'" in call_params["apply"]

    def test_non_200_response(self):
        with patch(
            "labor_report.main.httpx.get",
            return_value=self._mock_response(0, status_code=401),
        ):
            result = get_work_order_count("2024-01-01", "2024-02-01", "customer")
            assert result == 0


class TestGenerateCustomerFilter:
    """A formatted filter string for a single customer should like this:
    and ((EntityCompanyName eq 'CustomerABC' or ContactsName eq 'CustomerABC'))
    If there are multiple customer in the tuple, they should be joined
    with ' and '. Each customer filter should be surrounded in parentheses.
    The ' and ' should be substituted with ' or ' and the 'eq' should be
    substitued with 'ne' if the exclude param is True. After all joins
    take place, the final 'and' is prepended to the entire string along
    with a set of parentheses surrounding everything except the prepended 'and'
    """

    @pytest.fixture()
    def sample_filter_include(self):
        return " and ((EntityCompanyName eq 'CustomerABC' or ContactsName eq 'CustomerABC'))"

    @pytest.fixture()
    def sample_filter_exclude(self):
        return " and ((EntityCompanyName ne 'CustomerABC' or ContactsName ne 'CustomerABC'))"

    @pytest.fixture()
    def sample_filter_no_prefix(self, sample_filter_include):
        return sample_filter_include.removeprefix(" and (").removesuffix(")")

    def test_no_customers_input(self):
        result = generate_customer_filter((), False)
        assert result == ""

    def test_exclude_param(self, sample_filter_exclude, sample_filter_include):
        include_result = generate_customer_filter(("CustomerABC",), False)
        assert include_result == sample_filter_include
        exclude_result = generate_customer_filter(("CustomerABC",), True)
        assert exclude_result == sample_filter_exclude

    def test_multiple_customers(self, sample_filter_no_prefix):
        customers = tuple(["CustomerABC" for _ in range(3)])
        result = generate_customer_filter(customers, False)
        assert result.count(sample_filter_no_prefix) == 3
        assert result.count(" and ") == 1


class TestSortItemsByWorkOrder:
    @pytest.fixture()
    def work_order_items(self):
        return [
            {"ActivityNo": None, "SampleName": None},
            {"ActivityNo": "123", "SampleName": "TEST"},
            {"ActivityNo": "123", "SampleName": None},
            {"ActivityNo": "345", "SampleName": None},
            {"ActivityNo": "345", "SampleName": None},
        ]

    @pytest.fixture()
    def empty_list(self):
        return []

    def test_empty_list(self, empty_list):
        result = sort_items_by_work_order(empty_list)
        assert result == {}

    def test_multiple_work_orders(self, work_order_items):
        result = sort_items_by_work_order(work_order_items)
        assert len(result) == 2
        assert "123" in result.keys()
        assert "345" in result.keys()
        assert len(result["123"]) == 2
        assert result["123"][0]["SampleName"] == "TEST"
        assert len(result["345"]) == 2
        assert result["345"][0]["SampleName"] is None


class TestPaginateParameters:
    @pytest.fixture()
    def params(self):
        return {"skip": 0, "other": None}

    def test_no_count_in_keys(self, params):
        data = {"value": [{"item1": "something"}, {"item2", "something else"}]}
        result, count = paginate_parameters(params, data)
        assert result["skip"] == 0
        assert count == 0

    def test_count_in_keys(self, params):
        data = {"count": 70, "value": [{"item1": "nothing"}]}
        result, count = paginate_parameters(params, data)
        assert result["skip"] == 70
        assert count == 70


class TestAddValues:
    @pytest.fixture()
    def data_list(self):
        return [{"ID": 1}, {"ID": 2}, {"ID": 3}]

    def test_no_value_in_keys(self, data_list):
        response_data = {"ID": 4}
        data_copy = data_list.copy()
        data_copy.append(response_data.copy())
        full_list = add_values(data_list, response_data)
        assert full_list == data_copy

    def test_value_in_keys(self, data_list):
        response_data = {"count": 2, "value": [{"ID": 4}, {"ID", 5}]}
        data_copy = data_list.copy()
        data_copy.extend(response_data.copy()["value"])
        full_list = add_values(data_list, response_data)
        assert full_list == data_copy

    def test_no_value_in_keys_list_of_dicts(self, data_list):
        response_data = [{"ID": 4}, {"ID": 5}]
        data_copy = data_list.copy()
        data_copy.extend(response_data.copy())
        full_list = add_values(data_list, response_data)
        assert full_list == data_copy
