"""Tests for transaction and forecast history endpoints."""
import io

import pytest
import requests

from conftest import api_url, minimal_sales_csv


def test_transaction_history_after_deposit(authenticated_user):
    user = authenticated_user["user"]
    headers = authenticated_user["headers"]

    requests.post(
        api_url("/balance/deposit"),
        headers=headers,
        json={"user_id": user["user_id"], "amount": 100, "currency": "RUB"},
        timeout=10,
    )

    r = requests.get(
        api_url(f"/history/transactions/{user['user_id']}"),
        headers=headers,
        timeout=10,
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any(t["type"] == "deposit" for t in data)


def test_transaction_history_forbidden_other_user(authenticated_user):
    import uuid
    login2 = f"u_{uuid.uuid4().hex[:8]}"
    rr = requests.post(api_url("/auth/signup"), json={
        "login": login2, "email": f"{login2}@t.com",
        "display_name": "U2", "password": "p2",
    }, timeout=10)
    user2_id = int(rr.json()["user_id"])

    headers1 = authenticated_user["headers"]
    r = requests.get(
        api_url(f"/history/transactions/{user2_id}"),
        headers=headers1,
        timeout=10,
    )
    assert r.status_code == 403


def test_forecast_history_empty_for_new_user(authenticated_user):
    user = authenticated_user["user"]
    headers = authenticated_user["headers"]

    r = requests.get(
        api_url(f"/history/forecasts/{user['user_id']}"),
        headers=headers,
        timeout=10,
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_forecast_history_shows_created_jobs(authenticated_user):
    user = authenticated_user["user"]
    headers = authenticated_user["headers"]

    csv_bytes = minimal_sales_csv(n_series=1, n_days=40)
    requests.post(
        api_url("/forecast/upload"),
        files={"file": ("s.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=headers,
        timeout=30,
    )

    r = requests.get(
        api_url(f"/history/forecasts/{user['user_id']}"),
        headers=headers,
        timeout=10,
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert "job_id" in data[0]
    assert "status" in data[0]
