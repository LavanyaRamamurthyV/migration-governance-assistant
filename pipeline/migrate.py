"""Step 2: Migrate.

Turns the raw legacy staging data into clean Data Hub tables, following the
rules in pipeline/spec.py (rename, retype, trim, tokenize, mask free text).
"""
import hashlib
import sqlite3
from collections import Counter

import pandas as pd

import config
from pipeline.mask import mask_series
from pipeline.spec import TABLES


def _token(value: str) -> str:
    return hashlib.sha256((config.PII_SALT + value).encode("utf-8")).hexdigest()[:16]


def transform(series: pd.Series, kind: str, mask_counts: Counter) -> pd.Series:
    if kind == "id":
        return series.str.strip()
    if kind == "lower":
        return series.str.strip().str.lower()
    if kind == "upper":
        return series.str.strip().str.upper()
    if kind == "zip":
        return series.str.strip().str.zfill(5)
    if kind == "int":
        return pd.to_numeric(series, errors="coerce").astype("Int64")
    if kind == "dec2":
        return pd.to_numeric(series, errors="coerce").round(2)
    if kind == "float":
        return pd.to_numeric(series, errors="coerce")
    if kind == "ts":
        return pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    if kind == "token":
        lookup = {v: _token(v) for v in series.dropna().unique()}   # hash each distinct value once
        return series.map(lookup)
    if kind == "text_mask":
        masked, counts = mask_series(series)
        mask_counts.update(counts)
        return masked
    raise ValueError(f"unknown kind {kind}")


INDEXES = [
    ("hub_customer", "customer_key"), ("hub_order", "order_id"), ("hub_order", "customer_key"),
    ("hub_order_item", "order_id"), ("hub_order_item", "product_id"), ("hub_order_item", "seller_id"),
    ("hub_payment", "order_id"), ("hub_review", "order_id"), ("hub_product", "product_id"),
    ("hub_seller", "seller_id"),
]


def run(ctx):
    frames = ctx["frames"]
    if config.HUB_DB.exists():
        config.HUB_DB.unlink()
    con = sqlite3.connect(config.HUB_DB)
    mask_counts = Counter()
    translation = (frames["translation"]
                   .set_index("product_category_name")["product_category_name_english"])
    hub_rows = {}
    for t in TABLES:
        src = frames[t["name"]]
        out = pd.DataFrame(index=src.index)
        for col in t["columns"]:
            if col.get("lookup"):
                out[col["tgt"]] = out["category_name_pt"].map(translation)
            else:
                out[col["tgt"]] = transform(src[col["src"]], col["kind"], mask_counts)
        out.to_sql(t["hub_table"], con, index=False, if_exists="replace", chunksize=100_000)
        hub_rows[t["hub_table"]] = len(out)
    for table, column in INDEXES:
        con.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} ON {table}({column})")
    con.commit()
    con.close()
    ctx["hub_rows"] = hub_rows
    ctx["migration_mask"] = dict(mask_counts)
    return (f"{len(hub_rows)} hub tables, {sum(hub_rows.values()):,} rows; "
            f"free-text items masked: {dict(mask_counts) or 'none'}")
