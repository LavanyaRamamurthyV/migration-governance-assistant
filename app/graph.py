"""The query workflow, orchestrated with LangGraph.

    retrieve -> relevance check --yes--> generate -> verify citation -> END
                      |
                      +----no----> refuse -> END

Each box is a small function ("node") that reads and updates a shared state dictionary.
LangGraph runs them in order and handles the yes/no branch.
"""
import json
import re
import time
from datetime import datetime
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

import config
from app import llm, retrieval


class QState(TypedDict, total=False):
    question: str
    provider: str
    chunks: list
    relevance: float
    coverage: float
    threshold: float
    relevant: bool
    answer: str
    model: str
    in_tokens: int
    out_tokens: int
    status: str          # "answered" or "refused"
    reason: str
    sources: list        # passages the answer actually cites
    note: str
    trace: list          # one row per workflow step, shown in the UI


def _trace(state, step, tool, t0, detail):
    rows = list(state.get("trace", []))
    rows.append(dict(step=step, tool=tool, ms=round((time.perf_counter() - t0) * 1000), detail=detail))
    return rows


# ---------------------------------------------------------------- nodes
def retrieve(state: QState):
    t0 = time.perf_counter()
    chunks = retrieval.retrieve(state["question"])
    top = chunks[0]
    detail = f"top {len(chunks)} passages; best: {top['file']} > {top['section'][:40]} (meaning {top['vec']}, keyword {top['kw']})"
    return {"chunks": chunks, "trace": _trace(state, "1. Retrieve", "Chroma + scikit-learn", t0, detail)}


def check_relevance(state: QState):
    t0 = time.perf_counter()
    relevance, coverage = retrieval.relevance(state["question"], state["chunks"])
    threshold = retrieval.get_store().threshold
    relevant = relevance >= threshold
    detail = f"relevance {relevance} vs threshold {threshold} (word coverage {coverage}) -> {'continue' if relevant else 'refuse'}"
    return {"relevance": relevance, "coverage": coverage, "threshold": threshold, "relevant": relevant,
            "trace": _trace(state, "2. Relevance check", "LangGraph + NumPy", t0, detail)}


def route(state: QState) -> str:
    return "generate" if state["relevant"] else "refuse"


def generate(state: QState):
    t0 = time.perf_counter()
    provider, note = state["provider"], ""
    try:
        out = llm.generate(state["question"], state["chunks"], provider)
    except llm.LlmError as exc:   # safety net: never leave the user with a blank screen
        note = f"The {provider} model was unavailable ({exc}). Showing the best passage instead."
        out = llm.extractive(state["chunks"])
        provider = "extractive"
    detail = f"{provider} / {out['model']}; tokens in {out['in_tokens']}, out {out['out_tokens']}"
    return {"answer": out["text"], "model": out["model"], "in_tokens": out["in_tokens"], "out_tokens": out["out_tokens"],
            "note": note, "trace": _trace(state, "3. Generate", f"{provider.capitalize()} API" if provider != "extractive" else "No LLM", t0, detail)}


def verify(state: QState):
    t0 = time.perf_counter()
    text = state["answer"].strip()
    chunks = state["chunks"]
    cited = sorted({int(n) for group in re.findall(r"\[([^\]]+)\]", text)
                    for n in re.findall(r"S(\d+)", group) if 1 <= int(n) <= len(chunks)})
    if text.upper().startswith("NOT_FOUND") or not text:
        update = dict(status="refused", reason="The retrieved passages do not contain the answer.",
                      answer="Not found in documents.", sources=[])
        detail = "model returned NOT_FOUND -> refused"
    elif not cited:
        update = dict(status="refused", reason="The answer had no verifiable citation (policy P-08).",
                      answer="Not found in documents.", sources=[])
        detail = "no valid [S#] citation -> refused"
    else:
        sources = [dict(tag=f"S{i}", **{k: chunks[i - 1][k] for k in ("file", "section", "text", "score")}) for i in cited]
        update = dict(status="answered", reason="", sources=sources)
        detail = f"citations verified: {', '.join('S' + str(i) for i in cited)}"
    update["trace"] = _trace(state, "4. Verify citation", "Python check", t0, detail)
    return update


def refuse(state: QState):
    t0 = time.perf_counter()
    return {"status": "refused", "answer": "Not found in documents.", "sources": [],
            "reason": f"The question does not look related to the indexed documents (relevance {state['relevance']} < {state['threshold']}).",
            "trace": _trace(state, "3. Refuse", "LangGraph branch", t0, "no LLM call made")}


# ---------------------------------------------------------------- graph
def build_graph():
    g = StateGraph(QState)
    g.add_node("retrieve", retrieve)
    g.add_node("check_relevance", check_relevance)
    g.add_node("generate", generate)
    g.add_node("verify", verify)
    g.add_node("refuse", refuse)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "check_relevance")
    g.add_conditional_edges("check_relevance", route, {"generate": "generate", "refuse": "refuse"})
    g.add_edge("generate", "verify")
    g.add_edge("verify", END)
    g.add_edge("refuse", END)
    return g.compile()


GRAPH = build_graph()


def _log(state):
    try:
        config.LOGS.mkdir(parents=True, exist_ok=True)
        row = dict(ts=datetime.now().isoformat(timespec="seconds"), question=state["question"],
                   provider=state["provider"], model=state.get("model", ""), status=state["status"],
                   reason=state.get("reason", ""), relevance=state.get("relevance"),
                   top_source=f"{state['chunks'][0]['file']} > {state['chunks'][0]['section']}" if state.get("chunks") else "",
                   latency_ms=state["latency_ms"], in_tokens=state.get("in_tokens", 0), out_tokens=state.get("out_tokens", 0))
        with open(config.QUERY_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass   # logging must never break an answer


def run_query(question: str, provider: str | None = None, log: bool = True) -> dict:
    """Run the whole workflow for one question and return the final state."""
    question = (question or "").strip()
    if not question:
        return dict(question="", status="refused", answer="Please type a question.", reason="Empty question.",
                    sources=[], chunks=[], trace=[], latency_ms=0, provider=provider or "")
    t0 = time.perf_counter()
    state = GRAPH.invoke({"question": question, "provider": provider or config.default_provider(), "trace": []})
    state["latency_ms"] = round((time.perf_counter() - t0) * 1000)
    if log:
        _log(state)
    return state


if __name__ == "__main__":
    import sys
    if "--mermaid" in sys.argv:   # draw the workflow straight from the code, so the picture cannot drift
        print(GRAPH.get_graph().draw_mermaid())
