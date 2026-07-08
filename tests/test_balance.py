"""Tests for balance deposit and retrieval."""
import pytest
import requests

from conftest import api_url


def test_get_balance(authenticated_user):
    user = authenticated_user["user"]
    headers = authenticated_user["headers"]
    r = requests.get(api_url(f"/balance/{user['user_id']}"), headers=headers, timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "balance" in data
    assert isinstance(data["balance"], (int, float))


def test_deposit_increases_balance(authenticated_user):
    user = authenticated_user["user"]
    headers = authenticated_user["headers"]

    bal_before = requests.get(
        api_url(f"/balance/{user['user_id']}"), headers=headers, timeout=10
    ).json()["balance"]

    deposit_amount = 250.0
    r = requests.post(
        api_url("/balance/deposit"),
        json={"user_id": user["user_id"], "amount": deposit_amount},
        headers=headers,
        timeout=10,
    )
    assert r.status_code == 200, r.text

    bal_after = requests.get(
        api_url(f"/balance/{user['user_id']}"), headers=headers, timeout=10
    ).json()["balance"]
    assert abs(bal_after - (bal_before + deposit_amount)) < 1e-6


def test_deposit_negative_rejected(authenticated_user):
    user = authenticated_user["user"]
    headers = authenticated_user["headers"]
    r = requests.post(
        api_url("/balance/deposit"),
        json={"user_id": user["user_id"], "amount": -50.0},
        headers=headers,
        timeout=10,
    )
    assert r.status_code in (400, 422)


def test_withdraw_decreases_balance(authenticated_user):
    """Withdraw without an explicit currency must succeed (defaults to RUB)."""
    user = authenticated_user["user"]
    headers = authenticated_user["headers"]

    requests.post(
        api_url("/balance/deposit"),
        json={"user_id": user["user_id"], "amount": 100.0},
        headers=headers,
        timeout=10,
    )
    bal_before = requests.get(
        api_url(f"/balance/{user['user_id']}"), headers=headers, timeout=10
    ).json()["balance"]

    r = requests.post(
        api_url("/balance/withdraw"),
        json={"user_id": user["user_id"], "amount": 30.0},
        headers=headers,
        timeout=10,
    )
    assert r.status_code == 200, r.text

    bal_after = requests.get(
        api_url(f"/balance/{user['user_id']}"), headers=headers, timeout=10
    ).json()["balance"]
    assert abs(bal_after - (bal_before - 30.0)) < 1e-6


def test_withdraw_insufficient_funds_rejected(authenticated_user):
    """Withdrawing more than the available balance returns 400."""
    user = authenticated_user["user"]
    headers = authenticated_user["headers"]
    r = requests.post(
        api_url("/balance/withdraw"),
        json={"user_id": user["user_id"], "amount": 999999.0},
        headers=headers,
        timeout=10,
    )
    assert r.status_code == 400


def test_get_balance_other_user_forbidden(authenticated_user):
    import uuid
    login2 = f"u_{uuid.uuid4().hex[:8]}"
    rr = requests.post(api_url("/auth/signup"), json={
        "login": login2, "email": f"{login2}@t.com",
        "display_name": "U2", "password": "p2",
    }, timeout=10)
    user2_id = int(rr.json()["user_id"])

    headers1 = authenticated_user["headers"]
    r = requests.get(api_url(f"/balance/{user2_id}"), headers=headers1, timeout=10)
    assert r.status_code == 403


def test_transaction_history_after_deposit(authenticated_user):
    user = authenticated_user["user"]
    headers = authenticated_user["headers"]
    requests.post(
        api_url("/balance/deposit"),
        json={"user_id": user["user_id"], "amount": 10.0},
        headers=headers,
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
