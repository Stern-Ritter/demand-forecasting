"""Tests for the forecast job lifecycle (upload → process → poll → download)."""
import io

import pytest
import requests

from conftest import api_url, wait_for_job, minimal_sales_csv


# ------------------------------------------------------------------ upload


def test_upload_csv_creates_job(authenticated_user):
    headers = authenticated_user["headers"]
    csv_bytes = minimal_sales_csv(n_series=2, n_days=60)

    r = requests.post(
        api_url("/forecast/upload"),
        files={"file": ("sales.csv", io.BytesIO(csv_bytes), "text/csv")},
        params={"horizon": 7},
        headers=headers,
        timeout=30,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    assert data["horizon"] == 7


def test_upload_wrong_extension_rejected(authenticated_user):
    headers = authenticated_user["headers"]
    r = requests.post(
        api_url("/forecast/upload"),
        files={"file": ("data.txt", io.BytesIO(b"id,date,sales\n"), "text/plain")},
        headers=headers,
        timeout=10,
    )
    assert r.status_code == 400


def test_upload_empty_file_rejected(authenticated_user):
    headers = authenticated_user["headers"]
    r = requests.post(
        api_url("/forecast/upload"),
        files={"file": ("sales.csv", io.BytesIO(b""), "text/csv")},
        headers=headers,
        timeout=10,
    )
    assert r.status_code == 400


def test_upload_requires_auth():
    csv_bytes = minimal_sales_csv(n_series=1, n_days=40)
    r = requests.post(
        api_url("/forecast/upload"),
        files={"file": ("sales.csv", io.BytesIO(csv_bytes), "text/csv")},
        timeout=10,
    )
    assert r.status_code == 401


# ------------------------------------------------------------------ process


def test_process_job_deducts_balance(authenticated_user):
    user = authenticated_user["user"]
    headers = authenticated_user["headers"]

    # Top-up balance
    requests.post(
        api_url("/balance/deposit"),
        json={"user_id": user["user_id"], "amount": 100.0},
        headers=headers,
        timeout=10,
    )

    # Get initial balance
    bal_r = requests.get(api_url(f"/balance/{user['user_id']}"), headers=headers, timeout=10)
    initial_balance = bal_r.json()["balance"]

    # Upload
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
    assert proc_r.status_code == 200, proc_r.text

    # Balance should have decreased
    bal_r2 = requests.get(api_url(f"/balance/{user['user_id']}"), headers=headers, timeout=10)
    assert bal_r2.json()["balance"] < initial_balance


def test_process_same_job_twice_rejected(authenticated_user):
    headers = authenticated_user["headers"]
    user_id = authenticated_user["user"]["user_id"]

    requests.post(
        api_url("/balance/deposit"),
        json={"user_id": user_id, "amount": 100.0},
        headers=headers,
        timeout=10,
    )

    csv_bytes = minimal_sales_csv(n_series=1, n_days=40)
    up_r = requests.post(
        api_url("/forecast/upload"),
        files={"file": ("sales.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=headers,
        timeout=30,
    )
    job_id = int(up_r.json()["job_id"])

    requests.post(api_url(f"/forecast/job/{job_id}/process"), headers=headers, timeout=10)
    r2 = requests.post(api_url(f"/forecast/job/{job_id}/process"), headers=headers, timeout=10)
    assert r2.status_code == 400


def test_process_another_users_job_forbidden(authenticated_user):
    """A second user cannot process the first user's job."""
    import uuid
    headers1 = authenticated_user["headers"]

    csv_bytes = minimal_sales_csv(n_series=1, n_days=40)
    up_r = requests.post(
        api_url("/forecast/upload"),
        files={"file": ("sales.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=headers1,
        timeout=30,
    )
    job_id = int(up_r.json()["job_id"])

    # Register + login second user
    login2 = f"u2_{uuid.uuid4().hex[:8]}"
    requests.post(api_url("/auth/signup"), json={
        "login": login2, "email": f"{login2}@test.com",
        "display_name": "User2", "password": "pass2",
    }, timeout=10)
    r2 = requests.post(api_url("/auth/signin"),
                       json={"login": login2, "password": "pass2"}, timeout=10)
    headers2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}

    proc_r = requests.post(api_url(f"/forecast/job/{job_id}/process"), headers=headers2, timeout=10)
    assert proc_r.status_code == 403


# ------------------------------------------------------------------ status


def test_get_job_status(authenticated_user):
    headers = authenticated_user["headers"]
    csv_bytes = minimal_sales_csv(n_series=1, n_days=40)
    up_r = requests.post(
        api_url("/forecast/upload"),
        files={"file": ("sales.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=headers,
        timeout=30,
    )
    job_id = int(up_r.json()["job_id"])

    status_r = requests.get(api_url(f"/forecast/job/{job_id}"), headers=headers, timeout=10)
    assert status_r.status_code == 200
    data = status_r.json()
    assert data["job_id"] == str(job_id)
    assert data["status"] == "pending"


# ------------------------------------------------------------------ download


def test_download_before_processing_rejected(authenticated_user):
    headers = authenticated_user["headers"]
    csv_bytes = minimal_sales_csv(n_series=1, n_days=40)
    up_r = requests.post(
        api_url("/forecast/upload"),
        files={"file": ("sales.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=headers,
        timeout=30,
    )
    job_id = int(up_r.json()["job_id"])

    dl_r = requests.get(api_url(f"/forecast/job/{job_id}/download"), headers=headers, timeout=10)
    assert dl_r.status_code == 400


# ------------------------------------------------------------------ list


def test_list_jobs_empty_for_new_user(authenticated_user):
    headers = authenticated_user["headers"]
    r = requests.get(api_url("/forecast/jobs"), headers=headers, timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_jobs_contains_created_jobs(authenticated_user):
    headers = authenticated_user["headers"]
    csv_bytes = minimal_sales_csv(n_series=1, n_days=40)
    requests.post(
        api_url("/forecast/upload"),
        files={"file": ("sales.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=headers,
        timeout=30,
    )
    r = requests.get(api_url("/forecast/jobs"), headers=headers, timeout=10)
    assert r.status_code == 200
    assert len(r.json()) >= 1


# ------------------------------------------------------------------ ML service unit tests
#
# These tests run the *worker* inference code directly (no running service).
# They assert that the pre-trained model from m5_models.ipynb (section 8) is
# loaded from ./model and used to forecast — the model is never retrained here.

import os
import sys

_ML_WORKER = os.path.join(os.path.dirname(__file__), "../ml_worker")
sys.path.insert(0, _ML_WORKER)

MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../model"))
SAMPLE_CSV = os.path.abspath(os.path.join(os.path.dirname(__file__), "../test_webservice_sample.csv"))

# All 41 features the notebook trained on (order matters for the model).
EXPECTED_FEATURES = [
    "rmean_h28_7", "rstd_h28_7", "rmean_h28_14", "rstd_h28_14",
    "rmean_h28_30", "rstd_h28_30", "rmean_h28_60", "rstd_h28_60",
    "rmax_h28_30", "rmin_h28_30", "zero_frac_h28_30",
    "dow_mean_4w_h28", "days_since_sale_h28",
    "days_since_release",
    "dayofweek", "is_weekend", "weekofyear", "dayofmonth", "month", "is_christmas",
    "snap", "sell_price", "price_change", "price_discount",
    "item_id_enc", "dept_id_enc", "cat_id_enc", "store_id_enc", "state_id_enc",
    "event_name_1_enc", "event_type_1_enc", "event_type_2_enc",
    "lag_1", "lag_2", "lag_7", "lag_8", "lag_14",
    "rmean_7", "rmean_28", "rstd_7", "rstd_28",
]


def test_load_model_bundle_matches_notebook():
    """The saved model exposes exactly the 41 features defined in the notebook."""
    from services.ml_service import load_model_bundle

    bundle = load_model_bundle(MODEL_DIR)

    assert bundle.feature_names == EXPECTED_FEATURES
    assert bundle.cat_features == [
        "item_id_enc", "dept_id_enc", "cat_id_enc", "store_id_enc", "state_id_enc",
        "event_name_1_enc", "event_type_1_enc", "event_type_2_enc",
    ]
    assert set(bundle.id_encodings.keys()) == {
        "item_id", "dept_id", "cat_id", "store_id", "state_id",
        "event_name_1", "event_type_1", "event_type_2",
    }
    assert hasattr(bundle.model, "predict")


def test_decompose_and_encode_m5_id():
    """An M5 id is split into category columns and mapped to known codes."""
    from services.ml_service import _decompose_id, _encode_ids, load_model_bundle
    import pandas as pd

    parts = _decompose_id("FOODS_1_001_TX_2_evaluation")
    assert parts == {
        "cat_id": "FOODS", "dept_id": "FOODS_1", "item_id": "FOODS_1_001",
        "state_id": "TX", "store_id": "TX_2",
    }

    bundle = load_model_bundle(MODEL_DIR)
    df = pd.DataFrame({
        "id": ["FOODS_1_001_TX_2_evaluation"],
        "date": pd.to_datetime(["2016-01-01"]),
        "sales": [0],
    })
    enc = _encode_ids(df, bundle.id_encodings)
    # This series existed in training, so every code must be a real (>= 0) category.
    for col in ("item_id_enc", "dept_id_enc", "cat_id_enc", "store_id_enc", "state_id_enc"):
        assert enc.loc[0, col] >= 0


def test_add_features_builds_notebook_columns():
    """Feature engineering produces the lag / rolling / calendar / price columns."""
    import pandas as pd
    import numpy as np
    from services.ml_service import add_features

    dates = pd.date_range("2020-01-01", periods=120)
    df = pd.DataFrame({
        "id": ["S1"] * 120 + ["S2"] * 120,
        "date": list(dates) * 2,
        "sales": list(np.random.randint(0, 10, 120)) * 2,
        "sell_price": [2.5] * 240,
    })

    out = add_features(df)
    for col in ("lag_1", "lag_14", "rmean_7", "rstd_28", "rmean_h28_60",
                "rmax_h28_30", "zero_frac_h28_30", "dow_mean_4w_h28",
                "days_since_sale_h28", "dayofweek", "weekofyear", "dayofmonth",
                "month", "is_christmas", "price_change", "price_discount"):
        assert col in out.columns


def test_run_forecast_uses_pretrained_model(tmp_path):
    """End-to-end inference on the notebook's test sample using the real model."""
    import pandas as pd
    from services.ml_service import load_and_validate, run_forecast

    df = load_and_validate(SAMPLE_CSV)
    n_series = df["id"].nunique()
    horizon = 7

    result = run_forecast(
        df, horizon=horizon, model_dir=MODEL_DIR, result_dir=str(tmp_path)
    )

    assert result["n_series"] == n_series
    assert os.path.exists(result["result_file_path"])

    fc_df = pd.read_csv(result["result_file_path"])
    assert set(fc_df.columns) == {"id", "date", "forecast"}
    assert len(fc_df) == n_series * horizon
    assert (fc_df["forecast"] >= 0).all()
    # Forecast dates are strictly after the last historical date.
    assert pd.to_datetime(fc_df["date"]).min() > df["date"].max()


def test_run_forecast_unknown_id_is_robust(tmp_path):
    """A series id absent from training encodings still forecasts (code -1)."""
    import pandas as pd
    import numpy as np
    from services.ml_service import run_forecast

    dates = pd.date_range("2020-01-01", periods=60)
    df = pd.DataFrame({
        "id": ["UNKNOWN_SERIES_X"] * 60,
        "date": dates,
        "sales": np.random.randint(0, 5, 60),
        "sell_price": 1.0,
        "snap": 0,
    })

    result = run_forecast(df, horizon=5, model_dir=MODEL_DIR, result_dir=str(tmp_path))

    fc_df = pd.read_csv(result["result_file_path"])
    assert len(fc_df) == 5
    assert (fc_df["forecast"] >= 0).all()


def test_ml_service_invalid_csv(tmp_path):
    """CSV missing required columns raises ValueError."""
    import pandas as pd
    from services.ml_service import load_and_validate

    bad_csv = tmp_path / "bad.csv"
    pd.DataFrame({"col_a": [1, 2], "col_b": [3, 4]}).to_csv(bad_csv, index=False)

    with pytest.raises(ValueError, match="missing required columns"):
        load_and_validate(str(bad_csv))
