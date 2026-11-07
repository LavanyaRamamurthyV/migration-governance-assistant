"""Data questions: the LLM writes ONE read-only SQL query over the migrated target tables, the code checks and
runs it, and the LLM words the result. Nothing is answered from the model's memory.

Safety (code, not trust): only a single SELECT is run; the database is opened read-only; sqlite's authorizer
blocks everything except reads; results are capped at 200 rows. PII columns never hold raw values (tokenized)."""
import re
import sqlite3
import time

import config
from app import llm
from pipeline.spec import TABLES

SAMPLE_DB = config.ROOT / "data" / "target_sample.db"


def db_path():
    """Full migrated database if the pipeline has been run here, else the committed real-data sample."""
    if config.TARGET_DB.exists():
        return config.TARGET_DB, "full"
    return SAMPLE_DB, "sample"


def schema_text():
    lines = []
    for t in TABLES:
        cols = ", ".join(f"{c['tgt']} {c['ttype']}" + (" [PII-protected]" if c["pii"] != "N" else "") for c in t["columns"])
        lines.append(f"{t['tgt_table']}({cols})  -- from {t['source_file']}; key: {', '.join(t['key'])}")
    lines.append("Joins: tgt_order.customer_key=tgt_customer.customer_key; tgt_order_item/tgt_payment/tgt_review.order_id=tgt_order.order_id; "
                 "tgt_order_item.product_id=tgt_product.product_id; tgt_order_item.seller_id=tgt_seller.seller_id.")
    return "\n".join(lines)


SQL_SYSTEM = ("You write SQLite queries for a retail order database. Reply with ONE read-only SELECT statement and nothing else "
              "(no explanation, no markdown fences). Use only the tables and columns listed. Always add LIMIT 100 unless the "
              "query is an aggregate returning one row. If the question cannot be answered from these tables, reply exactly: NO_QUERY")
ANSWER_SYSTEM = ("You explain query results to a business reader in 1-3 plain sentences. Use ONLY the numbers in the result. "
                 "If the result is empty, say no matching rows were found. Do not mention SQL unless asked.")


def _clean_sql(text):
    text = re.sub(r"```(?:sql)?", "", text, flags=re.I).strip().rstrip(";").strip()
    return text


def check_sql(sql):
    if sql.upper() == "NO_QUERY":
        return "The question cannot be answered from the migrated tables."
    if ";" in sql:
        return "Only a single statement is allowed."
    if not re.match(r"^\s*(select|with)\b", sql, flags=re.I):
        return "Only SELECT queries are allowed."
    if re.search(r"\b(insert|update|delete|drop|alter|create|attach|pragma|replace|vacuum)\b", sql, flags=re.I):
        return "Query contains a blocked keyword."
    return None


def run_sql(sql, path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.set_authorizer(lambda action, *a: sqlite3.SQLITE_OK if action in (21, 20, 31, 33) else sqlite3.SQLITE_DENY)
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(200)
    finally:
        con.close()
    return cols, rows


def answer(question, provider):
    t0 = time.perf_counter()
    path, mode = db_path()
    out = dict(question=question, mode=mode, trace=[], in_tokens=0, out_tokens=0, provider=provider)
    r1 = llm.complete(f"Tables:\n{schema_text()}\n\nQuestion: {question}", provider, SQL_SYSTEM)
    sql = _clean_sql(r1["text"])
    out.update(sql=sql, model=r1.get("model", ""))
    out["in_tokens"] += r1.get("in_tokens", 0); out["out_tokens"] += r1.get("out_tokens", 0)
    out["trace"].append(dict(step="1. Write SQL", tool=f"{provider} LLM", detail=sql[:160]))
    problem = check_sql(sql)
    if problem:
        out.update(status="refused", reason=problem)
        return out
    try:
        cols, rows = run_sql(sql, path)
    except sqlite3.Error as exc:
        out.update(status="refused", reason=f"The generated query failed ({exc}). Try rephrasing the question.")
        return out
    out["trace"].append(dict(step="2. Check and run", tool="Python + SQLite (read-only)", detail=f"{len(rows)} rows from {'full migrated database' if mode == 'full' else 'real-data sample (5,000 orders)'}"))
    out.update(cols=cols, rows=rows)
    preview = "\n".join(" | ".join(map(str, r)) for r in rows[:30])
    r2 = llm.complete(f"Question: {question}\nColumns: {', '.join(cols)}\nRows (max 30 shown, {len(rows)} total):\n{preview}", provider, ANSWER_SYSTEM)
    out["in_tokens"] += r2.get("in_tokens", 0); out["out_tokens"] += r2.get("out_tokens", 0)
    out["trace"].append(dict(step="3. Explain result", tool=f"{provider} LLM", detail="plain-language answer"))
    out.update(status="answered", answer=r2["text"], latency_ms=round((time.perf_counter() - t0) * 1000))
    return out
