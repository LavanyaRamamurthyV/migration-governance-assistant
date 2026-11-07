# Data governance policy (sample policy for the Olist migration demo)

This is a SAMPLE policy written for this demo. It is not any real institution's policy. The thresholds in P-05 are the same values the pipeline enforces (config.py).

## Policies

### P-01 Data classification
Data is classified as Public, Internal, Confidential or Restricted. Personal data is Restricted. In this migration, customer_unique_id and free-text review comments are Restricted. Zip code prefixes are quasi-identifiers and are Confidential. Everything else is Internal.

### P-02 PII handling
Personal data must be tokenized or masked before it reaches the Data Hub and before any document is indexed for AI use. Direct identifiers are tokenized (customer_unique_id becomes customer_person_token). Free text is scanned for emails, phone numbers, national ids and long identifiers, and matches are masked. Quasi-identifiers are kept only at prefix level. Masking is pattern based and not exhaustive, so a human spot check is required each release.

### P-03 Retention
Transaction data (orders, order items, payments) is kept for 7 years. Customer and marketing data is kept for 3 years. Review text is kept for 2 years. Legacy staging copies are deleted 30 days after cutover.

### P-04 Access control
Restricted data requires data-owner approval and role-based access. Access is reviewed every quarter. Confidential data requires manager approval. Internal data is available to all employees.

### P-05 Migration reconciliation
Every migrated table must pass four checks, and each check has a threshold. Row counts must match 100 percent. Amount totals must match within 0.01 percent. Null-rate variance must be 0.5 percentage points or less per column. Key uniqueness must be preserved. Any failure blocks sign-off. Data-quality problems already present in the source are recorded as findings, not silently fixed.

### P-06 Layout change management
A record layout change needs an impact analysis, 10 business days notice to consuming teams, and sign-off from every consuming team. Every change gets a new layout version number and an entry in the version history.

### P-07 Decommissioning
A legacy platform can be switched off only after a 90 day parallel run, zero active consumers, and governance sign-off. Data is archived before deletion.

### P-08 AI usage
AI answers must cite their sources. When the answer is not in the approved documents the assistant must say so instead of guessing. A human must review any AI-suggested mapping before it is approved. Only masked documents may be indexed. Query logs are kept for 90 days.
