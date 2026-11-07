"""Quick self-check.   Run:  python check_setup.py
Tells you what works, what is missing, and (if a key is set) makes one tiny LLM call."""
import importlib
import os
import sys

import config

ok = True


def line(good, text):
    global ok
    ok = ok and good
    print(("  OK    " if good else "  FIX   ") + text)


print(f"Python {sys.version.split()[0]}")
for pkg in ["pandas", "numpy", "sklearn", "chromadb", "langgraph", "langchain_text_splitters", "streamlit", "dotenv", "snowballstemmer"]:
    try:
        importlib.import_module(pkg)
        line(True, f"package {pkg}")
    except ImportError:
        line(False, f"package {pkg} missing -> pip install -r requirements.txt")

line(config.INDEX_META.exists(), "search index built" if config.INDEX_META.exists()
     else "no index yet -> python -m pipeline.run_pipeline --index-only")
raw = sorted(p.name for p in config.RAW_DIR.glob("olist_*.csv")) if config.RAW_DIR.exists() else []
print(f"  INFO  Olist CSVs found in {config.RAW_DIR}: {len(raw)} of 8 (only needed to re-run the full pipeline)")

provider = config.default_provider()
print(f"  INFO  LLM provider: {provider}")
if provider in ("gemini", "claude", "ollama") and config.INDEX_META.exists():
    from app import llm
    try:
        out = llm.generate("Reply with the single word OK.", [dict(file="test.md", section="test", text="[test]\nThe answer is OK.", score=1)], provider)
        line(True, f"{provider} call worked (model {out['model']}): {out['text'][:60]!r}")
    except llm.LlmError as exc:
        line(False, f"{provider} call failed: {exc}")
print("\nAll good." if ok else "\nFix the FIX lines above, then run this again.")
