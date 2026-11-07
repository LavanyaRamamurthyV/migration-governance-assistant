"""Single source of truth for the migration design.

One entry per source file: which hub table it becomes, which columns map where,
the transformation rule, and the PII flag. The migration code, the mapping
document, and the record-layout document are all generated from this file.

`kind` tells migrate.py how to transform the column:
  id / lower / upper / zip / int / dec2 / float / ts / token / text_mask
"""


def C(src, tgt, ttype, kind, rule, pii="N", **extra):
    return dict(src=src, tgt=tgt, ttype=ttype, kind=kind, rule=rule, pii=pii, **extra)


TABLES = [
    dict(
        name="customers", source_file="olist_customers_dataset.csv", hub_table="hub_customer",
        owner="Customer Data Office", consumers=["Marketing", "Customer Experience"],
        key=["customer_key"],
        columns=[
            C("customer_id", "customer_key", "VARCHAR(32)", "id",
              "Copy as surrogate key (trimmed). In the source this id is assigned per order.", "Y"),
            C("customer_unique_id", "customer_person_token", "VARCHAR(16)", "token",
              "Tokenize: SHA-256 with a secret salt, first 16 hex characters. The raw value is never copied to the hub.", "Y"),
            C("customer_zip_code_prefix", "customer_zip_prefix", "CHAR(5)", "zip",
              "Keep as a 5-character string and restore leading zeros. Quasi-identifier: kept at prefix level only.", "Quasi"),
            C("customer_city", "customer_city", "VARCHAR(60)", "lower", "Trim and lowercase."),
            C("customer_state", "customer_state", "CHAR(2)", "upper", "Trim and uppercase."),
        ]),
    dict(
        name="orders", source_file="olist_orders_dataset.csv", hub_table="hub_order",
        owner="Order Management Data", consumers=["Marketing", "Finance", "Logistics"],
        key=["order_id"],
        columns=[
            C("order_id", "order_id", "VARCHAR(32)", "id", "Copy (trimmed)."),
            C("customer_id", "customer_key", "VARCHAR(32)", "id", "Copy (trimmed). Foreign key to hub_customer.", "Y"),
            C("order_status", "order_status", "VARCHAR(12)", "lower", "Trim and lowercase. Values are not enumerated in the source."),
            C("order_purchase_timestamp", "purchase_ts", "TIMESTAMP", "ts", "Parse 'YYYY-MM-DD HH:MM:SS' text into an ISO timestamp."),
            C("order_approved_at", "approved_ts", "TIMESTAMP", "ts", "Parse text into an ISO timestamp. Nulls stay null."),
            C("order_delivered_carrier_date", "carrier_handoff_ts", "TIMESTAMP", "ts", "Parse text into an ISO timestamp. Nulls stay null."),
            C("order_delivered_customer_date", "delivered_ts", "TIMESTAMP", "ts", "Parse text into an ISO timestamp. Nulls stay null."),
            C("order_estimated_delivery_date", "estimated_delivery_ts", "TIMESTAMP", "ts", "Parse text into an ISO timestamp."),
        ]),
    dict(
        name="order_items", source_file="olist_order_items_dataset.csv", hub_table="hub_order_item",
        owner="Order Management Data", consumers=["Finance", "Seller Ops", "Logistics"],
        key=["order_id", "item_seq"],
        columns=[
            C("order_id", "order_id", "VARCHAR(32)", "id", "Copy (trimmed). Foreign key to hub_order."),
            C("order_item_id", "item_seq", "INTEGER", "int", "Cast text to integer. Position of the item within the order."),
            C("product_id", "product_id", "VARCHAR(32)", "id", "Copy (trimmed). Foreign key to hub_product."),
            C("seller_id", "seller_id", "VARCHAR(32)", "id", "Copy (trimmed). Foreign key to hub_seller."),
            C("shipping_limit_date", "shipping_limit_ts", "TIMESTAMP", "ts", "Parse text into an ISO timestamp."),
            C("price", "price_brl", "DECIMAL(18,2)", "dec2", "Cast to decimal, round to 2 places. No currency conversion (BRL)."),
            C("freight_value", "freight_brl", "DECIMAL(18,2)", "dec2", "Cast to decimal, round to 2 places. No currency conversion (BRL)."),
        ]),
    dict(
        name="payments", source_file="olist_order_payments_dataset.csv", hub_table="hub_payment",
        owner="Finance Data", consumers=["Finance", "Marketing"],
        key=["order_id", "payment_seq"],
        columns=[
            C("order_id", "order_id", "VARCHAR(32)", "id", "Copy (trimmed). Foreign key to hub_order."),
            C("payment_sequential", "payment_seq", "INTEGER", "int", "Cast text to integer."),
            C("payment_type", "payment_type", "VARCHAR(20)", "lower", "Trim and lowercase."),
            C("payment_installments", "installments_cnt", "INTEGER", "int", "Cast text to integer."),
            C("payment_value", "payment_value_brl", "DECIMAL(18,2)", "dec2", "Cast to decimal, round to 2 places. No currency conversion (BRL)."),
        ]),
    dict(
        name="reviews", source_file="olist_order_reviews_dataset.csv", hub_table="hub_review",
        owner="Customer Experience Data", consumers=["Customer Experience", "Marketing"],
        key=["review_id"],
        columns=[
            C("review_id", "review_id", "VARCHAR(32)", "id", "Copy (trimmed). Not unique in the source (see reconciliation findings)."),
            C("order_id", "order_id", "VARCHAR(32)", "id", "Copy (trimmed). Foreign key to hub_order."),
            C("review_score", "review_score", "INTEGER", "int", "Cast text to integer (1 to 5)."),
            C("review_comment_title", "comment_title", "VARCHAR(100)", "text_mask",
              "Free text. Emails, phone numbers, national ids and long identifiers are masked before loading.", "Y"),
            C("review_comment_message", "comment_message", "VARCHAR(500)", "text_mask",
              "Free text. Emails, phone numbers, national ids and long identifiers are masked before loading.", "Y"),
            C("review_creation_date", "review_created_ts", "TIMESTAMP", "ts", "Parse text into an ISO timestamp."),
            C("review_answer_timestamp", "review_answered_ts", "TIMESTAMP", "ts", "Parse text into an ISO timestamp."),
        ]),
    dict(
        name="products", source_file="olist_products_dataset.csv", hub_table="hub_product",
        owner="Product Catalog Data", consumers=["Marketing", "Seller Ops"],
        key=["product_id"],
        columns=[
            C("product_id", "product_id", "VARCHAR(32)", "id", "Copy (trimmed)."),
            C("product_category_name", "category_name_pt", "VARCHAR(60)", "lower", "Trim and lowercase. Portuguese category name."),
            C("product_name_lenght", "product_name_length", "INTEGER", "int", "Cast to integer. Renames the source typo 'lenght' to 'length'."),
            C("product_description_lenght", "product_description_length", "INTEGER", "int", "Cast to integer. Renames the source typo 'lenght' to 'length'."),
            C("product_photos_qty", "photos_qty", "INTEGER", "int", "Cast text to integer."),
            C("product_weight_g", "weight_g", "INTEGER", "int", "Cast text to integer (grams)."),
            C("product_length_cm", "length_cm", "INTEGER", "int", "Cast text to integer (centimetres)."),
            C("product_height_cm", "height_cm", "INTEGER", "int", "Cast text to integer (centimetres)."),
            C("product_width_cm", "width_cm", "INTEGER", "int", "Cast text to integer (centimetres)."),
            C("product_category_name_translation.product_category_name_english", "category_name_en", "VARCHAR(60)", "lookup",
              "Left join to product_category_name_translation on the Portuguese category name. Null when no translation exists.",
              lookup=True),
        ]),
    dict(
        name="sellers", source_file="olist_sellers_dataset.csv", hub_table="hub_seller",
        owner="Seller Operations Data", consumers=["Seller Ops", "Logistics"],
        key=["seller_id"],
        columns=[
            C("seller_id", "seller_id", "VARCHAR(32)", "id", "Copy (trimmed)."),
            C("seller_zip_code_prefix", "seller_zip_prefix", "CHAR(5)", "zip", "Keep as a 5-character string and restore leading zeros.", "Quasi"),
            C("seller_city", "seller_city", "VARCHAR(60)", "lower", "Trim and lowercase."),
            C("seller_state", "seller_state", "CHAR(2)", "upper", "Trim and uppercase."),
        ]),
    dict(
        name="geolocation", source_file="olist_geolocation_dataset.csv", hub_table="hub_geolocation",
        owner="Geo Reference Data", consumers=["Logistics", "Marketing"],
        key=[],
        columns=[
            C("geolocation_zip_code_prefix", "geo_zip_prefix", "CHAR(5)", "zip", "Keep as a 5-character string and restore leading zeros.", "Quasi"),
            C("geolocation_lat", "latitude", "DOUBLE", "float", "Cast text to floating point."),
            C("geolocation_lng", "longitude", "DOUBLE", "float", "Cast text to floating point."),
            C("geolocation_city", "geo_city", "VARCHAR(60)", "lower", "Trim and lowercase."),
            C("geolocation_state", "geo_state", "CHAR(2)", "upper", "Trim and uppercase."),
        ]),
]

# the 9th source file is a lookup table that is folded into hub_product
LOOKUP_SOURCES = {"translation": "product_category_name_translation.csv"}

TABLE_BY_HUB = {t["hub_table"]: t for t in TABLES}

# Downstream consumer feeds (used by the sunset plan). Demo design, built on the real tables above.
FEEDS = [
    dict(feed="marketing_campaign_feed", team="Marketing", owner_role="Marketing Analytics Lead",
         tables=["hub_customer", "hub_order", "hub_product", "hub_geolocation"],
         legacy_dependency="Nightly flat file keyed on customer_unique_id",
         cutover="2027-03-10",
         extra_blocker="The hub exposes customer_person_token instead of the raw customer_unique_id (policy P-02), "
                       "so the campaign join key must be re-mapped before cutover."),
    dict(feed="finance_revenue_feed", team="Finance", owner_role="Finance Data Steward",
         tables=["hub_order", "hub_order_item", "hub_payment"],
         legacy_dependency="Daily payment and revenue extract", cutover="2027-03-08", extra_blocker=None),
    dict(feed="logistics_delivery_feed", team="Logistics", owner_role="Logistics Data Lead",
         tables=["hub_order", "hub_order_item", "hub_seller", "hub_geolocation"],
         legacy_dependency="Delivery performance extract", cutover="2027-03-09", extra_blocker=None),
    dict(feed="cx_review_feed", team="Customer Experience", owner_role="Customer Experience Analyst",
         tables=["hub_review", "hub_order", "hub_customer"],
         legacy_dependency="Weekly review and score extract", cutover="2027-03-11", extra_blocker=None),
    dict(feed="seller_scorecard_feed", team="Seller Ops", owner_role="Seller Operations Lead",
         tables=["hub_seller", "hub_order_item", "hub_product"],
         legacy_dependency="Monthly seller scorecard extract", cutover="2027-03-12", extra_blocker=None),
]

# Proposed record layout v2 (target record layout update). Demo design, clearly labelled as such.
LAYOUT_V2_EFFECTIVE = "2027-01-15"
