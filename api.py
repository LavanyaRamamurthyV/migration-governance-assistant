"""Thin HTTP wrapper around the same workflow.   Run:  uvicorn api:app --reload
Then open http://127.0.0.1:8000/docs to try it."""
from fastapi import FastAPI
from pydantic import BaseModel

from app import graph

app = FastAPI(title="Migration & Governance Assistant API")


class AskRequest(BaseModel):
    question: str
    provider: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(body: AskRequest):
    s = graph.run_query(body.question, body.provider)
    return {"status": s["status"], "answer": s["answer"], "reason": s.get("reason", ""),
            "sources": [{"tag": x["tag"], "file": x["file"], "section": x["section"]} for x in s.get("sources", [])],
            "relevance": s.get("relevance"), "latency_ms": s["latency_ms"], "trace": s.get("trace", [])}
