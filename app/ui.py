"""Streamlit demo UI.   Run:  streamlit run app/ui.py"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # so `import config` works from app/

import pandas as pd
import streamlit as st

import config
from app import graph, llm, retrieval
from pipeline.mask import mask_text

st.set_page_config(page_title="Migration & Governance Assistant", layout="wide")

EXAMPLES = [
    "Where does customer_zip_prefix come from?",
    "What changed in layout v2 for order_status?",
    "What is blocking the Customer Experience cutover?",
    "What reconciliation thresholds apply to a migration?",
    "How is customer_unique_id transformed during migration?",
    "Who is the CEO of Olist?",
]


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
    if summary.get("hub_rows"):
        st.metric("Rows migrated to the hub", f"{sum(summary['hub_rows'].values()):,}")
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
st.title("Migration & Governance Assistant")
st.caption("Ask questions about a legacy-to-Data-Hub migration. Answers come only from the indexed documents, with citations. "
           "Data: Olist public dataset (Kaggle, CC BY-NC-SA 4.0).")
tab_ask, tab_mig, tab_eval, tab_use = st.tabs(["Ask", "Migration results", "Evaluation", "Usage"])


def pick(question):
    st.session_state["question"] = question
    st.session_state["go"] = True


with tab_ask:
    cols = st.columns(3)
    for i, ex in enumerate(EXAMPLES):
        cols[i % 3].button(ex, key=f"ex{i}", on_click=pick, args=(ex,))
    question = st.text_input("Your question", key="question")
    go = st.button("Ask", type="primary") or st.session_state.pop("go", False)

    if go and question.strip():
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
        if state.get("note"):
            st.info(state["note"])

        if state.get("sources"):
            st.markdown("**Sources**")
            for src in state["sources"]:
                with st.expander(f"{src['tag']}: {src['file']} > {src['section']}  (score {src['score']})"):
                    st.text(src["text"])

        st.markdown("**Workflow trace**")
        st.dataframe(pd.DataFrame(state["trace"]).rename(columns={"step": "Step", "tool": "Tool", "ms": "ms", "detail": "What happened"}),
                     hide_index=True)
        st.caption(f"Total {state['latency_ms']} ms. Tokens in {state.get('in_tokens', 0)}, out {state.get('out_tokens', 0)}. "
                   f"Model: {state.get('model', '-')}")

with tab_mig:
    if not recon:
        st.info("Run the pipeline first:  python -m pipeline.run_pipeline")
    else:
        st.subheader("Reconciliation: legacy staging vs Data Hub")
        rows = []
        for t in recon["tables"]:
            rows.append({"Hub table": t["table"], "Source rows": t["source_rows"], "Hub rows": t["hub_rows"],
                         "Rows match": "Yes" if t["row_match"] else "NO",
                         "Amount check": "; ".join(f"{a['column']} diff {a['diff_pct']}%" for a in t["amount_checks"]) or "n/a",
                         "Max null drift (pp)": t["null_check"]["max_drift_pp"],
                         "Keys preserved": "n/a" if not t["key_check"] else ("Yes" if t["key_check"]["preserved"] else "NO"),
                         "Status": t["status"]})
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        th = recon["thresholds"]
        st.caption(f"Policy P-05 thresholds: row counts exact, amounts within {th['amount_pct']}%, null drift within {th['null_rate_pp']} pp.")
        st.subheader("Data-quality findings (found in the source data)")
        st.dataframe(pd.DataFrame([{"ID": f["id"], "Finding": f["title"], "Count": f["count"], "Teams": ", ".join(f["teams"]),
                                    "Blocks cutover": "Yes" if f["blocking"] else "No"} for f in recon["findings"]]), hide_index=True)
        st.subheader("Referential integrity")
        st.dataframe(pd.DataFrame(recon["referential"]).rename(columns={"check": "Check", "orphans": "Orphan rows"}), hide_index=True)

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
