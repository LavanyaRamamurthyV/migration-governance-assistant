# Record layout: v1.1 (current) and v2.0 (proposed)

Data: Olist Brazilian E-Commerce Public Dataset (Kaggle, CC BY-NC-SA 4.0). Source system label: Teradata (stand-in: Olist CSV extract). Target: Data Hub (SQLite stand-in).

Layout v1.1 is the layout actually produced by this migration. Layout v2.0 is a PROPOSED DEMO CHANGE: it shows how a target record layout update is documented, approved and communicated per policy P-06.

## Current layout v1.1

### hub_customer layout v1.1

Consuming teams: Marketing, Customer Experience. Fields in record order (position, name, type):
1. customer_key VARCHAR(32)
2. customer_person_token VARCHAR(16)
3. customer_zip_prefix CHAR(5)
4. customer_city VARCHAR(60)
5. customer_state CHAR(2)

### hub_order layout v1.1

Consuming teams: Marketing, Finance, Logistics. Fields in record order (position, name, type):
1. order_id VARCHAR(32)
2. customer_key VARCHAR(32)
3. order_status VARCHAR(12)
4. purchase_ts TIMESTAMP
5. approved_ts TIMESTAMP
6. carrier_handoff_ts TIMESTAMP
7. delivered_ts TIMESTAMP
8. estimated_delivery_ts TIMESTAMP

### hub_order_item layout v1.1

Consuming teams: Finance, Seller Ops, Logistics. Fields in record order (position, name, type):
1. order_id VARCHAR(32)
2. item_seq INTEGER
3. product_id VARCHAR(32)
4. seller_id VARCHAR(32)
5. shipping_limit_ts TIMESTAMP
6. price_brl DECIMAL(18,2)
7. freight_brl DECIMAL(18,2)

### hub_payment layout v1.1

Consuming teams: Finance, Marketing. Fields in record order (position, name, type):
1. order_id VARCHAR(32)
2. payment_seq INTEGER
3. payment_type VARCHAR(20)
4. installments_cnt INTEGER
5. payment_value_brl DECIMAL(18,2)

### hub_review layout v1.1

Consuming teams: Customer Experience, Marketing. Fields in record order (position, name, type):
1. review_id VARCHAR(32)
2. order_id VARCHAR(32)
3. review_score INTEGER
4. comment_title VARCHAR(100)
5. comment_message VARCHAR(500)
6. review_created_ts TIMESTAMP
7. review_answered_ts TIMESTAMP

### hub_product layout v1.1

Consuming teams: Marketing, Seller Ops. Fields in record order (position, name, type):
1. product_id VARCHAR(32)
2. category_name_pt VARCHAR(60)
3. product_name_length INTEGER
4. product_description_length INTEGER
5. photos_qty INTEGER
6. weight_g INTEGER
7. length_cm INTEGER
8. height_cm INTEGER
9. width_cm INTEGER
10. category_name_en VARCHAR(60)

### hub_seller layout v1.1

Consuming teams: Seller Ops, Logistics. Fields in record order (position, name, type):
1. seller_id VARCHAR(32)
2. seller_zip_prefix CHAR(5)
3. seller_city VARCHAR(60)
4. seller_state CHAR(2)

### hub_geolocation layout v1.1

Consuming teams: Logistics, Marketing. Fields in record order (position, name, type):
1. geo_zip_prefix CHAR(5)
2. latitude DOUBLE
3. longitude DOUBLE
4. geo_city VARCHAR(60)
5. geo_state CHAR(2)

## Proposed changes in layout v2.0 (demo change)

Effective date for all changes below: 2027-01-15 (demo value). Policy P-06 requires an impact analysis, 10 business days notice, and sign-off from every consuming team.

### CHG-001: hub_customer.consent_flag (New field)

Field: hub_customer.consent_flag
Change type: New field
v1 value: not present
v2 value: consent_flag CHAR(1), default 'U' (U = unknown, Y = consented, N = declined)
Effective date: 2027-01-15 (demo)
Impacted teams: Marketing, Customer Experience
Reason: Marketing needs the consent state before any campaign use.
Sign-off status: Pending

### CHG-002: hub_customer.customer_region_cd (New field)

Field: hub_customer.customer_region_cd
Change type: New field
v1 value: not present
v2 value: customer_region_cd CHAR(2), derived from customer_state (N, NE, CO, SE, S)
Effective date: 2027-01-15 (demo)
Impacted teams: Marketing, Logistics
Reason: Regional reporting without joining a state lookup in every feed.
Sign-off status: Pending

### CHG-003: hub_order.order_status (Modified field)

Field: hub_order.order_status
Change type: Modified field
v1 value: VARCHAR(12), longest observed value is 11 characters
v2 value: VARCHAR(20)
Effective date: 2027-01-15 (demo)
Impacted teams: Logistics, Finance, Marketing
Reason: Headroom for new order statuses without another layout change.
Sign-off status: Pending

### CHG-004: hub_payment.payment_value_brl (Modified field)

Field: hub_payment.payment_value_brl
Change type: Modified field
v1 value: DECIMAL(18,2)
v2 value: DECIMAL(18,4)
Effective date: 2027-01-15 (demo)
Impacted teams: Finance
Reason: Finance wants extra precision for installment and currency calculations.
Sign-off status: Pending

### CHG-005: hub_review.pii_masked_flag (New field)

Field: hub_review.pii_masked_flag
Change type: New field
v1 value: not present
v2 value: pii_masked_flag CHAR(1), 'Y' when masking changed the comment text
Effective date: 2027-01-15 (demo)
Impacted teams: Customer Experience
Reason: Makes the PII control visible to downstream users.
Sign-off status: Pending

### CHG-006: hub_order_item.currency_cd (New field)

Field: hub_order_item.currency_cd
Change type: New field
v1 value: not present
v2 value: currency_cd CHAR(3), default 'BRL'
Effective date: 2027-01-15 (demo)
Impacted teams: Finance
Reason: Prices are implicitly BRL today; make it explicit.
Sign-off status: Pending

## Version history

### Version v1.0
Date: 2026-11-02 (demo). Change: initial hub layout created from the legacy extract. Approver role: Data Governance Lead. Status: Superseded.

### Version v1.1
Date: 2026-11-06 (demo). Change: fixed the legacy typo 'lenght' to 'length' in two hub_product fields. Approver role: Data Architecture Lead. Status: Current.

### Version v2.0
Effective date: 2027-01-15 (demo). Change: CHG-001 to CHG-006 above. Approver roles: one per consuming team (Marketing, Finance, Logistics, Customer Experience, Seller Ops). Status: Proposed, sign-offs pending.
