"""Streamlit demo UI.   Run:  streamlit run app/ui.py"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # so `import config` works from app/

import pandas as pd
import streamlit as st

import config
import re

from app import data_qa, graph, llm, retrieval
from pipeline.mask import mask_text
from pipeline.spec import TABLES

st.set_page_config(page_title="Migration & Governance Assistant", layout="wide")

DOC_EXAMPLES = [
    "Where does customer_zip_prefix come from?",
    "What changed in layout v2 for order_status?",
    "What is blocking the Customer Experience cutover?",
    "What reconciliation thresholds apply to a migration?",
]
DATA_EXAMPLES = [
    "How many orders were delivered?",
    "Top 5 product categories by revenue",
    "Average review score by customer state",
    "Which payment type is used most?",
]
DATA_WORDS = re.compile(r"\b(how many|count|total|average|avg|sum|top \d+|top|most|least|highest|lowest|revenue|sales|percent|percentage|number of|per state|by state|by month)\b", re.I)
DOC_WORDS = re.compile(r"(layout|mapping|policy|runbook|threshold|cutover|reconcil|finding|pii|migrat|sunset|decommission|transform|owner|consumer|feed|phase|risk|blocking|where does|come from)", re.I)


def route(question, mode):
    if mode == "Documents":
        return "docs"
    if mode == "Data":
        return "data"
    return "data" if DATA_WORDS.search(question) and not DOC_WORDS.search(question) else "docs"



def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


summary = read_json(config.RESULTS / "run_summary.json") or {}
recon = read_json(config.RESULTS / "reconciliation.json")

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Settings")
    default = config.default_provider()
    provider = st.selectbox("LLM provider (model-agnostic)", llm.PROVIDERS,
                            index=llm.PROVIDERS.index(default) if default in llm.PROVIDERS else 0)
    key_env = {"gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"), "claude": ("ANTHROPIC_API_KEY",)}.get(provider)
    if key_env:
        st.caption("API key: " + ("found" if any(os.getenv(k) for k in key_env) else "missing (add it to .env)"))
    elif provider == "extractive":
        st.caption("No LLM: shows the best passages only.")

    st.divider()
    st.subheader("Last pipeline run")
    if summary.get("tgt_rows"):
        st.metric("Rows migrated to the target", f"{sum(summary['tgt_rows'].values()):,}")
        st.metric("Tables reconciled", f"{summary['tables_passed']} of {summary['tables_total']} PASS")
        st.metric("Data-quality findings", summary["findings"])
        masked = sum(summary.get("pii_masked_in_migration", {}).values()) + sum(summary.get("pii_masked_in_documents", {}).values())
        st.metric("PII items masked", masked)
    idx = summary.get("index", {})
    if idx:
        st.caption(f"Index: {idx.get('chunks')} chunks, embeddings: {idx.get('embedding_backend')}, "
                   f"relevance threshold {idx.get('relevance_threshold')}")

    with st.expander("Try the PII masker"):
        sample = st.text_area("Text", "Call me on (11) 98765-4321 or write to maria.silva@example.com. CPF 123.456.789-09",
                              height=90)
        st.code(mask_text(sample)[0], language=None)

# ------------------------------------------------------------------ tabs
TARGET = "Target Platform"
st.title("Migration & Governance Assistant")
st.caption("Moves legacy data to the Target Platform, proves it arrived intact, protects personal data, and answers questions "
           "about both the migration (from documents, with citations) and the data (from the migrated tables). "
           "Data: Olist public dataset (Kaggle, CC BY-NC-SA 4.0).")
tab_ask, tab_mig, tab_eval, tab_use, tab_how = st.tabs(["Ask", "Migration results", "Evaluation", "Usage", "How it works"])


def pick(question):
    st.session_state["question"] = question
    st.session_state["go"] = True


def show_trace(state):
    st.markdown("**Workflow trace**")
    st.dataframe(pd.DataFrame(state["trace"]).rename(columns={"step": "Step", "tool": "Tool", "ms": "ms", "detail": "What happened"}),
                 hide_index=True)


with tab_ask:
    mode = st.radio("Question type", ["Auto", "Documents", "Data"], horizontal=True,
                    help="Documents = questions about the migration (mapping, layout, policy, findings). "
                         "Data = questions about the records themselves (counts, totals, rankings). Auto picks for you.")
    c1, c2 = st.columns(2)
    c1.markdown("**Migration questions** (answered from documents, with citations)")
    for i, ex in enumerate(DOC_EXAMPLES):
        c1.button(ex, key=f"d{i}", on_click=pick, args=(ex,))
    c2.markdown("**Data questions** (answered by a checked SQL query on the migrated tables)")
    for i, ex in enumerate(DATA_EXAMPLES):
        c2.button(ex, key=f"q{i}", on_click=pick, args=(ex,))
    question = st.text_input("Your question", key="question")
    go = st.button("Ask", type="primary") or st.session_state.pop("go", False)

    if go and question.strip():
        kind = route(question, mode)
        if kind == "data":
            try:
                with st.spinner("Writing and running the query..."):
                    res = data_qa.answer(question, provider)
            except llm.LlmError as exc:
                st.error(str(exc))
                st.stop()
            st.caption("Answered from the " + ("full migrated database" if res["mode"] == "full" else
                       "real-data sample (5,000 orders, all links intact; run the full pipeline for all 99,441)"))
            if res["status"] == "answered":
                st.success("Answered from the data")
                st.markdown(res["answer"])
                st.markdown("**SQL that was run**")
                st.code(res["sql"], language="sql")
                st.dataframe(pd.DataFrame(res["rows"], columns=res["cols"]), hide_index=True)
            else:
                st.warning("Could not answer from the data")
                st.write(res.get("reason", ""))
                st.code(res.get("sql", ""), language="sql")
            show_trace(res)
            st.caption(f"Tokens in {res['in_tokens']}, out {res['out_tokens']}. Model: {res.get('model', '-')}")
        else:
            try:
                retrieval.get_store()
            except FileNotFoundError as exc:
                st.error(str(exc))
                st.stop()
            with st.spinner("Running the workflow..."):
                state = graph.run_query(question, provider)
            if state["status"] == "answered":
                st.success("Answered, with verified citations")
                st.markdown(state["answer"])
            else:
                st.warning("Not found in documents")
                st.write(state.get("reason", ""))
                if mode == "Auto":
                    st.caption("If this is a question about the records themselves, switch Question type to Data.")
            if state.get("note"):
                st.info(state["note"])
            if state.get("sources"):
                st.markdown("**Sources**")
                for src in state["sources"]:
                    with st.expander(f"{src['tag']}: {src['file']} > {src['section']}  (score {src['score']})"):
                        st.text(src["text"])
            show_trace(state)
            st.caption(f"Total {state['latency_ms']} ms. Tokens in {state.get('in_tokens', 0)}, out {state.get('out_tokens', 0)}. "
                       f"Model: {state.get('model', '-')}")

with tab_mig:
    if not recon:
        st.info("Run the pipeline first:  python -m pipeline.run_pipeline")
    else:
        st.markdown(f"**What this tab shows:** the legacy data was copied into the {TARGET}, then every table was checked against its "
                    f"source. All checks below were computed from the real data, not typed in.")
        st.subheader(f"1. Reconciliation: did everything arrive? (legacy staging vs {TARGET})")
        st.caption("Each row is one table. Source rows = rows in the legacy staging copy. Target rows = rows in the Target Platform. "
                   "A table PASSES only if row counts match exactly, money totals agree within the tolerance, "
                   "no column became noticeably emptier, and keys stayed unique.")
        rows = []
        for t in recon["tables"]:
            rows.append({"Target table": t["table"], "Source file": t["source_file"], "Source rows": t["source_rows"],
                         "Target rows": t["tgt_rows"], "Rows match": "Yes" if t["row_match"] else "NO",
                         "Money totals": "; ".join(f"{a['column']} diff {a['diff_pct']}%" for a in t["amount_checks"]) or "n/a",
                         "Max empty-value drift (pp)": t["null_check"]["max_drift_pp"],
                         "Keys preserved": "n/a" if not t["key_check"] else ("Yes" if t["key_check"]["preserved"] else "NO"),
                         "Status": t["status"]})
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        th = recon["thresholds"]
        st.caption(f"Policy P-05 thresholds: row counts exact, money within {th['amount_pct']}%, empty-value drift within {th['null_rate_pp']} percentage points. "
                   "pp = percentage points. Column-by-column detail is in the 'Tables and columns' section of the How it works tab.")
        st.subheader("2. Data-quality findings (problems that already existed in the legacy data)")
        st.caption("The migration does not hide these. They are kept, counted, and assigned to the teams that consume the data. "
                   "'Blocks cutover' means the consuming team cannot switch to the Target Platform until it is resolved.")
        st.dataframe(pd.DataFrame([{"ID": f["id"], "Finding": f["title"], "Count": f["count"], "Teams": ", ".join(f["teams"]),
                                    "Blocks cutover": "Yes" if f["blocking"] else "No"} for f in recon["findings"]]), hide_index=True)
        st.subheader("3. Referential integrity (do the links between tables still work?)")
        st.markdown("Tables point to each other with ids. For example, every row in the order-item table carries an `order_id`, "
                    "which must exist in the order table. A row whose id has no match is an **orphan**. "
                    "**0 orphans on every link means no record lost its parent during migration.**")
        ri = pd.DataFrame(recon["referential"]).rename(columns={"check": "Link (child.column -> parent table)", "orphans": "Orphan rows"})
        ri["Result"] = ri["Orphan rows"].map(lambda n: "OK" if n == 0 else "PROBLEM")
        st.dataframe(ri, hide_index=True)

with tab_eval:
    ev = read_json(config.RESULTS / "eval_results.json")
    if not ev:
        st.info("Run:  python -m eval.run_eval")
    else:
        s = ev["summary"]
        st.caption(f"Provider used for this evaluation: {s['provider']}")
        c = st.columns(4)
        c[0].metric("Correct", f"{s['correct']} of {s['questions']}")
        c[1].metric("Retrieval hit rate", f"{s['retrieval_hit_rate']:.0%}")
        c[2].metric("Answer vs refuse accuracy", f"{s['answer_vs_refuse_accuracy']:.0%}")
        c[3].metric("Correct refusals", f"{s['correct_refusals']} of {s['unanswerable_total']}")
        st.dataframe(pd.DataFrame(ev["rows"]), hide_index=True)

with tab_use:
    try:
        log = pd.read_json(config.QUERY_LOG, lines=True)
    except (ValueError, OSError):
        log = pd.DataFrame()
    if log.empty:
        st.info("No questions asked yet.")
    else:
        c = st.columns(4)
        c[0].metric("Questions", len(log))
        c[1].metric("Refused", f"{(log['status'] == 'refused').mean():.0%}")
        c[2].metric("Average latency", f"{int(log['latency_ms'].mean())} ms")
        c[3].metric("Tokens used", int(log["in_tokens"].sum() + log["out_tokens"].sum()))
        st.bar_chart(log["latency_ms"].tail(20))
        st.dataframe(log.tail(20).iloc[::-1][["ts", "question", "provider", "status", "latency_ms"]], hide_index=True)


# ------------------------------------------------------------------ How it works (the presentation tab)
def mermaid(path, height):
    code = (config.ROOT / "docs" / "diagrams" / path).read_text(encoding="utf-8")
    st.iframe(
        f'<!doctype html><html><body style="margin:0"><div class="mermaid">{code}</div><script type="module">import mermaid from '
        f'"https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.esm.min.mjs";mermaid.initialize({{startOnLoad:true,theme:"neutral"}});</script></body></html>',
        height=height)


with tab_how:
    rows_total = sum(summary.get("tgt_rows", {}).values()) or 1550851
    st.header("What this tool is for")
    st.markdown(
        "Large organisations are retiring old data platforms and moving their data to a new one. That move is risky: records can be "
        "lost, changed, or exposed, and the people who depend on the data need to know what changed. This tool does the move on a real "
        "dataset, **proves** it was done correctly, **protects** personal data, **documents** everything, and lets anyone **ask questions** "
        "about the migration and about the data.")
    st.table(pd.DataFrame([
        {"Purpose": "Migrate", "What it does": "Copies and cleans 8 legacy tables into the Target Platform with typed, standardised columns", "Where to see it": "Tables and columns (below)"},
        {"Purpose": "Reconcile", "What it does": "Checks row counts, money totals, empty values, keys and links table by table", "Where to see it": "Migration results tab"},
        {"Purpose": "Protect", "What it does": "Replaces personal identifiers with tokens and masks personal text", "Where to see it": "Personal data (below)"},
        {"Purpose": "Document", "What it does": "Generates the mapping, layout v2, sunset plan and reconciliation report from the real schema and results", "Where to see it": "Ask tab (citations)"},
        {"Purpose": "Answer", "What it does": "Migration questions from documents with citations; data questions from the migrated tables via checked SQL", "Where to see it": "Ask tab"},
    ]).set_index("Purpose"))

    st.header("Where the data comes from and where it goes")
    st.markdown(
        "**From:** the legacy platform, shown here as *Teradata (stand-in)*: 9 CSV files from the public Olist dataset. "
        "**To:** the **Target Platform**, the new system the data is moving to. In this demo it is a SQLite database standing in for it. "
        "The data passes through a *staging* copy first so the original is never altered.")
    st.table(pd.DataFrame([
        {"Stage": "1. Legacy source", "What it is": "9 CSV files exactly as exported (Olist)", "Where": "data/raw/ (not in the repo)", "Contents": "Everything as text, original column names"},
        {"Stage": "2. Legacy staging", "What it is": "Untouched copy of the legacy data in a database", "Where": "storage/legacy_staging.db", "Contents": "8 stg_ tables, the reference for reconciliation"},
        {"Stage": "3. Target Platform", "What it is": "Cleaned, typed, protected data in the new layout", "Where": "storage/target_platform.db", "Contents": f"8 tgt_ tables, {rows_total:,} rows"},
    ]).set_index("Stage"))

    st.header("How it runs: the two workflows")
    st.markdown("Colors: green = data processing, amber = governance and checks, purple = AI, grey = user interface. "
                "**Bold** names are the tools. The **dotted box** is the orchestration: the part that decides what runs, in what order.")
    st.subheader("Workflow 1: migration pipeline (runs in batch, about 15 seconds)")
    mermaid("ingestion.mmd", 620)
    st.table(pd.DataFrame([
        {"Step": "1. Load", "Tool": "pandas + SQLite", "What happens": "Reads the 9 legacy CSVs and stores them unchanged in the staging database", "Output": "stg_ tables"},
        {"Step": "2. Migrate", "Tool": "pandas + SQL", "What happens": "Applies the mapping rules: types, trimming, case, dates, rounding; tokenizes customer ids", "Output": "tgt_ tables"},
        {"Step": "3. Reconcile", "Tool": "pandas + NumPy + SQL", "What happens": "Compares every target table with its staging source and runs data-quality and link checks", "Output": "reconciliation.json"},
        {"Step": "4. Generate docs", "Tool": "pandas + Python", "What happens": "Writes mapping, layout v2, sunset plan and reconciliation report from the real schema and results", "Output": "4 documents"},
        {"Step": "5. Mask PII", "Tool": "Python regex", "What happens": "Masks emails, phones, national ids and long identifiers in documents", "Output": "6 masked documents"},
        {"Step": "6. Chunk", "Tool": "LangChain text splitter", "What happens": "Cuts documents into passages along their headings", "Output": "133 chunks"},
        {"Step": "7. Embed and store", "Tool": "Chroma + scikit-learn", "What happens": "Turns passages into vectors so they can be searched by meaning", "Output": "search index"},
    ]).set_index("Step"))
    st.subheader("Workflow 2: answering a migration question (every question)")
    mermaid("query.mmd", 700)
    st.table(pd.DataFrame([
        {"Step": "1. Retrieve", "Tool": "Chroma + scikit-learn", "What happens": "Hybrid search: meaning (vectors) blended with exact keywords (TF-IDF), 60/40, blended by NumPy"},
        {"Step": "2. Relevance check", "Tool": "LangGraph + NumPy", "What happens": "If the best passages do not match the question well enough, stop here. No LLM call is made"},
        {"Step": "3. Generate", "Tool": "Gemini / Claude / Ollama", "What happens": "The LLM answers using only the retrieved passages and must cite them as [S1], [S2]"},
        {"Step": "4. Verify", "Tool": "Python", "What happens": "An answer with no valid citation is refused"},
        {"Step": "5-6. Show and log", "Tool": "Streamlit, JSON log", "What happens": "Shows answer and sources; records time, tokens and outcome (Usage tab)"},
    ]).set_index("Step"))
    st.markdown("**Data questions** take a different path: the LLM writes one SQL query from the table list, Python checks it is a single "
                "read-only SELECT, runs it on the migrated tables, and the LLM words the result. The SQL and the rows are always shown so "
                "the answer can be checked.")

    st.header("Tables and columns: what went where")
    st.markdown("Pick a table to see, for each column, where it came from, what it became, and the rule that was applied.")
    names = {f"{t['tgt_table']}  (from {t['source_file']})": t for t in TABLES}
    t = names[st.selectbox("Target table", list(names))]
    m1, m2, m3 = st.columns(3)
    m1.metric("Columns", len(t["columns"]))
    m2.metric("Key", ", ".join(t["key"]))
    m3.metric("Consumers", ", ".join(t["consumers"]))
    st.dataframe(pd.DataFrame([{"Legacy column": c["src"], "Target column": c["tgt"], "Type": c["ttype"], "Rule applied": c["rule"],
                                "Personal data": {"Y": "Yes", "Quasi": "Indirect", "N": "No"}[c["pii"]]} for c in t["columns"]]),
                 hide_index=True)
    st.caption("Personal data: Yes = identifies a person or links to one. Indirect = could help identify someone when combined with other data.")

    st.header("How the tables link (and why that is checked)")
    st.markdown("Orders are the hub of the model: a customer places an **order**, which has **items** (each from a product and a seller), "
                "**payments** and **reviews**. Each link is an id that must exist in the parent table.")
    st.table(pd.DataFrame([
        {"Child table": "tgt_order", "Column": "customer_key", "Parent table": "tgt_customer", "Meaning": "Every order belongs to a known customer"},
        {"Child table": "tgt_order_item", "Column": "order_id", "Parent table": "tgt_order", "Meaning": "Every item belongs to an order"},
        {"Child table": "tgt_order_item", "Column": "product_id", "Parent table": "tgt_product", "Meaning": "Every item is a known product"},
        {"Child table": "tgt_order_item", "Column": "seller_id", "Parent table": "tgt_seller", "Meaning": "Every item has a known seller"},
        {"Child table": "tgt_payment", "Column": "order_id", "Parent table": "tgt_order", "Meaning": "Every payment belongs to an order"},
        {"Child table": "tgt_review", "Column": "order_id", "Parent table": "tgt_order", "Meaning": "Every review belongs to an order"},
    ]).set_index("Child table"))
    st.caption("Referential integrity = every link above still finds its parent. Results are on the Migration results tab (0 orphans on all 6).")

    st.header("Personal data (PII): what is protected and how")
    st.markdown("PII = personally identifiable information. Three techniques are used, depending on the field:")
    pii_rows = [{"Table": tt["tgt_table"], "Column": c["tgt"], "Sensitivity": "Direct" if c["pii"] == "Y" else "Indirect",
                 "Protection": c["rule"]} for tt in TABLES for c in tt["columns"] if c["pii"] != "N"]
    st.dataframe(pd.DataFrame(pii_rows), hide_index=True)
    mig = summary.get("pii_masked_in_migration", {})
    doc = summary.get("pii_masked_in_documents", {})
    st.table(pd.DataFrame([
        {"Technique": "Tokenization", "Applied to": "customer_unique_id (the person identifier)", "Result in this run": "96,096 distinct people became 96,096 distinct tokens, 0 collisions. The raw id never reaches the Target Platform"},
        {"Technique": "Masking in free text", "Applied to": "Customer review comments during migration", "Result in this run": f"{sum(mig.values())} masked ({', '.join(f'{v} {k}' for k, v in mig.items()) or 'none'})"},
        {"Technique": "Masking in documents", "Applied to": "Generated and authored documents before they are indexed for search", "Result in this run": f"{sum(doc.values())} masked ({', '.join(f'{v} {k}' for k, v in doc.items()) or 'none'}: long hex identifiers)"},
        {"Technique": "Kept coarse", "Applied to": "ZIP code prefix (5 digits), city, state", "Result in this run": "Not masked: kept at prefix level only, no street address exists in the data"},
    ]).set_index("Technique"))
    st.caption("Masking is pattern based (emails, phones, national ids, long identifiers). It is not exhaustive and needs a human spot check. "
               "Try it live in the sidebar: 'Try the PII masker'.")

    st.header("Glossary")
    st.table(pd.DataFrame([
        {"Term": "Target Platform", "Meaning": "The new system the data is migrated to (a SQLite stand-in in this demo)"},
        {"Term": "Legacy staging", "Meaning": "An untouched copy of the old data, used as the reference to prove nothing was lost"},
        {"Term": "Reconciliation", "Meaning": "Comparing old and new, table by table, against agreed thresholds"},
        {"Term": "Orphan", "Meaning": "A row whose link points to a parent row that does not exist"},
        {"Term": "RAG", "Meaning": "Retrieval-Augmented Generation: find the relevant passages first, then let an LLM answer using only those"},
        {"Term": "Embedding / vector", "Meaning": "Numbers that represent the meaning of a passage so similar passages can be found"},
        {"Term": "Orchestration", "Meaning": "The control layer deciding which step runs next (a Python script for the pipeline, LangGraph for questions)"},
        {"Term": "Cutover", "Meaning": "The moment a consuming team switches from the legacy platform to the Target Platform"},
    ]).set_index("Term"))
