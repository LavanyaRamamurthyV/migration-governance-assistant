# Reconciliation report

Data: Olist Brazilian E-Commerce Public Dataset (Kaggle, CC BY-NC-SA 4.0). Source system label: Teradata (stand-in: Olist CSV extract). Target: Target Platform (SQLite stand-in).

Run date: 2026-11-07. Result: 8 of 8 target tables PASS. Thresholds from policy P-05: row counts must match exactly; money totals within 0.01%; null-rate drift at most 0.5 percentage points; key uniqueness preserved.

## Summary

| Hub table | Source rows | Hub rows | Row match | Max null drift (pp) | Status |
|---|---|---|---|---|---|
| tgt_customer | 99,441 | 99,441 | Yes | 0.0 | PASS |
| tgt_order | 99,441 | 99,441 | Yes | 0.0 | PASS |
| tgt_order_item | 112,650 | 112,650 | Yes | 0.0 | PASS |
| tgt_payment | 103,886 | 103,886 | Yes | 0.0 | PASS |
| tgt_review | 99,224 | 99,224 | Yes | 0.0 | PASS |
| tgt_product | 32,951 | 32,951 | Yes | 0.0 | PASS |
| tgt_seller | 3,095 | 3,095 | Yes | 0.0 | PASS |
| tgt_geolocation | 1,000,163 | 1,000,163 | Yes | 0.0 | PASS |

## Table results

### tgt_customer reconciliation

Source rows: 99,441. Hub rows: 99,441. Row counts match: yes. Status: PASS.
Null-rate check: 5 columns, largest drift 0.0 pp (column customer_key), pass.
Key check on customer_key: 99,441 distinct in source, 99,441 in target. Unique in source: yes. Uniqueness preserved by migration: yes.
Tokenization check: 96,096 distinct customer_unique_id values became 96,096 distinct customer_person_token values (0 collisions).

### tgt_order reconciliation

Source rows: 99,441. Hub rows: 99,441. Row counts match: yes. Status: PASS.
Null-rate check: 8 columns, largest drift 0.0 pp (column order_id), pass.
Key check on order_id: 99,441 distinct in source, 99,441 in target. Unique in source: yes. Uniqueness preserved by migration: yes.

### tgt_order_item reconciliation

Source rows: 112,650. Hub rows: 112,650. Row counts match: yes. Status: PASS.
Amount check price_brl: source total 13,591,643.70, target total 13,591,643.70, difference 0.0% (pass).
Amount check freight_brl: source total 2,251,909.54, target total 2,251,909.54, difference 0.0% (pass).
Null-rate check: 7 columns, largest drift 0.0 pp (column order_id), pass.
Key check on order_id, item_seq: 112,650 distinct in source, 112,650 in target. Unique in source: yes. Uniqueness preserved by migration: yes.

### tgt_payment reconciliation

Source rows: 103,886. Hub rows: 103,886. Row counts match: yes. Status: PASS.
Amount check payment_value_brl: source total 16,008,872.12, target total 16,008,872.12, difference 0.0% (pass).
Null-rate check: 5 columns, largest drift 0.0 pp (column order_id), pass.
Key check on order_id, payment_seq: 103,886 distinct in source, 103,886 in target. Unique in source: yes. Uniqueness preserved by migration: yes.

### tgt_review reconciliation

Source rows: 99,224. Hub rows: 99,224. Row counts match: yes. Status: PASS.
Null-rate check: 7 columns, largest drift 0.0 pp (column review_id), pass.
Key check on review_id: 98,410 distinct in source, 98,410 in target. Unique in source: NO. Uniqueness preserved by migration: yes.

### tgt_product reconciliation

Source rows: 32,951. Hub rows: 32,951. Row counts match: yes. Status: PASS.
Null-rate check: 9 columns, largest drift 0.0 pp (column product_id), pass.
Key check on product_id: 32,951 distinct in source, 32,951 in target. Unique in source: yes. Uniqueness preserved by migration: yes.

### tgt_seller reconciliation

Source rows: 3,095. Hub rows: 3,095. Row counts match: yes. Status: PASS.
Null-rate check: 4 columns, largest drift 0.0 pp (column seller_id), pass.
Key check on seller_id: 3,095 distinct in source, 3,095 in target. Unique in source: yes. Uniqueness preserved by migration: yes.

### tgt_geolocation reconciliation

Source rows: 1,000,163. Hub rows: 1,000,163. Row counts match: yes. Status: PASS.
Null-rate check: 5 columns, largest drift 0.0 pp (column geo_zip_prefix), pass.

## Referential integrity

### Referential integrity checks
tgt_order_item.order_id -> tgt_order: 0 orphan rows.
tgt_payment.order_id -> tgt_order: 0 orphan rows.
tgt_review.order_id -> tgt_order: 0 orphan rows.
tgt_order.customer_key -> tgt_customer: 0 orphan rows.
tgt_order_item.product_id -> tgt_product: 0 orphan rows.
tgt_order_item.seller_id -> tgt_seller: 0 orphan rows.

## PII controls during migration

### PII controls applied during migration
customer_unique_id is tokenized (SHA-256 with a secret salt, first 16 hex characters). The raw value is not stored in the target.
Free-text review fields were scanned for emails, phone numbers, national ids and long identifiers. Items masked: {'phone': 3}.
Zip code prefixes are kept as 5-character strings and classified as quasi-identifiers.

## Data-quality findings

### F-01: Duplicate review_id values in the source (excess rows)

Finding F-01: Duplicate review_id values in the source (excess rows). Count: 814.
Impacted teams: Customer Experience
Blocks cutover: yes
Recommendation: Agree a de-duplication rule with the data owner. Rows were kept so that counts reconcile.
Status: Open

### F-02: Delivered orders with no delivered timestamp

Finding F-02: Delivered orders with no delivered timestamp. Count: 8.
Impacted teams: Logistics, Finance
Blocks cutover: yes
Recommendation: Confirm with Order Management whether the status or the timestamp is wrong before cutover.
Status: Open

### F-03: Orders with no order items

Finding F-03: Orders with no order items. Count: 775.
Impacted teams: Finance, Logistics
Blocks cutover: no (warning)
Recommendation: Mostly cancelled or unavailable orders. Exclude them from revenue feeds explicitly.
Status: Open

### F-04: Orders with no payment record

Finding F-04: Orders with no payment record. Count: 1.
Impacted teams: Finance
Blocks cutover: no (warning)
Recommendation: Confirm these orders are expected to have no payment.
Status: Open

### F-05: Products with no category name

Finding F-05: Products with no category name. Count: 610.
Impacted teams: Marketing, Seller Ops
Blocks cutover: no (warning)
Recommendation: Ask the catalog owner for a default category or a backfill.
Status: Open

### F-06: Products whose category has no English translation

Finding F-06: Products whose category has no English translation. Count: 13.
Impacted teams: Marketing
Blocks cutover: no (warning)
Recommendation: Add the missing rows to the translation lookup.
Status: Open
