# Legacy G sunset plan (demo)

Legacy G is this demo's name for the legacy platform being retired, a stand-in for a Genesis-style sunset. Phase dates and owner roles are DEMO VALUES. The blockers and warnings are NOT invented: they come from the real reconciliation findings in reconciliation_report.md.

## Phases

### Phase 1: Inventory
Dates: 2026-11-16 to 2026-12-04 (demo). List every feed that reads from Legacy G, its owner, and its hub tables.

### Phase 2: Parallel run
Dates: 2026-12-07 to 2027-03-07 (demo). Run Legacy G and the Data Hub side by side for 90 days, as required by policy P-07, and compare outputs.

### Phase 3: Cutover
Dates: 2027-03-08 to 2027-03-12 (demo). Move each feed to the hub on its own cutover date after the consuming team signs off.

### Phase 4: Decommission
Dates: 2027-03-15 to 2027-03-26 (demo). Archive, then switch off Legacy G once there are zero active consumers and governance has signed off (policy P-07).

## Consumer inventory

### Feed marketing_campaign_feed (Marketing)

Team: Marketing
Owner role: Marketing Analytics Lead
Feed name: marketing_campaign_feed
Legacy G dependency: Nightly flat file keyed on customer_unique_id
Hub tables: hub_customer, hub_order, hub_product, hub_geolocation
Cutover date (demo): 2027-03-10
Migration status: Blocked
Blockers: The hub exposes customer_person_token instead of the raw customer_unique_id (policy P-02), so the campaign join key must be re-mapped before cutover.
Warnings: F-05 Products with no category name (610); F-06 Products whose category has no English translation (13)

### Feed finance_revenue_feed (Finance)

Team: Finance
Owner role: Finance Data Steward
Feed name: finance_revenue_feed
Legacy G dependency: Daily payment and revenue extract
Hub tables: hub_order, hub_order_item, hub_payment
Cutover date (demo): 2027-03-08
Migration status: Blocked
Blockers: F-02 Delivered orders with no delivered timestamp (8)
Warnings: F-03 Orders with no order items (775); F-04 Orders with no payment record (1)

### Feed logistics_delivery_feed (Logistics)

Team: Logistics
Owner role: Logistics Data Lead
Feed name: logistics_delivery_feed
Legacy G dependency: Delivery performance extract
Hub tables: hub_order, hub_order_item, hub_seller, hub_geolocation
Cutover date (demo): 2027-03-09
Migration status: Blocked
Blockers: F-02 Delivered orders with no delivered timestamp (8)
Warnings: F-03 Orders with no order items (775)

### Feed cx_review_feed (Customer Experience)

Team: Customer Experience
Owner role: Customer Experience Analyst
Feed name: cx_review_feed
Legacy G dependency: Weekly review and score extract
Hub tables: hub_review, hub_order, hub_customer
Cutover date (demo): 2027-03-11
Migration status: Blocked
Blockers: F-01 Duplicate review_id values in the source (excess rows) (814)
Warnings: none

### Feed seller_scorecard_feed (Seller Ops)

Team: Seller Ops
Owner role: Seller Operations Lead
Feed name: seller_scorecard_feed
Legacy G dependency: Monthly seller scorecard extract
Hub tables: hub_seller, hub_order_item, hub_product
Cutover date (demo): 2027-03-12
Migration status: Ready with warnings
Blockers: none
Warnings: F-05 Products with no category name (610)

## Risks

### Risk R-01: late sign-offs
Layout v2.0 needs sign-off from five consuming teams. A single late sign-off moves that team's cutover date.

### Risk R-02: join key change for Marketing
The hub stores customer_person_token, not the raw customer_unique_id, so campaign joins must be rebuilt and re-tested.

### Risk R-03: unresolved data-quality findings
Open blocking findings in the reconciliation report must be resolved or formally accepted by the data owner before cutover.

### Risk R-04: parallel-run cost
Running two platforms for 90 days doubles storage and monitoring effort. Track it weekly.
