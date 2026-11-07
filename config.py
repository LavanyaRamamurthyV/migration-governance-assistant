"""Central settings.

Every governance threshold lives here, so the code and the written policy
(docs/authored/data_governance_policy.md) can never disagree.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# ---- folders ---------------------------------------------------------------
RAW_DIR = Path(os.getenv("RAW_DIR", ROOT / "data" / "raw"))   # Olist CSVs go here
STORAGE = ROOT / "storage"                                    # rebuilt each run, not committed
RESULTS = ROOT / "results"                                    # small JSON summaries, committed
LOGS = ROOT / "logs"                                          # query log, not committed
DOCS_AUTHORED = ROOT / "docs" / "authored"                    # policy + runbook (human written)
DOCS_INDEXED = ROOT / "docs" / "indexed"                      # masked docs that get embedded
DOCS_UNMASKED = STORAGE / "docs_unmasked"                     # generated docs before masking

LEGACY_DB = STORAGE / "legacy_staging.db"    # stand-in for the legacy (Teradata-style) side
HUB_DB = STORAGE / "data_hub.db"             # stand-in for the Data Hub
CHROMA_DIR = STORAGE / "chroma"
CHUNKS_FILE = STORAGE / "chunks.json"
INDEX_META = STORAGE / "index_meta.json"
LSA_FILE = STORAGE / "lsa_model.pkl"
QUERY_LOG = LOGS / "queries.jsonl"

# ---- policy P-05: migration reconciliation thresholds -----------------------
AMOUNT_TOLERANCE_PCT = 0.01        # money totals must match within 0.01 %
NULL_RATE_TOLERANCE_PP = 0.5       # null-rate drift allowed, in percentage points

# ---- policy P-02: PII handling ----------------------------------------------
PII_SALT = os.getenv("PII_SALT", "demo-salt-change-me")

# ---- RAG settings ------------------------------------------------------------
CHUNK_SIZE = 1000          # characters
CHUNK_OVERLAP = 150
TOP_K = 4                  # passages sent to the LLM
VECTOR_CANDIDATES = 20     # how many nearest vectors Chroma returns before blending
W_VECTOR = 0.6             # hybrid blend: 60 % meaning ...
W_KEYWORD = 0.4            # ... 40 % exact words
LSA_WEIGHTS = (0.2, 0.8)   # offline fallback vectors are weaker, so lean on exact words
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "auto")   # auto | chroma-default | lsa


def default_provider() -> str:
    """Pick the LLM provider: explicit setting, else Gemini if a key exists, else no-LLM mode."""
    explicit = os.getenv("LLM_PROVIDER", "").strip().lower()
    if explicit:
        return explicit
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    return "extractive"
