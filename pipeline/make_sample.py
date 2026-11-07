"""Builds data/target_sample.db: a small, referentially complete sample (5,000 orders) of the REAL migrated
tables, so data questions work in a fresh Codespace without the 1.5M-row files.
Run after the full pipeline:  python -m pipeline.make_sample"""
import sqlite3
import config

N_ORDERS = 5000
OUT = config.ROOT / "data" / "target_sample.db"


def main():
    OUT.parent.mkdir(exist_ok=True)
    OUT.unlink(missing_ok=True)
    con = sqlite3.connect(OUT)
    con.execute(f"ATTACH DATABASE '{config.TARGET_DB}' AS full")
    # deterministic sample: every 20th order by id order
    con.execute("CREATE TABLE tgt_order AS SELECT * FROM (SELECT *, ROW_NUMBER() OVER (ORDER BY order_id) rn FROM full.tgt_order) WHERE rn % 20 = 0")
    con.execute("ALTER TABLE tgt_order DROP COLUMN rn")
    q = {
        "tgt_customer": "SELECT * FROM full.tgt_customer WHERE customer_key IN (SELECT customer_key FROM tgt_order)",
        "tgt_order_item": "SELECT * FROM full.tgt_order_item WHERE order_id IN (SELECT order_id FROM tgt_order)",
        "tgt_payment": "SELECT * FROM full.tgt_payment WHERE order_id IN (SELECT order_id FROM tgt_order)",
        "tgt_review": "SELECT * FROM full.tgt_review WHERE order_id IN (SELECT order_id FROM tgt_order)",
    }
    for t, sql in q.items():
        con.execute(f"CREATE TABLE {t} AS {sql}")
    con.execute("CREATE TABLE tgt_product AS SELECT * FROM full.tgt_product WHERE product_id IN (SELECT product_id FROM tgt_order_item)")
    con.execute("CREATE TABLE tgt_seller AS SELECT * FROM full.tgt_seller WHERE seller_id IN (SELECT seller_id FROM tgt_order_item)")
    con.execute("CREATE TABLE tgt_geolocation AS SELECT geo_zip_prefix, AVG(latitude) AS latitude, AVG(longitude) AS longitude, MIN(geo_city) AS geo_city, MIN(geo_state) AS geo_state FROM full.tgt_geolocation WHERE geo_zip_prefix IN (SELECT customer_zip_prefix FROM tgt_customer) GROUP BY geo_zip_prefix")
    con.commit()
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        print(t, con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    con.execute("VACUUM")
    con.close()


if __name__ == "__main__":
    main()
