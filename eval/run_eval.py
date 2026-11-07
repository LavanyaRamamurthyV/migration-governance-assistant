"""Measure the assistant instead of eyeballing it.

    python -m eval.run_eval                      # uses your default provider
    python -m eval.run_eval --provider extractive

For answerable questions we check: did retrieval find the right source, did the assistant
answer, and does the answer contain the expected fact. For unanswerable questions we check
that it refuses. scikit-learn then reports accuracy, precision, recall and F1 for the
decision "answer vs refuse".
"""
import argparse
import json

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

import config
from app import graph


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=None)
    args = ap.parse_args()
    provider = args.provider or config.default_provider()

    questions = json.loads((config.ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
    rows, y_true, y_pred = [], [], []
    for q in questions:
        s = graph.run_query(q["question"], provider, log=False)
        answered = s["status"] == "answered"
        found = [f"{c['file']} > {c['section']}" for c in s.get("chunks", [])]
        hit = any(exp in label for exp in q["expected_sources"] for label in found) if q["answerable"] else None
        kw = all(k in s["answer"].lower() for k in q["expected_keywords"]) if q["answerable"] else None
        correct = (answered and kw) if q["answerable"] else (not answered)
        rows.append(dict(question=q["question"], answerable=q["answerable"], answered=answered, retrieval_hit=hit,
                         keyword_hit=kw, correct=bool(correct), relevance=s.get("relevance"), latency_ms=s["latency_ms"]))
        y_true.append(int(q["answerable"]))
        y_pred.append(int(answered))
        print(f"{'OK  ' if correct else 'FAIL'} rel={s.get('relevance')!s:6} retr={'-' if hit is None else int(hit)} | {q['question']}")

    p, r, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    answerable = [x for x in rows if x["answerable"]]
    summary = dict(
        provider=provider, questions=len(rows),
        correct=sum(x["correct"] for x in rows), accuracy_overall=round(sum(x["correct"] for x in rows) / len(rows), 3),
        retrieval_hit_rate=round(float(np.mean([x["retrieval_hit"] for x in answerable])), 3),
        answer_vs_refuse_accuracy=round(float(accuracy_score(y_true, y_pred)), 3),
        precision=round(float(p), 3), recall=round(float(r), 3), f1=round(float(f1), 3),
        correct_refusals=sum(1 for x in rows if not x["answerable"] and not x["answered"]),
        unanswerable_total=sum(1 for x in rows if not x["answerable"]),
        confusion_matrix=confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
        mean_latency_ms=int(np.mean([x["latency_ms"] for x in rows])))
    print("\n" + json.dumps(summary, indent=2))
    config.RESULTS.mkdir(parents=True, exist_ok=True)
    (config.RESULTS / "eval_results.json").write_text(json.dumps(dict(summary=summary, rows=rows), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
