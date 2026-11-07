"""Step 3: Reconcile (policy P-05).

Compares the legacy staging database with the Data Hub, table by table:
  - row counts must match exactly
  - money totals must match within AMOUNT_TOLERANCE_PCT
  - null rates may drift by at most NULL_RATE_TOLERANCE_PP percentage points
  - key uniqueness must be preserved
Then it runs data-quality checks on the hub and records them as findings.
"""
import json
import sqlite3

import numpy as np

import config
from pipeline.spec import TABLES


def scalar(con, sql):
    value = con.execute(sql).fetchone()[0]
    return 0 if value is None else value


def reconcile_table(leg, hub, t):
    stg, hubt = f"stg_{t['name']}", t["hub_table"]
    mapped = [c for c in t["columns"] if not c.get("lookup")]
    result = dict(table=hubt, source_file=t["source_file"])

    # 1) row counts
    result["source_rows"] = scalar(leg, f"SELECT COUNT(*) FROM {stg}")
    result["hub_rows"] = scalar(hub, f"SELECT COUNT(*) FROM {hubt}")
    result["row_match"] = result["source_rows"] == result["hub_rows"]

    # 2) money totals
    amounts = []
    for c in mapped:
        if c["kind"] != "dec2":
            continue
        s = float(scalar(leg, f"SELECT SUM(CAST({c['src']} AS REAL)) FROM {stg}"))
        h = float(scalar(hub, f"SELECT SUM({c['tgt']}) FROM {hubt}"))
        diff_pct = float(np.abs(s - h) / np.abs(s) * 100) if s else 0.0
        amounts.append(dict(column=c["tgt"], source_sum=round(s, 2), hub_sum=round(h, 2),
                            diff_pct=round(diff_pct, 6), passed=bool(diff_pct <= config.AMOUNT_TOLERANCE_PCT)))
    result["amount_checks"] = amounts

    # 3) null rates, per mapped column
    src_rates, hub_rates = [], []
    for c in mapped:
        src_rates.append(scalar(leg, f"SELECT SUM({c['src']} IS NULL) FROM {stg}") / max(result["source_rows"], 1) * 100)
        hub_rates.append(scalar(hub, f"SELECT SUM({c['tgt']} IS NULL) FROM {hubt}") / max(result["hub_rows"], 1) * 100)
    drift = np.abs(np.array(src_rates) - np.array(hub_rates))
    worst = int(np.argmax(drift)) if len(drift) else 0
    result["null_check"] = dict(
        max_drift_pp=round(float(drift.max()), 4) if len(drift) else 0.0,
        worst_column=mapped[worst]["tgt"] if mapped else None,
        passed=bool((drift <= config.NULL_RATE_TOLERANCE_PP).all()),
        columns_checked=len(mapped))

    # 4) key uniqueness preserved
    if t["key"]:
        src_key = ", ".join(next(c["src"] for c in mapped if c["tgt"] == k) for k in t["key"])
        hub_key = ", ".join(t["key"])
        s_distinct = scalar(leg, f"SELECT COUNT(*) FROM (SELECT DISTINCT {src_key} FROM {stg})")
        h_distinct = scalar(hub, f"SELECT COUNT(*) FROM (SELECT DISTINCT {hub_key} FROM {hubt})")
        result["key_check"] = dict(key=t["key"], source_distinct=s_distinct, hub_distinct=h_distinct,
                                   unique_in_source=bool(s_distinct == result["source_rows"]),
                                   preserved=bool(s_distinct == h_distinct))
    else:
        result["key_check"] = None

    # 5) tokenization must not create collisions
    if t["hub_table"] == "hub_customer":
        s = scalar(leg, f"SELECT COUNT(DISTINCT customer_unique_id) FROM {stg}")
        h = scalar(hub, f"SELECT COUNT(DISTINCT customer_person_token) FROM {hubt}")
        result["token_check"] = dict(source_distinct_persons=s, hub_distinct_tokens=h, collisions=int(s - h), passed=bool(s == h))
    else:
        result["token_check"] = None

    ok = (result["row_match"] and all(a["passed"] for a in amounts) and result["null_check"]["passed"]
          and (result["key_check"] is None or result["key_check"]["preserved"])
          and (result["token_check"] is None or result["token_check"]["passed"]))
    result["status"] = "PASS" if ok else "FAIL"
    return result


REFERENTIAL = [
    ("hub_order_item.order_id -> hub_order", "SELECT COUNT(*) FROM hub_order_item i WHERE NOT EXISTS (SELECT 1 FROM hub_order o WHERE o.order_id = i.order_id)"),
    ("hub_payment.order_id -> hub_order", "SELECT COUNT(*) FROM hub_payment p WHERE NOT EXISTS (SELECT 1 FROM hub_order o WHERE o.order_id = p.order_id)"),
    ("hub_review.order_id -> hub_order", "SELECT COUNT(*) FROM hub_review r WHERE NOT EXISTS (SELECT 1 FROM hub_order o WHERE o.order_id = r.order_id)"),
    ("hub_order.customer_key -> hub_customer", "SELECT COUNT(*) FROM hub_order o WHERE NOT EXISTS (SELECT 1 FROM hub_customer c WHERE c.customer_key = o.customer_key)"),
    ("hub_order_item.product_id -> hub_product", "SELECT COUNT(*) FROM hub_order_item i WHERE NOT EXISTS (SELECT 1 FROM hub_product p WHERE p.product_id = i.product_id)"),
    ("hub_order_item.seller_id -> hub_seller", "SELECT COUNT(*) FROM hub_order_item i WHERE NOT EXISTS (SELECT 1 FROM hub_seller s WHERE s.seller_id = i.seller_id)"),
]

# (title, sql, impacted teams, blocking?, recommendation)
FINDING_CHECKS = [
    ("Duplicate review_id values in the source (excess rows)",
     "SELECT COUNT(*) - COUNT(DISTINCT review_id) FROM hub_review",
     ["Customer Experience"], True,
     "Agree a de-duplication rule with the data owner. Rows were kept so that counts reconcile."),
    ("Delivered orders with no delivered timestamp",
     "SELECT COUNT(*) FROM hub_order WHERE order_status = 'delivered' AND delivered_ts IS NULL",
     ["Logistics", "Finance"], True,
     "Confirm with Order Management whether the status or the timestamp is wrong before cutover."),
    ("Orders with a delivered timestamp earlier than the purchase timestamp",
     "SELECT COUNT(*) FROM hub_order WHERE delivered_ts IS NOT NULL AND delivered_ts < purchase_ts",
     ["Logistics"], True,
     "Investigate clock or entry errors. Do not use these rows for delivery-time metrics."),
    ("Orders with no order items",
     "SELECT COUNT(*) FROM hub_order o WHERE NOT EXISTS (SELECT 1 FROM hub_order_item i WHERE i.order_id = o.order_id)",
     ["Finance", "Logistics"], False,
     "Mostly cancelled or unavailable orders. Exclude them from revenue feeds explicitly."),
    ("Orders with no payment record",
     "SELECT COUNT(*) FROM hub_order o WHERE NOT EXISTS (SELECT 1 FROM hub_payment p WHERE p.order_id = o.order_id)",
     ["Finance"], False,
     "Confirm these orders are expected to have no payment."),
    ("Products with no category name",
     "SELECT COUNT(*) FROM hub_product WHERE category_name_pt IS NULL",
     ["Marketing", "Seller Ops"], False,
     "Ask the catalog owner for a default category or a backfill."),
    ("Products whose category has no English translation",
     "SELECT COUNT(*) FROM hub_product WHERE category_name_pt IS NOT NULL AND category_name_en IS NULL",
     ["Marketing"], False,
     "Add the missing rows to the translation lookup."),
]


def run(ctx):
    leg = sqlite3.connect(config.LEGACY_DB)
    hub = sqlite3.connect(config.HUB_DB)
    tables = [reconcile_table(leg, hub, t) for t in TABLES]

    referential = [dict(check=name, orphans=int(scalar(hub, sql))) for name, sql in REFERENTIAL]

    findings = []
    for title, sql, teams, blocking, rec in FINDING_CHECKS:
        n = int(scalar(hub, sql))
        if n > 0:
            findings.append(dict(id=f"F-{len(findings) + 1:02d}", title=title, count=n, teams=teams,
                                 blocking=blocking, recommendation=rec, status="Open"))
    for r in referential:
        if r["orphans"] > 0:
            findings.append(dict(id=f"F-{len(findings) + 1:02d}", title=f"Orphan rows: {r['check']}", count=r["orphans"],
                                 teams=["Finance", "Logistics"], blocking=True,
                                 recommendation="Resolve the missing parent rows before cutover.", status="Open"))
    leg.close()
    hub.close()

    recon = dict(
        tables=tables, referential=referential, findings=findings,
        tables_passed=sum(1 for t in tables if t["status"] == "PASS"), tables_total=len(tables),
        thresholds=dict(row_count="exact match", amount_pct=config.AMOUNT_TOLERANCE_PCT,
                        null_rate_pp=config.NULL_RATE_TOLERANCE_PP))
    ctx["recon"] = recon
    config.RESULTS.mkdir(parents=True, exist_ok=True)
    (config.RESULTS / "reconciliation.json").write_text(json.dumps(recon, indent=2), encoding="utf-8")
    return f"{recon['tables_passed']}/{recon['tables_total']} tables PASS; {len(findings)} data-quality findings"
