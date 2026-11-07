"""Steps 6 and 7: Chunk, then Embed and store.

Step 6 splits each masked document by its headings (one record per chunk), and only
splits further when a section is long. Step 7 turns every chunk into a vector, stores
it in Chroma, and calibrates the "is this question about our documents?" threshold.
"""
import json
import shutil

import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

import config
from app import retrieval


# ----------------------------------------------------------------------- step 6
def _sections(text: str):
    """Yield (h2, h3, body) for each heading section of a markdown document."""
    h2 = h3 = ""
    buf, out = [], []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            out.append((h2, h3, body))
        buf.clear()

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            h2, h3 = line[3:].strip(), ""
        elif line.startswith("### "):
            flush()
            h3 = line[4:].strip()
        elif line.startswith("# "):
            continue
        else:
            buf.append(line)
    flush()
    return out


def chunk_docs(ctx):
    splitter = RecursiveCharacterTextSplitter(chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP)
    chunks = []
    for path in sorted(config.DOCS_INDEXED.glob("*.md")):
        for h2, h3, body in _sections(path.read_text(encoding="utf-8")):
            section = h3 or h2 or "overview"
            label = " > ".join(x for x in (path.name, h2, h3) if x)
            pieces = [body] if len(body) <= config.CHUNK_SIZE * 1.5 else splitter.split_text(body)
            for piece in pieces:
                chunks.append(dict(id=f"c{len(chunks):04d}", file=path.name, section=section,
                                   text=f"[{label}]\n{piece}"))
    if not chunks:
        raise SystemExit("No documents found in docs/indexed/. Run the full pipeline first.")
    config.STORAGE.mkdir(parents=True, exist_ok=True)
    config.CHUNKS_FILE.write_text(json.dumps(chunks, indent=1), encoding="utf-8")
    ctx["chunks"] = chunks
    files = len({c["file"] for c in chunks})
    return f"{len(chunks)} chunks from {files} documents"


# ----------------------------------------------------------------------- step 7
def _pick_embedder(texts):
    pref = config.EMBEDDING_BACKEND
    if pref in ("auto", "chroma-default"):
        try:
            emb = retrieval.ChromaDefaultEmbedder()
            return emb, emb.embed(texts)
        except Exception as exc:   # most likely: no internet for the one-time model download
            if pref == "chroma-default":
                raise
            print(f"      ! Neural embedding model unavailable ({type(exc).__name__}). Falling back to offline LSA embeddings.")
    emb = retrieval.LsaEmbedder()
    vectors = emb.fit(texts)
    emb.save()
    return emb, vectors


def _calibrate(chunks_count):
    """Relevance threshold = just above the best relevance any clearly off-topic question reaches."""
    probes = json.loads((config.ROOT / "eval" / "offtopic_probes.json").read_text(encoding="utf-8"))
    best = [retrieval.relevance(q, retrieval.retrieve(q))[0] for q in probes]
    return round(float(np.clip(max(best) + 0.02, 0.10, 0.60)), 3), round(float(max(best)), 3), round(float(np.mean(best)), 3)


def embed_and_store(ctx):
    import chromadb
    chunks = ctx["chunks"]
    texts = [c["text"] for c in chunks]
    embedder, vectors = _pick_embedder(texts)

    if config.CHROMA_DIR.exists():
        shutil.rmtree(config.CHROMA_DIR)
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR),
                                       settings=chromadb.config.Settings(anonymized_telemetry=False))
    collection = client.create_collection("migration_docs", embedding_function=None,
                                          configuration={"hnsw": {"space": "cosine"}})
    for start in range(0, len(chunks), 128):
        part = slice(start, start + 128)
        collection.add(ids=[c["id"] for c in chunks[part]],
                       embeddings=np.asarray(vectors[part], dtype="float32").tolist(),
                       documents=texts[part],
                       metadatas=[{"file": c["file"], "section": c["section"]} for c in chunks[part]])

    w_vec, w_kw = (config.LSA_WEIGHTS if embedder.name == "lsa" else (config.W_VECTOR, config.W_KEYWORD))
    meta = dict(embedding_backend=embedder.name, chunks=len(chunks), relevance_threshold=0.2,
                w_vector=w_vec, w_keyword=w_kw)
    config.INDEX_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    retrieval.reset_store()
    threshold, off_max, off_mean = _calibrate(len(chunks))
    meta.update(relevance_threshold=threshold, offtopic_best_max=off_max, offtopic_best_mean=off_mean)
    config.INDEX_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    retrieval.reset_store()
    ctx["index_meta"] = meta
    return f"{len(chunks)} vectors stored in Chroma ({embedder.name}); relevance threshold {threshold}"
