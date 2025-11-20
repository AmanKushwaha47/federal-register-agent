import json
import re
from collections import Counter
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

STOPWORDS = {
    'the','and','for','with','that','this','from','are','was','have','has','will','shall',
    'notice','of','to','in','a','an','on','by','us','u.s','u.s.', 'u.s.a', 'be', 'is', 'as',
}

def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    text = re.sub(r"[^A-Za-z0-9'\-]+", ' ', text).lower()
    tokens = [t.strip("'\-") for t in text.split() if t]
    return tokens

def get_top_keywords(conn, n: int = 30, min_len: int = 4) -> List[str]:
    """Return top-n keywords from document titles (best-effort)."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT title FROM documents WHERE title IS NOT NULL LIMIT 20000")
        rows = cur.fetchall()
        cur.close()

        c = Counter()
        for (title,) in rows:
            if not title:
                continue
            for t in _tokenize(title):
                if len(t) < min_len or t in STOPWORDS:
                    continue
                if re.fullmatch(r"\d+", t):
                    continue
                c[t] += 1
        return [w for w, _ in c.most_common(n)]
    except Exception as e:
        logger.debug(f"get_top_keywords error: {e}")
        return []

def get_unique_agencies(conn) -> List[str]:
    """
    Preferred: read from normalized agencies table.
    Fallback: read JSON 'agencies' from documents.
    """
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT name FROM agencies WHERE name IS NOT NULL ORDER BY name")
        rows = cur.fetchall()
        agencies = [r[0] for r in rows if r and r[0]]
        if agencies:
            cur.close()
            return agencies

        cur.execute("SELECT agencies FROM documents WHERE agencies IS NOT NULL LIMIT 10000")
        rows = cur.fetchall()
        cur.close()
        s = set()
        for (ag,) in rows:
            try:
                data = json.loads(ag)
                if isinstance(data, list):
                    for a in data:
                        name = a.get('name') if isinstance(a, dict) else str(a)
                        if name:
                            s.add(name)
            except Exception:
                continue
        return sorted(list(s))
    except Exception as e:
        logger.debug(f"get_unique_agencies error: {e}")
        return []

def get_unique_document_types(conn) -> List[str]:
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT document_type FROM documents WHERE document_type IS NOT NULL ORDER BY document_type")
        rows = cur.fetchall()
        cur.close()
        return [r[0] for r in rows if r and r[0]]
    except Exception as e:
        logger.debug(f"get_unique_document_types error: {e}")
        return []

def normalize_agencies_field(raw: Any) -> str:
    """
    Ensure the agencies field is a JSON string of a list of objects or names.
    Use this before inserting/updating DB.
    """
    try:
        if raw is None:
            return "[]"
        if isinstance(raw, str):
            try:
                json.loads(raw)
                return raw
            except Exception:
                return json.dumps([raw], ensure_ascii=False)
        if isinstance(raw, dict):
            return json.dumps([raw], ensure_ascii=False)
        if isinstance(raw, list):
            return json.dumps(raw, ensure_ascii=False)
        return json.dumps([str(raw)], ensure_ascii=False)
    except Exception:
        return "[]"