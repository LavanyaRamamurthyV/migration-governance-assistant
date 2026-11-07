"""PII masking (policy P-02).

Pattern based, so it is NOT exhaustive. It catches the common shapes:
emails, phone numbers, Brazilian CPF / US SSN, and long hex identifiers.
Used twice: on free-text columns during migration, and on every document
before it is chunked and embedded.
"""
import re
from collections import Counter

import pandas as pd

import config


def _mask_email(text: str) -> str:
    local, _, domain = text.partition("@")
    return f"{local[:1]}***@{domain}"


# (label, compiled pattern, replacement string or function)
PATTERNS = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"), lambda m: _mask_email(m.group(0))),
    ("national_id", re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)"), "[CPF-MASKED]"),
    ("national_id", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"), "[SSN-MASKED]"),
    ("phone", re.compile(r"\+\d{1,3}[\s-]?\(?\d{2,3}\)?[\s-]?\d{4,5}[\s-]?\d{4}"), "[PHONE-MASKED]"),
    ("phone", re.compile(r"\(\d{2,3}\)\s?\d{4,5}[\s-]?\d{4}"), "[PHONE-MASKED]"),
    ("phone", re.compile(r"(?<!\d)(?:\d{2}[\s-])?9\d{4}[\s-]?\d{4}(?!\d)"), "[PHONE-MASKED]"),
    ("phone", re.compile(r"(?<!\d)\d{3}[-.\s]\d{3}[-.\s]\d{4}(?!\d)"), "[PHONE-MASKED]"),
    ("identifier", re.compile(r"\b[0-9a-f]{32}\b"), "[ID-MASKED]"),
    ("identifier", re.compile(r"\b[0-9a-f]{16}\b"), "[ID-MASKED]"),
]


def mask_text(text: str):
    """Return (masked_text, Counter of what was masked)."""
    counts = Counter()
    for label, pattern, repl in PATTERNS:
        text, n = pattern.subn(repl, text)
        if n:
            counts[label] += n
    return text, counts


def mask_series(series: pd.Series):
    """Mask every non-null value in a pandas column. Returns (masked_series, Counter)."""
    counts = Counter()

    def _one(value):
        if value is None or pd.isna(value):
            return value
        masked, c = mask_text(str(value))
        counts.update(c)
        return masked

    return series.map(_one), counts


def run(ctx):
    """Pipeline step 5: mask every document, then write it to docs/indexed/ (what gets embedded)."""
    config.DOCS_INDEXED.mkdir(parents=True, exist_ok=True)
    for old in config.DOCS_INDEXED.glob("*.md"):
        old.unlink()
    per_file, total = {}, Counter()
    sources = sorted(config.DOCS_UNMASKED.glob("*.md")) + sorted(config.DOCS_AUTHORED.glob("*.md"))
    for path in sources:
        masked, counts = mask_text(path.read_text(encoding="utf-8"))
        (config.DOCS_INDEXED / path.name).write_text(masked, encoding="utf-8")
        per_file[path.name] = dict(counts)
        total.update(counts)
    ctx["doc_mask"] = dict(total)
    ctx["doc_mask_by_file"] = per_file
    return f"{len(sources)} documents masked; items masked: {dict(total) or 'none'}"
