import os
import pytest

# Set the test database path BEFORE any application code is imported.
# This ensures that `app.database.DB_PATH` evaluates to `test_paytrace.db`
# instead of the production `paytrace.db`.
TEST_DB = "test_paytrace.db"
os.environ["PAYTRACE_DB_PATH"] = TEST_DB

@pytest.fixture(scope="session", autouse=True)
def cleanup_test_db():
    """
    Ensure the test database is removed after the test suite finishes.
    """
    yield
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except OSError:
            pass



