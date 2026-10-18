import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(_tmp, "test.db")
os.environ.setdefault("VERCEL", "")

import app as app_module  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture
def client():
    app_module.initialize_db()
    # clean tables
    conn = app_module.get_db()
    conn.execute("DELETE FROM bills")
    conn.commit()
    conn.close()
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c
