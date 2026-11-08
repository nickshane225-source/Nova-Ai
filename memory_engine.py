"""
Nova AI - Memory Engine & Second Brain.

Pure Python standard library (sqlite3, math, re).
Provides local SQLite storage for notes, documents, and semantic search (BM25/TF-IDF)
without requiring heavy external vector database packages.
"""

import datetime
import math
import os
import re
import sqlite3
import threading
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    exe_dir = Path(sys.executable).resolve().parent
    try:
        test_file = exe_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        ROOT = exe_dir
    except Exception:
        appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        ROOT = Path(appdata) / "NovaAI"
        ROOT.mkdir(parents=True, exist_ok=True)
else:
    ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DB = DATA_DIR / "nova_brain.db"

_lock = threading.Lock()

def get_db(db_path=None):
    p = Path(db_path) if db_path else DEFAULT_DB
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path=None):
    with _lock:
        conn = get_db(db_path)
        try:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT UNIQUE,
                content TEXT,
                category TEXT DEFAULT 'general',
                created_at TEXT,
                updated_at TEXT,
                tainted INTEGER DEFAULT 0
            )
            """)
            cur.execute("PRAGMA table_info(notes)")
            cols = [r["name"] for r in cur.fetchall()]
            if "tainted" not in cols:
                cur.execute("ALTER TABLE notes ADD COLUMN tainted INTEGER DEFAULT 0")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact TEXT UNIQUE,
                category TEXT DEFAULT 'user',
                created_at TEXT
            )
            """)
            conn.commit()
        finally:
            conn.close()

# Initialize immediately with default path
init_db()

def _tokenize(text: str):
    """Normalize and tokenize text into words."""
    if not text:
        return []
    words = re.findall(r"[a-zA-Z0-9_\u0900-\u097F\u0980-\u09FF\u0600-\u06FF\u4E00-\u9FFF]+", text.lower())
    return [w for w in words if len(w) > 1]

def save_note(title: str, content: str, category: str = "general", tainted: int = 0, db_path=None) -> int:
    """Creates or updates a note in the second brain."""
    title = title.strip()
    content = content.strip()
    now = datetime.datetime.now().isoformat()
    with _lock:
        conn = get_db(db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO notes (title, content, category, created_at, updated_at, tainted)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(title) DO UPDATE SET
                    content = excluded.content,
                    category = excluded.category,
                    updated_at = excluded.updated_at,
                    tainted = excluded.tainted
                """,
                (title, content, category, now, now, 1 if tainted else 0)
            )
            conn.commit()
            last_id = cur.lastrowid
            if not last_id or last_id == 0:
                cur.execute("SELECT id FROM notes WHERE title = ?", (title,))
                row = cur.fetchone()
                if row:
                    last_id = row[0]
            return last_id or 0
        finally:
            conn.close()

def get_note(title_or_id, db_path=None):
    """Fetches a note by title or integer ID."""
    clean = str(title_or_id).strip()
    with _lock:
        conn = get_db(db_path)
        try:
            cur = conn.cursor()
            if isinstance(title_or_id, int) or clean.isdigit():
                cur.execute("SELECT * FROM notes WHERE id = ?", (int(clean),))
            else:
                cur.execute("SELECT * FROM notes WHERE LOWER(title) = LOWER(?)", (clean,))
            row = cur.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()

def list_notes(category=None, limit=50, db_path=None):
    """Lists recent notes."""
    with _lock:
        conn = get_db(db_path)
        try:
            cur = conn.cursor()
            if category:
                cur.execute("SELECT * FROM notes WHERE LOWER(category) = LOWER(?) ORDER BY updated_at DESC LIMIT ?", (category, limit))
            else:
                cur.execute("SELECT * FROM notes ORDER BY updated_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

def delete_note(title_or_id, db_path=None) -> bool:
    """Deletes a note."""
    clean = str(title_or_id).strip()
    with _lock:
        conn = get_db(db_path)
        try:
            cur = conn.cursor()
            if isinstance(title_or_id, int) or clean.isdigit():
                cur.execute("DELETE FROM notes WHERE id = ?", (int(clean),))
            else:
                cur.execute("DELETE FROM notes WHERE LOWER(title) = LOWER(?)", (clean,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

def search_notes(query: str, limit: int = 5, db_path=None):
    """
    Semantic BM25 keyword search over notes (title & content) with true RSJ IDF.
    Returns top matching notes ranked by relevance score.
    """
    q_tokens = _tokenize(query)
    if not q_tokens:
        return list_notes(limit=limit, db_path=db_path)

    all_notes = list_notes(limit=200, db_path=db_path)
    if not all_notes:
        return []

    docs_info = []
    total_len = 0
    for note in all_notes:
        d_tokens = _tokenize(note["title"] + " " + note["content"])
        t_tokens = set(_tokenize(note["title"]))
        total_len += len(d_tokens)
        docs_info.append((note, d_tokens, set(d_tokens), t_tokens))

    N = len(all_notes)
    avg_len = max(total_len / N if N > 0 else 1.0, 1.0)

    # Compute true Robertson-Spärck Jones IDF for each query term
    idf_map = {}
    for qt in q_tokens:
        n = sum(1 for _, _, token_set, _ in docs_info if qt in token_set)
        if n > 0 and N > 0:
            idf_map[qt] = math.log(1.0 + (N - n + 0.5) / (n + 0.5))
        else:
            idf_map[qt] = 0.0

    scored = []
    k1 = 1.5
    b = 0.75

    for note, doc_tokens, _, title_tokens in docs_info:
        doc_len = len(doc_tokens)
        score = 0.0
        for qt in q_tokens:
            tf = doc_tokens.count(qt)
            if tf > 0:
                idf = idf_map.get(qt, 1.0)
                # Title matches give boost
                if qt in title_tokens:
                    tf += 2
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * (doc_len / avg_len))
                score += idf * (numerator / denominator)

        if score > 0:
            item = dict(note)
            item["score"] = round(score, 3)
            scored.append(item)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]

# --- Memory Facts Bridge ---

def add_memory_fact(fact: str, category: str = "user", db_path=None):
    fact = fact.strip()
    if not fact:
        return False
    now = datetime.datetime.now().isoformat()
    with _lock:
        conn = get_db(db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO memories (fact, category, created_at) VALUES (?, ?, ?)",
                (fact, category, now)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

def get_memory_facts(limit=100, db_path=None):
    with _lock:
        conn = get_db(db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT fact FROM memories ORDER BY id DESC LIMIT ?", (limit,))
            return [r["fact"] for r in cur.fetchall()]
        finally:
            conn.close()

def delete_memory_fact(keyword: str, db_path=None):
    with _lock:
        conn = get_db(db_path)
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM memories WHERE LOWER(fact) LIKE ?", (f"%{keyword.lower().strip()}%",))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
