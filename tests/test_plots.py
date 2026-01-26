import pytest

from src.plots import _calculate_mean, calculate_stand_dev


class TestCalculateMean:
    def test_ignore_zeros(self):
        zero_dict = {"A": 0, "B": 0, "C": 10.5, "D": 9.5}
        assert _calculate_mean(zero_dict) == pytest.approx(10.0)

    def test_all_zeros(self):
        all_zero_dict = {"A": 0, "B": 0, "C": 0, "D": 0}
        assert _calculate_mean(all_zero_dict) == 0

    def test_do_not_ignore_zeros(self):
        some_zero_dict = {"A": 0, "B": 0, "C": 10.5, "D": 9.5}
        assert _calculate_mean(some_zero_dict, ignore_zero=False) == pytest.approx(5.0)


class TestCalculateStandDev:
    @pytest.fixture()
    def test_dict(self):
        return {"A": 3, "B": 4, "C": 5, "D": 5, "E": 6, "F": 7}

    def test_calculate_with_mean(self, test_dict):
        assert calculate_stand_dev(test_dict, mean=5) == pytest.approx(1.2910)

    def test_calculate_without_mean(self, test_dict):
        assert calculate_stand_dev(test_dict) == pytest.approx(1.2910)