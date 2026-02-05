import os
import pytest

from labor_report.main import initialize_api_key



class TestInitializeApiKey:
    @pytest.fixture
    def api_key(self):
        return "TEST_KEY"

    @pytest.fixture
    def api_key_file(self, tmp_path, api_key):
        os.chdir(tmp_path)
        temp_file = "api.txt"
        with open(temp_file, 'w') as f:
            f.write(f"MY_API_KEY={api_key}")
        return os.path.join(tmp_path, temp_file)

    def test_load_api_key(self, api_key_file, api_key):
        assert f"APIkey {api_key}" == initialize_api_key(api_key_file)



