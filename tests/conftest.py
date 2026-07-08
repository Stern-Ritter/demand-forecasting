import io
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("BASE_URL", "http://localhost").rstrip("/")
API_PREFIX = os.environ.get("API_PREFIX", "/api/1.0").rstrip("/")


def api_url(path: str) -> str:
    path = path if path.startswith("/") else f"/{path}"
    return f"{BASE_URL}{API_PREFIX}{path}"


@pytest.fixture(scope="module")
def api_base():
    return api_url("")


@pytest.fixture
def unique_login():
    return f"user_{uuid.uuid4().hex[:12]}"


@pytest.fixture
def unique_email(unique_login):
    return f"{unique_login}@test.example.com"


@pytest.fixture
def user_password():
    return "top_secret"


@pytest.fixture
def signup_payload(unique_login, unique_email, user_password):
    return {
        "login": unique_login,
        "email": unique_email,
        "display_name": f"Test {unique_login}",
        "password": user_password,
    }


@pytest.fixture
def created_user(signup_payload):
    r = requests.post(api_url("/auth/signup"), json=signup_payload, timeout=10)
    assert r.status_code == 201, (r.status_code, r.text)
    data = r.json()
    return {
        "user_id": int(data["user_id"]),
        "login": signup_payload["login"],
        "password": signup_payload["password"],
        "email": signup_payload["email"],
        "display_name": signup_payload["display_name"],
    }


@pytest.fixture
def auth_headers(created_user):
    r = requests.post(
        api_url("/auth/signin"),
        json={"login": created_user["login"], "password": created_user["password"]},
        timeout=10,
    )
    assert r.status_code == 200, (r.status_code, r.text)
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def authenticated_user(created_user, auth_headers):
    return {"user": created_user, "headers": auth_headers}


def wait_for_job(job_id: int, headers: dict, max_wait: float = 120.0) -> dict:
    """Poll until job reaches completed or failed."""
    url = api_url(f"/forecast/job/{job_id}")
    start = time.monotonic()
    while time.monotonic() - start < max_wait:
        r = requests.get(url, headers=headers, timeout=10)
        assert r.status_code == 200, (r.status_code, r.text)
        data = r.json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(2.0)
    raise TimeoutError(f"Job {job_id} did not complete in {max_wait}s")


def minimal_sales_csv(n_series: int = 3, n_days: int = 60) -> bytes:
    """Generate a minimal valid sales CSV for testing."""
    import pandas as pd

    rows = []
    base_date = pd.Timestamp("2020-01-01")
    for i in range(n_series):
        sid = f"SERIES_{i:03d}"
        for d in range(n_days):
            rows.append({
                "id": sid,
                "date": (base_date + pd.Timedelta(days=d)).strftime("%Y-%m-%d"),
                "sales": max(0, int(5 + 3 * (d % 7 == 5) + (i * 2))),
            })
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode()
