"""Run:  python -m pytest -q
Tests that need the search index are skipped until you run the pipeline."""
import pytest

import config
from app import graph, llm
from pipeline.mask import mask_text

needs_index = pytest.mark.skipif(not config.INDEX_META.exists(), reason="build the index first")


def test_mask_email_phone_ids():
    text = "mail maria.silva@example.com phone (11) 98765-4321 cpf 123.456.789-09 id " + "a" * 32
    masked, counts = mask_text(text)
    assert "maria.silva@example.com" not in masked and "m***@example.com" in masked
    assert "98765-4321" not in masked and "123.456.789-09" not in masked and "a" * 32 not in masked
    assert counts["email"] == 1 and counts["phone"] == 1 and counts["national_id"] == 1 and counts["identifier"] == 1


def test_amounts_and_years_are_not_masked():
    text = "Rows migrated: 99,441. Period 2016-2018. Total 13591643.70 BRL."
    assert mask_text(text)[0] == text


def test_gemini_picks_newest_full_flash_first():
    class M:
        def __init__(self, name): self.name, self.supported_actions = name, ["generateContent"]
    class Client:
        class models:
            @staticmethod
            def list():
                return [M("models/gemini-2.5-flash"), M("models/gemini-3.6-flash"), M("models/gemini-3.8-flash-lite"),
                        M("models/gemini-3.8-flash-preview-05"), M("models/gemini-3.6-flash-image"), M("models/text-embedding-004")]
    assert llm._gemini_candidates(Client)[0] == "gemini-3.6-flash"


@needs_index
def test_offtopic_question_is_refused_without_calling_an_llm():
    s = graph.run_query("What is the capital of France?", "extractive", log=False)
    assert s["status"] == "refused" and any(t["step"] == "3. Refuse" for t in s["trace"])


@needs_index
def test_onTopic_question_is_answered_with_citation():
    s = graph.run_query("Where does customer_zip_prefix come from?", "extractive", log=False)
    assert s["status"] == "answered" and s["sources"]
    assert any("MAP-003" in x["section"] for x in s["chunks"])


@needs_index
@pytest.mark.parametrize("reply,status,n_sources", [
    ("NOT_FOUND", "refused", 0),
    ("It comes from the legacy file but I cite nothing.", "refused", 0),
    ("Per the mapping [S1, S2] and policy [S3].", "answered", 3),
])
def test_citation_verification(monkeypatch, reply, status, n_sources):
    monkeypatch.setattr(llm, "generate", lambda q, c, p: dict(text=reply, model="stub", in_tokens=1, out_tokens=1))
    s = graph.run_query("Where does customer_zip_prefix come from?", "gemini", log=False)
    assert s["status"] == status and len(s["sources"]) == n_sources


@needs_index
def test_llm_failure_falls_back_to_best_passage(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    s = graph.run_query("Where does customer_zip_prefix come from?", "gemini", log=False)
    assert s["status"] == "answered" and "unavailable" in s["note"]


@needs_index
def test_api_endpoint():
    from fastapi.testclient import TestClient
    import api
    client = TestClient(api.app)
    assert client.get("/health").json() == {"status": "ok"}
    r = client.post("/ask", json={"question": "What is the decommissioning rule?", "provider": "extractive"}).json()
    assert r["status"] == "answered" and r["sources"]


# ---- data questions (SQL engine), tested with a stubbed LLM
def test_sql_checker_blocks_writes():
    from app import data_qa
    assert data_qa.check_sql("SELECT 1") is None
    assert data_qa.check_sql("DROP TABLE tgt_order")
    assert data_qa.check_sql("SELECT 1; DELETE FROM tgt_order")
    assert data_qa.check_sql("NO_QUERY")


def test_data_answer_runs_on_sample(monkeypatch):
    from app import data_qa, llm
    replies = iter(["SELECT COUNT(*) AS n FROM tgt_order", "There are some orders."])
    monkeypatch.setattr(llm, "complete", lambda prompt, provider, system: dict(text=next(replies), model="stub"))
    res = data_qa.answer("how many orders?", "gemini")
    assert res["status"] == "answered" and res["rows"][0][0] > 1000


def test_readonly_connection_rejects_write():
    import sqlite3, pytest
    from app import data_qa
    with pytest.raises(sqlite3.Error):
        data_qa.run_sql("INSERT INTO tgt_order VALUES (1)", data_qa.db_path()[0])
