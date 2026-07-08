"""
LightGBM demand forecasting **inference** service.

The model is trained offline in the M5 notebook (`m5_models.ipynb`, section 8)
and saved to ``MODEL_DIR`` as four joblib artifacts:

  * ``lgbm_recursive.pkl``  — the trained ``LGBMRegressor`` (``lgbm_rec``)
  * ``feature_names.pkl``   — ordered list of the 41 features the model expects
  * ``cat_features.pkl``    — the 8 categorical ``*_enc`` feature names
  * ``id_encodings.pkl``    — ``{column: {raw_value: code}}`` category encodings

This module **loads** that model (it never retrains it) and reconstructs the
exact 41-feature set from the notebook so that inference matches training:

  lag_1, lag_2, lag_7, lag_8, lag_14
  rmean_7, rmean_28, rstd_7, rstd_28
  rmean_h28_{7,14,30,60}, rstd_h28_{7,14,30,60}   (leak-safe, shifted by 28)
  rmax_h28_30, rmin_h28_30, zero_frac_h28_30
  dow_mean_4w_h28, days_since_sale_h28            (leak-safe, shifted by 28)
  days_since_release
  dayofweek, is_weekend, weekofyear, dayofmonth, month, is_christmas
  snap, sell_price, price_change, price_discount
  item_id_enc, dept_id_enc, cat_id_enc, store_id_enc, state_id_enc
  event_name_1_enc, event_type_1_enc, event_type_2_enc

Forecasting is recursive: each predicted day is appended to the history and the
lag/rolling features are recomputed before predicting the next day.

Assumptions for the forecast horizon (future values that the uploaded CSV cannot
contain): ``sell_price`` is carried forward from the last observed value; ``snap``
defaults to 0; the three event columns default to "no event" (encoded as -1, the
same code the model saw for eventless days during training).
"""

import logging
import os
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLS = {"id", "date", "sales"}

LAG_COLS = [1, 2, 7, 8, 14, 28]
ROLL_WINS = [7, 28]
H28_WINS = [7, 14, 30, 60]

# Category columns derived from the series id (static per series).
ID_COLS = ["item_id", "dept_id", "cat_id", "store_id", "state_id"]
ID_ENC = [f"{c}_enc" for c in ID_COLS]
# Calendar event columns supplied per-row by the uploaded CSV (time-varying).
EVENT_COLS = ["event_name_1", "event_type_1", "event_type_2"]
EVENT_ENC = [f"{c}_enc" for c in EVENT_COLS]

# The deepest look-back feature is rmean_h28_60 = shift(28).rolling(60) (~88 days);
# dow_mean_4w_h28 reaches shift(49). Trim each series to this many trailing days
# before recursion to bound the cost.
LOOKBACK_DAYS = 100

MODEL_ARTIFACTS = {
    "model": "lgbm_recursive.pkl",
    "feature_names": "feature_names.pkl",
    "cat_features": "cat_features.pkl",
    "id_encodings": "id_encodings.pkl",
}


# ------------------------------------------------------------------ model load


@dataclass
class ModelBundle:
    model: object
    feature_names: List[str]
    cat_features: List[str]
    id_encodings: Dict[str, Dict[str, int]]


@lru_cache(maxsize=1)
def load_model_bundle(model_dir: str) -> ModelBundle:
    """Load the pre-trained model and its metadata once per worker process."""
    paths = {k: os.path.join(model_dir, fname) for k, fname in MODEL_ARTIFACTS.items()}
    missing = [p for p in paths.values() if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError(
            f"Model artifacts not found in '{model_dir}': {missing}. "
            f"Run section 8 of m5_models.ipynb to generate them."
        )

    bundle = ModelBundle(
        model=joblib.load(paths["model"]),
        feature_names=list(joblib.load(paths["feature_names"])),
        cat_features=list(joblib.load(paths["cat_features"])),
        id_encodings=joblib.load(paths["id_encodings"]),
    )
    logger.info(
        "Loaded pre-trained model from %s (%d features, %d categorical)",
        model_dir,
        len(bundle.feature_names),
        len(bundle.cat_features),
    )
    return bundle


# ------------------------------------------------------------------ id parsing


def _decompose_id(series_id: str) -> Dict[str, str]:
    """
    Split an M5 series id into its category columns, e.g.
    ``FOODS_1_001_TX_2_evaluation`` -> item_id=FOODS_1_001, dept_id=FOODS_1,
    cat_id=FOODS, store_id=TX_2, state_id=TX.

    Unrecognised ids fall back to the raw id for every column (encoded as the
    unseen-category code -1 downstream).
    """
    parts = str(series_id).split("_")
    if parts and parts[-1] in ("evaluation", "validation"):
        parts = parts[:-1]
    if len(parts) >= 5:
        return {
            "cat_id": parts[0],
            "dept_id": f"{parts[0]}_{parts[1]}",
            "item_id": f"{parts[0]}_{parts[1]}_{parts[2]}",
            "state_id": parts[3],
            "store_id": f"{parts[3]}_{parts[4]}",
        }
    return {c: str(series_id) for c in ID_COLS}


def _encode_ids(df: pd.DataFrame, id_encodings: Dict[str, Dict[str, int]]) -> pd.DataFrame:
    """Attach the 5 static ``*_enc`` id columns using the training encodings."""
    meta = df[["id"]].drop_duplicates().reset_index(drop=True)
    decomposed = meta["id"].map(_decompose_id).apply(pd.Series)
    meta = pd.concat([meta, decomposed], axis=1)
    for c in ID_COLS:
        mapping = id_encodings.get(c, {})
        meta[f"{c}_enc"] = meta[c].map(mapping).fillna(-1).astype("int32")
    enc_cols = ["id"] + ID_ENC
    return df.merge(meta[enc_cols], on="id", how="left")


def _encode_events(df: pd.DataFrame, id_encodings: Dict[str, Dict[str, int]]) -> pd.DataFrame:
    """Attach the 3 per-row ``event_*_enc`` columns using the training encodings.

    Missing columns or values (empty / unseen events) are encoded as -1, which is
    exactly the code the model saw for eventless days during training.
    """
    for c in EVENT_COLS:
        mapping = id_encodings.get(c, {})
        if c in df.columns:
            df[f"{c}_enc"] = df[c].map(mapping).fillna(-1).astype("int32")
        else:
            df[f"{c}_enc"] = np.int32(-1)
    return df


# ------------------------------------------------------------------ load / prep


def load_and_validate(file_path: str) -> pd.DataFrame:
    """Read the uploaded CSV, validate its schema and normalise columns.

    Output columns: id, date, sales, sell_price, snap, event_name_1,
    event_type_1, event_type_2.
    """
    df = pd.read_csv(file_path)
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")

    df["date"] = pd.to_datetime(df["date"])
    df["sales"] = pd.to_numeric(df["sales"], errors="coerce").fillna(0).clip(lower=0)

    if "sell_price" in df.columns:
        df["sell_price"] = pd.to_numeric(df["sell_price"], errors="coerce")
    else:
        df["sell_price"] = np.nan

    if "snap" in df.columns:
        df["snap"] = pd.to_numeric(df["snap"], errors="coerce").fillna(0).astype(int)
    else:
        df["snap"] = 0

    # Keep event columns as raw strings (missing -> NA); they are encoded later.
    for c in EVENT_COLS:
        df[c] = df[c].astype("string") if c in df.columns else pd.NA

    df = df.sort_values(["id", "date"]).reset_index(drop=True)
    # Forward/back fill prices within each series, then default the rest to 0.
    df["sell_price"] = df.groupby("id")["sell_price"].ffill().bfill().fillna(0.0)
    return df[["id", "date", "sales", "sell_price", "snap"] + EVENT_COLS]


def _first_sale_date(df: pd.DataFrame) -> pd.Series:
    """First date with positive sales per series (min date if never sold)."""
    first = df[df["sales"] > 0].groupby("id")["date"].min()
    all_min = df.groupby("id")["date"].min()
    return first.reindex(all_min.index).fillna(all_min)


# ------------------------------------------------------------------ features


def add_features(data: pd.DataFrame) -> pd.DataFrame:
    """Reproduce the notebook's ``add_features`` (lag / rolling / calendar / price)."""
    data = data.sort_values(["id", "date"]).copy().reset_index(drop=True)
    g = data.groupby("id")["sales"]

    for lag in LAG_COLS:
        data[f"lag_{lag}"] = g.shift(lag)
    for w in ROLL_WINS:
        data[f"rmean_{w}"] = g.shift(1).rolling(w).mean()
        data[f"rstd_{w}"] = g.shift(1).rolling(w).std()

    s28 = g.shift(28)
    g28 = s28.groupby(data["id"])
    new_roll: List[str] = []
    for w in H28_WINS:
        cm, cs = f"rmean_h28_{w}", f"rstd_h28_{w}"
        data[cm] = g28.rolling(w).mean().reset_index(level=0, drop=True).astype("float32")
        data[cs] = g28.rolling(w).std().reset_index(level=0, drop=True).astype("float32")
        new_roll += [cm, cs]
    data["rmax_h28_30"] = g28.rolling(30).max().reset_index(level=0, drop=True).astype("float32")
    data["rmin_h28_30"] = g28.rolling(30).min().reset_index(level=0, drop=True).astype("float32")
    new_roll += ["rmax_h28_30", "rmin_h28_30"]

    data["_iszero"] = (data["sales"] == 0).astype("float32")
    z28 = data.groupby("id")["_iszero"].shift(28)
    data["zero_frac_h28_30"] = (
        z28.groupby(data["id"]).rolling(30).mean().reset_index(level=0, drop=True).astype("float32")
    )
    data.drop(columns="_iszero", inplace=True)
    new_roll.append("zero_frac_h28_30")

    # Same weekday over the previous 4 weeks, shifted by the 28-day horizon.
    data["dow_mean_4w_h28"] = (
        (g.shift(28) + g.shift(35) + g.shift(42) + g.shift(49)) / 4
    ).astype("float32")
    new_roll.append("dow_mean_4w_h28")

    # Days since the last positive sale, again shifted by the horizon (leak-safe).
    nonzero_date = data["date"].where(data["sales"] > 0)
    last_sale = nonzero_date.groupby(data["id"]).ffill()
    data["days_since_sale_h28"] = (
        (data["date"] - last_sale).dt.days.groupby(data["id"]).shift(28).astype("float32")
    )
    new_roll.append("days_since_sale_h28")

    for c in new_roll:
        data[c] = data[c].fillna(0)

    # calendar
    data["dayofweek"] = data["date"].dt.dayofweek.astype("int8")
    data["is_weekend"] = (data["dayofweek"] >= 5).astype("int8")
    data["weekofyear"] = data["date"].dt.isocalendar().week.astype("int16")
    data["dayofmonth"] = data["date"].dt.day.astype("int16")
    data["month"] = data["date"].dt.month.astype("int8")
    data["is_christmas"] = ((data["month"] == 12) & (data["dayofmonth"] == 25)).astype("int8")

    # price
    data["price_rmean_28"] = data.groupby("id")["sell_price"].transform(
        lambda x: x.shift(1).rolling(28).mean()
    ).astype("float32")
    data["price_change"] = (data["sell_price"] / data["price_rmean_28"] - 1).astype("float32")
    price_max_hist = data.groupby("id")["sell_price"].cummax()
    data["price_discount"] = (data["sell_price"] / price_max_hist).astype("float32")
    return data


def _build_feature_matrix(panel: pd.DataFrame, first_sale: pd.Series) -> pd.DataFrame:
    feats = add_features(panel)
    fsd = feats["id"].map(first_sale)
    feats["days_since_release"] = (
        (feats["date"] - fsd).dt.days.clip(lower=0).fillna(0).astype("int32")
    )
    return feats


def _predict(bundle: ModelBundle, frame: pd.DataFrame) -> np.ndarray:
    """Run the model on the feature columns it was trained with (clip to >= 0).

    The model was trained with the ``*_enc`` columns as pandas ``category`` dtype
    (their integer codes are the category values), so they must be passed as
    ``category`` here — LightGBM re-aligns them to the categories seen in training
    and treats unseen codes as missing. Numeric columns are plain ``float32``.
    """
    X = frame[bundle.feature_names].copy()
    X = X.replace([np.inf, -np.inf], 0)
    cat = set(bundle.cat_features)
    for c in bundle.feature_names:
        if c in cat:
            X[c] = X[c].fillna(-1).astype("int32").astype("category")
        else:
            X[c] = X[c].fillna(0).astype("float32")
    return np.clip(bundle.model.predict(X), 0, None)


# ------------------------------------------------------------------ forecasting


def _recursive_forecast(
    history: pd.DataFrame,
    first_sale: pd.Series,
    bundle: ModelBundle,
    horizon: int,
) -> pd.DataFrame:
    """Recursive one-step-ahead forecast for each series over ``horizon`` days."""
    ids = history["id"].unique()
    last_date = history["date"].max()

    # Trim to the trailing window needed by the deepest feature to bound cost.
    cutoff = last_date - pd.Timedelta(days=LOOKBACK_DAYS + horizon)
    panel = history[history["date"] > cutoff].copy()

    static_enc = panel.drop_duplicates("id").set_index("id")[ID_ENC]
    last_price = panel.sort_values("date").groupby("id")["sell_price"].last()

    records: List[Dict] = []
    for step in range(1, horizon + 1):
        future_date = last_date + pd.Timedelta(days=step)

        future = pd.DataFrame({"id": ids})
        future["date"] = future_date
        future["sales"] = np.nan
        future["sell_price"] = future["id"].map(last_price).fillna(0.0)
        future["snap"] = 0
        for c in ID_ENC:
            future[c] = future["id"].map(static_enc[c]).fillna(-1).astype("int32")
        # No calendar event known on the horizon -> "no event" code (-1).
        for c in EVENT_ENC:
            future[c] = np.int32(-1)

        panel = pd.concat([panel, future], ignore_index=True)
        feats = _build_feature_matrix(panel, first_sale)
        mask = feats["date"] == future_date
        preds = _predict(bundle, feats.loc[mask])

        pred_map = dict(zip(feats.loc[mask, "id"], preds))
        step_mask = panel["date"] == future_date
        panel.loc[step_mask, "sales"] = panel.loc[step_mask, "id"].map(pred_map)

        for sid in ids:
            records.append(
                {"id": sid, "date": future_date, "forecast": round(float(pred_map[sid]), 4)}
            )

    return pd.DataFrame(records)[["id", "date", "forecast"]]


def run_forecast(
    df: pd.DataFrame,
    horizon: int,
    model_dir: str,
    result_dir: str,
) -> Dict:
    """Load the pre-trained model and produce ``horizon``-day forecasts.

    Returns a dict with the number of forecasted series and the result CSV path.
    """
    bundle = load_model_bundle(model_dir)

    # Defaults for callers that bypass ``load_and_validate``.
    if "sell_price" not in df.columns:
        df["sell_price"] = 0.0
    if "snap" not in df.columns:
        df["snap"] = 0

    df = _encode_ids(df, bundle.id_encodings)
    df = _encode_events(df, bundle.id_encodings)
    df = df[["id", "date", "sales", "sell_price", "snap"] + ID_ENC + EVENT_ENC]

    first_sale = _first_sale_date(df)

    forecasts = _recursive_forecast(df, first_sale, bundle, horizon)
    n_series = forecasts["id"].nunique()

    os.makedirs(result_dir, exist_ok=True)
    result_path = os.path.join(result_dir, f"{uuid.uuid4().hex}_forecast.csv")
    forecasts.to_csv(result_path, index=False)
    logger.info(
        "Forecast saved to %s (%d series, %d rows)",
        result_path,
        n_series,
        len(forecasts),
    )

    return {
        "result_file_path": result_path,
        "n_series": n_series,
    }
