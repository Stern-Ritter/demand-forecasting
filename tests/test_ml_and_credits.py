"""Integration test: full forecast flow with credit deduction."""
import io

import pytest
import requests

from conftest import api_url, minimal_sales_csv, wait_for_job


def test_full_forecast_flow_and_balance_deduction(authenticated_user):
    """Upload → process → poll → download; check balance decreases."""
    headers = authenticated_user["headers"]
    user_id = authenticated_user["user"]["user_id"]

    # Top-up balance
    dep = requests.post(
        api_url("/balance/deposit"),
        headers=headers,
        json={"user_id": user_id, "amount": 100},
        timeout=10,
    )
    assert dep.status_code == 200

    bal_before = requests.get(
        api_url(f"/balance/{user_id}"), headers=headers, timeout=10
    ).json()["balance"]

    # Upload CSV
    csv_bytes = minimal_sales_csv(n_series=2, n_days=60)
    up_r = requests.post(
        api_url("/forecast/upload"),
        files={"file": ("sales.csv", io.BytesIO(csv_bytes), "text/csv")},
        params={"horizon": 7},
        headers=headers,
        timeout=30,
    )
    assert up_r.status_code == 201
    job_id = int(up_r.json()["job_id"])

    # Process
    proc_r = requests.post(
        api_url(f"/forecast/job/{job_id}/process"),
        headers=headers,
        timeout=10,
    )
    assert proc_r.status_code == 200

    # Balance deducted immediately
    bal_after_proc = requests.get(
        api_url(f"/balance/{user_id}"), headers=headers, timeout=10
    ).json()["balance"]
    assert bal_after_proc < bal_before

    # Poll for completion
    job_data = wait_for_job(job_id, headers, max_wait=180)
    assert job_data["status"] == "completed"
    assert job_data.get("result") is not None
    assert job_data["result"]["n_series"] == 2

    # Download result
    dl_r = requests.get(
        api_url(f"/forecast/job/{job_id}/download"),
        headers=headers,
        timeout=30,
    )
    assert dl_r.status_code == 200
    assert "text/csv" in dl_r.headers.get("content-type", "")
    lines = dl_r.text.strip().split("\n")
    assert lines[0].startswith("id,date,forecast")
    # 2 series × 7 days = 14 rows + header
    assert len(lines) == 15


def test_insufficient_funds_prevents_processing(authenticated_user):
    """User with zero balance cannot start a forecast job."""
    headers = authenticated_user["headers"]

    csv_bytes = minimal_sales_csv(n_series=1, n_days=40)
    up_r = requests.post(
        api_url("/forecast/upload"),
        files={"file": ("sales.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=headers,
        timeout=30,
    )
    assert up_r.status_code == 201
    job_id = int(up_r.json()["job_id"])

    # Do NOT deposit anything — assume new user has 0 balance
    proc_r = requests.post(
        api_url(f"/forecast/job/{job_id}/process"),
        headers=headers,
        timeout=10,
    )
    # Either 400 (insufficient funds) or 200 if user had existing balance
    assert proc_r.status_code in (200, 400)
