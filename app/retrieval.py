"""Hybrid retrieval: meaning search (Chroma) + exact-word search (TF-IDF), blended with NumPy.

Why hybrid: migration documents are full of exact identifiers such as
`customer_zip_prefix`. Meaning search finds "postal code" when the text says
"zip prefix"; keyword search finds the exact field name. Blending gets both.
"""
import json
import pickle
import re
from functools import lru_cache

import numpy as np
import snowballstemmer
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.preprocessing import Normalizer

import config

_STOP = set(ENGLISH_STOP_WORDS)
_stemmer = snowballstemmer.stemmer("english")


@lru_cache(maxsize=None)
def _stem(word: str) -> str:
    return _stemmer.stemWord(word)


def analyzer(text: str):
    """Tokenizer for keyword search.
    - drops filler words ("the", "of", ...)
    - stems words so "transformed" matches "transformation"
    - keeps whole identifiers AND their underscore parts, so 'customer_zip_prefix'
      matches both 'customer_zip_prefix' and 'zip'."""
    tokens = [t for t in re.findall(r"[a-z0-9_]+", text.lower())
              if t not in _STOP and (len(t) > 1 or t.isdigit())]
    out = []
    for t in tokens:
        if "_" in t:
            out.append(t)
            out.extend(_stem(p) for p in t.split("_") if len(p) > 1 and p not in _STOP)
        else:
            out.append(_stem(t))
    return out


# --------------------------------------------------------------------------- embedders
class ChromaDefaultEmbedder:
    """Chroma's built-in sentence embedding model (MiniLM, runs locally on CPU).
    Downloads about 80 MB the first time it is used, so it needs internet once."""
    name = "chroma-default"

    def __init__(self):
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        self.ef = DefaultEmbeddingFunction()

    def embed(self, texts):
        return np.array([np.asarray(v, dtype="float32") for v in self.ef(list(texts))])


class LsaEmbedder:
    """Offline fallback: TF-IDF followed by SVD ("latent semantic analysis").
    Needs no download. Weaker than a neural model, but fully local."""
    name = "lsa"

    def fit(self, texts):
        self.vec = TfidfVectorizer(analyzer=analyzer, sublinear_tf=True)
        X = self.vec.fit_transform(texts)
        k = max(2, min(128, X.shape[0] - 1, X.shape[1] - 1))
        self.svd = TruncatedSVD(n_components=k, random_state=0)
        self.norm = Normalizer()
        return self.norm.fit_transform(self.svd.fit_transform(X))

    def embed(self, texts):
        return self.norm.transform(self.svd.transform(self.vec.transform(list(texts))))

    def save(self):
        with open(config.LSA_FILE, "wb") as fh:
            pickle.dump(self, fh)

    @staticmethod
    def load():
        with open(config.LSA_FILE, "rb") as fh:   # file is produced by our own pipeline
            return pickle.load(fh)


# --------------------------------------------------------------------------- store
class Store:
    def __init__(self):
        import chromadb
        if not config.INDEX_META.exists():
            raise FileNotFoundError("No index found. Run:  python -m pipeline.run_pipeline --index-only")
        self.meta = json.loads(config.INDEX_META.read_text(encoding="utf-8"))
        self.chunks = json.loads(config.CHUNKS_FILE.read_text(encoding="utf-8"))
        self.kw = TfidfVectorizer(analyzer=analyzer, sublinear_tf=True)
        self.kw_matrix = self.kw.fit_transform([c["text"] for c in self.chunks])
        backend = self.meta["embedding_backend"]
        self.embedder = LsaEmbedder.load() if backend == "lsa" else ChromaDefaultEmbedder()
        client = chromadb.PersistentClient(
            path=str(config.CHROMA_DIR), settings=chromadb.config.Settings(anonymized_telemetry=False))
        self.collection = client.get_collection("migration_docs", embedding_function=None)

    @property
    def threshold(self) -> float:
        import os
        override = os.getenv("RELEVANCE_THRESHOLD")
        return float(override) if override else float(self.meta.get("relevance_threshold", 0.2))


@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store()


def reset_store():
    get_store.cache_clear()


def retrieve(query: str, k: int = config.TOP_K):
    """Return the k best passages with their meaning score, keyword score and blended score."""
    st = get_store()
    n = len(st.chunks)

    vec = np.zeros(n)
    qv = np.asarray(st.embedder.embed([query])[0], dtype="float32")
    if np.linalg.norm(qv) > 0:   # a query made only of unknown words has no vector
        res = st.collection.query(query_embeddings=[qv.tolist()], n_results=min(config.VECTOR_CANDIDATES, n))
        for cid, dist in zip(res["ids"][0], res["distances"][0]):
            vec[int(cid[1:])] = max(0.0, 1.0 - float(dist))   # cosine distance -> similarity

    kw = (st.kw_matrix @ st.kw.transform([query]).T).toarray().ravel()   # TF-IDF cosine similarity
    w_vec = st.meta.get("w_vector", config.W_VECTOR)
    w_kw = st.meta.get("w_keyword", config.W_KEYWORD)
    score = w_vec * vec + w_kw * kw

    out = []
    for rank, i in enumerate(np.argsort(-score)[:k], 1):
        c = st.chunks[int(i)]
        out.append(dict(rank=rank, id=c["id"], file=c["file"], section=c["section"], text=c["text"],
                        vec=round(float(vec[i]), 3), kw=round(float(kw[i]), 3), score=round(float(score[i]), 3)))
    return out


def relevance(query: str, results):
    """How relevant is this result set to the question? Returns (relevance, coverage).

    coverage  = share of the question's key words that appear in the retrieved passages
    relevance = best blended score x coverage
    A question full of words that appear nowhere in our documents ("weather", "Dallas")
    gets a low coverage, so it scores low even if one stray word matched."""
    q = set(analyzer(query))
    if not q or not results:
        return 0.0, 0.0
    seen = set()
    for r in results:
        seen.update(analyzer(r["text"]))
    coverage = len(q & seen) / len(q)
    return round(results[0]["score"] * coverage, 3), round(coverage, 2)
