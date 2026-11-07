"""The orchestrator for the batch (ingestion) workflow.

    python -m pipeline.run_pipeline               # all 7 steps (needs the Olist CSVs in data/raw/)
    python -m pipeline.run_pipeline --index-only  # steps 6-7 only, from the committed docs in docs/indexed/

This plain Python script is the orchestration layer for the batch side: it decides the order,
passes data between steps (the `ctx` dictionary), and stops on failure. In production the
same steps would be tasks in an Airflow / Cloud Composer DAG on a schedule.
"""
import argparse
import datetime as dt
import json
import time

import config
from pipeline import generate_docs, index, load, mask, migrate, reconcile

STEPS = [
    ("1. Load",              "pandas + SQLite",         load.run),
    ("2. Migrate",           "pandas + SQL",            migrate.run),
    ("3. Reconcile",         "pandas + NumPy + SQL",    reconcile.run),
    ("4. Generate docs",     "pandas + Python",         generate_docs.run),
    ("5. Mask PII",          "Python regex",            mask.run),
    ("6. Chunk",             "LangChain text splitter", index.chunk_docs),
    ("7. Embed and store",   "Chroma + scikit-learn",   index.embed_and_store),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-only", action="store_true", help="only run steps 6 and 7 on docs/indexed/")
    args = parser.parse_args()

    steps = STEPS[5:] if args.index_only else STEPS
    ctx, timings = {}, {}
    for name, tool, fn in steps:
        print(f"[{name}]  ({tool})")
        t0 = time.time()
        message = fn(ctx)
        timings[name] = round(time.time() - t0, 1)
        print(f"      done in {timings[name]}s: {message}")

    config.RESULTS.mkdir(parents=True, exist_ok=True)
    path = config.RESULTS / "run_summary.json"
    summary = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    summary.update(generated_at=dt.datetime.now().isoformat(timespec="seconds"),
                   index=ctx["index_meta"], step_seconds={**summary.get("step_seconds", {}), **timings})
    if not args.index_only:
        summary.update(
            staging_rows=ctx["staging_rows"], tgt_rows=ctx["tgt_rows"],
            tables_passed=ctx["recon"]["tables_passed"], tables_total=ctx["recon"]["tables_total"],
            findings=len(ctx["recon"]["findings"]),
            pii_masked_in_migration=ctx["migration_mask"], pii_masked_in_documents=ctx["doc_mask"],
            data_source="Olist Brazilian E-Commerce Public Dataset (Kaggle, CC BY-NC-SA 4.0)")
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\nPipeline complete. Start the app with:  streamlit run app/ui.py")


if __name__ == "__main__":
    main()
