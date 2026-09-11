"""Project knowledge base: grounded retrieval over the VAuth repository.

Instead of canned Q&A pairs, the assistant searches the project's REAL
content (READMEs, model docs, source files, configs, test names) with TF-IDF
and answers with cited passages. Anything about the project — architecture,
endpoints, models, thresholds, telephony, banking, privacy, deployment,
file layout — resolves to actual files. Rebuilt lazily once per process.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

INCLUDE_EXTS = {".md", ".py", ".tsx", ".ts", ".txt", ".yaml", ".yml", ".json"}
SKIP_DIRS = {"node_modules", "dist", "__pycache__", ".git", ".pytest_cache",
             ".venv", "venv", ".idea", ".vscode"}
SKIP_FILES = {"package-lock.json"}
MAX_CHARS = 60000  # per file safety cap


def _chunks_for(path: Path, text: str) -> list[dict]:
    rel = str(path.relative_to(REPO))
    # Split markdown by headings, code by top-level defs/classes, else paragraphs.
    if path.suffix == ".md":
        parts = re.split(r"\n(?=#{1,3} )", text)
    elif path.suffix == ".py":
        parts = re.split(r"\n(?=class |def |@router|@app)", text)
    else:
        parts = text.split("\n\n")
    out = []
    for p in parts:
        p = p.strip()
        if len(p) < 60:
            continue
        out.append({"path": rel, "text": p[:900]})
        if len(out) > 60:
            break
    return out


def collect_passages() -> list[dict]:
    passages: list[dict] = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in sorted(files):
            p = Path(root) / fn
            if p.suffix not in INCLUDE_EXTS or fn in SKIP_FILES:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")[:MAX_CHARS]
            except OSError:
                continue
            if not text.strip():
                continue
            passages.extend(_chunks_for(p, text))
    return passages


_kb = None


def get_kb():
    """Lazily built {vectorizer, matrix, passages} (sklearn TF-IDF)."""
    global _kb
    if _kb is not None:
        return _kb
    from sklearn.feature_extraction.text import TfidfVectorizer

    passages = collect_passages()
    corpus = [f"{p['path']} {p['text']}" for p in passages]
    vectorizer = TfidfVectorizer(stop_words="english", max_features=8000,
                                 ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(corpus)
    _kb = {"vectorizer": vectorizer, "matrix": matrix, "passages": passages}
    return _kb


def search(query: str, top_k: int = 2) -> list[dict]:
    """Return top passages with cosine scores (empty if nothing relevant)."""
    import numpy as np

    try:
        kb = get_kb()
    except Exception:
        return []
    qv = kb["vectorizer"].transform([query])
    if qv.nnz == 0:
        return []
    scores = (kb["matrix"] @ qv.T).toarray().ravel()
    order = np.argsort(scores)[::-1][:top_k]
    return [{"path": kb["passages"][i]["path"],
             "text": kb["passages"][i]["text"],
             "score": round(float(scores[i]), 3)}
            for i in order if scores[i] > 0.05]


def stats() -> dict:
    try:
        kb = get_kb()
        return {"passages": len(kb["passages"]),
                "vocab": len(kb["vectorizer"].vocabulary_)}
    except Exception:
        return {"passages": 0, "vocab": 0}
