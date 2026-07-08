"""Tests for user registration, authentication and profile management."""
import uuid

import pytest
import requests

from conftest import api_url


def test_signup_creates_user(signup_payload):
    r = requests.post(api_url("/auth/signup"), json=signup_payload, timeout=10)
    assert r.status_code == 201, r.text
    data = r.json()
    assert "user_id" in data


def test_signup_duplicate_login_rejected(signup_payload, created_user):
    dup = dict(signup_payload)
    dup["email"] = f"different_{uuid.uuid4().hex[:6]}@test.com"
    r = requests.post(api_url("/auth/signup"), json=dup, timeout=10)
    assert r.status_code == 409


def test_signup_duplicate_email_rejected(signup_payload, created_user):
    dup = dict(signup_payload)
    dup["login"] = f"other_{uuid.uuid4().hex[:8]}"
    r = requests.post(api_url("/auth/signup"), json=dup, timeout=10)
    assert r.status_code == 409


def test_signin_returns_token(created_user):
    r = requests.post(
        api_url("/auth/signin"),
        json={"login": created_user["login"], "password": created_user["password"]},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_signin_wrong_password(created_user):
    r = requests.post(
        api_url("/auth/signin"),
        json={"login": created_user["login"], "password": "wrong_password"},
        timeout=10,
    )
    assert r.status_code == 401


def test_me_returns_current_user(authenticated_user):
    headers = authenticated_user["headers"]
    r = requests.get(api_url("/auth/me"), headers=headers, timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data["login"] == authenticated_user["user"]["login"]
    assert data["email"] == authenticated_user["user"]["email"]


def test_me_without_token_rejected():
    r = requests.get(api_url("/auth/me"), timeout=10)
    assert r.status_code == 401


def test_get_user_profile(authenticated_user):
    user = authenticated_user["user"]
    headers = authenticated_user["headers"]
    r = requests.get(api_url(f"/users/{user['user_id']}"), headers=headers, timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data["login"] == user["login"]
