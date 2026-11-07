# Migration runbook (sample for the Olist migration demo)

This runbook describes the validation checklist used for every table moved from the legacy extract to the Target Platform. It is a sample written for this demo.

## Migration steps

### Step 1: Extract
Receive the flat-file extract from the legacy system. Record the file name and the row count reported by the sender.

### Step 2: Load to staging
Load the file into the legacy staging database exactly as received, with every column as text. Do not clean anything at this stage.

### Step 3: Transform and load to the target
Apply the rules in the source-to-target mapping: rename columns, convert types, tokenize identifiers, and mask free text. Load the result into the Target Platform tables.

### Step 4: Reconcile
Compare staging and target using the P-05 checks: row counts, amount totals, null rates, and key uniqueness. Also run the referential integrity checks between target tables.

### Step 5: Log defects
Record every failed check as a defect. Record every problem that already exists in the source as a finding with an id, a count, the impacted teams, and whether it blocks cutover.

### Step 6: Sign-off
The data owner and the data governance lead review the reconciliation report. The table is signed off only when every P-05 check passes and every blocking finding is resolved or formally accepted.

## FAQ

### FAQ: What if row counts do not match?
Stop. Do not continue to sign-off. Log a defect, check the extract for truncation or duplicates, re-extract, and run the reconciliation again.

### FAQ: What if amount totals differ by more than 0.01 percent?
Treat it as a failed migration. Compare totals by group (for example by month) to find the rows that differ, fix the transformation rule, and re-run.

### FAQ: What if the source already has duplicate keys?
Keep the rows so that counts still reconcile, and log a finding. Ask the data owner for a de-duplication rule. Do not drop rows silently.

### FAQ: How are layout changes released?
Follow policy P-06: impact analysis, 10 business days notice, sign-off from every consuming team, then a new layout version number.

### FAQ: Who approves a mapping that an AI assistant suggested?
A human reviewer from the data owner team must approve it (policy P-08). The assistant can draft and explain, but it cannot approve.

### FAQ: When can a legacy platform be switched off?
After the 90 day parallel run, when there are zero active consumers and governance has signed off (policy P-07).
