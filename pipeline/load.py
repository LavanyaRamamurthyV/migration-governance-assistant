"""Step 1: Load.

Reads the 9 Olist CSV files exactly as they are (everything as text, like a flat-file
extract from a legacy system) and writes them into a "legacy staging" SQLite database.
"""
import sqlite3

import pandas as pd

import config
from pipeline.spec import LOOKUP_SOURCES, TABLES


def source_files() -> dict:
    files = {t["name"]: t["source_file"] for t in TABLES}
    files.update(LOOKUP_SOURCES)
    return files


def read_source(filename: str) -> pd.DataFrame:
    # dtype=str keeps leading zeros (zip codes) and avoids silent type guessing.
    # Only truly empty cells become nulls.
    return pd.read_csv(config.RAW_DIR / filename, dtype=str, keep_default_na=False,
                       na_values=[""], encoding="utf-8-sig")


def run(ctx):
    files = source_files()
    missing = [f for f in files.values() if not (config.RAW_DIR / f).exists()]
    if missing:
        raise SystemExit(
            f"\nMissing Olist files in {config.RAW_DIR}:\n  " + "\n  ".join(missing) +
            "\nDownload the dataset from https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce "
            "and unzip it into data/raw/ (or set RAW_DIR in .env).")
    config.STORAGE.mkdir(parents=True, exist_ok=True)
    if config.LEGACY_DB.exists():
        config.LEGACY_DB.unlink()
    con = sqlite3.connect(config.LEGACY_DB)
    frames, rows = {}, {}
    for name, filename in files.items():
        df = read_source(filename)
        df.to_sql(f"stg_{name}", con, index=False, if_exists="replace", chunksize=100_000)
        frames[name] = df
        rows[name] = len(df)
    con.commit()
    con.close()
    ctx["frames"] = frames
    ctx["staging_rows"] = rows
    return f"{len(files)} files, {sum(rows.values()):,} rows loaded into legacy staging"
