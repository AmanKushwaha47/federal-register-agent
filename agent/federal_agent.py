import os
import re
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional
import mysql.connector
from mysql.connector import Error
from openai import AsyncOpenAI
import aiohttp
import time
from .database_helpers import get_unique_agencies, get_unique_document_types, get_top_keywords
import textwrap
from dotenv import load_dotenv

load_dotenv("pipeline/config.env")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://localhost:11434")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", f"{OLLAMA_BASE}/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("OLLAMA_KEY", "ollama"))
LLM_MODEL = os.getenv("LLM_MODEL", "phi3:latest")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))

class FederalAgent:
    def __init__(self, db_config: Optional[Dict[str, Any]] = None, debug: bool = False):
        self.db_config = db_config or {
            "host": DB_HOST,
            "user": DB_USER,
            "password": DB_PASS,
            "database": DB_NAME,
        }
        self.debug = debug
        self._ensure_client()

        self._meta_cache: Optional[Dict[str, Any]] = None
        self._meta_cache_ts: float = 0.0
        self._meta_cache_ttl = 15.0 

    def _ensure_client(self):
        try:
            self.client = AsyncOpenAI(
                base_url=os.getenv("LLM_BASE_URL", LLM_BASE_URL),
                api_key=os.getenv("LLM_API_KEY", LLM_API_KEY),
                timeout=LLM_TIMEOUT
            )
        except Exception as e:
            logger.warning(f"AsyncOpenAI creation failed: {e}")
            self.client = None

    def _get_db_connection(self):
        return mysql.connector.connect(
            host=self.db_config["host"],
            user=self.db_config["user"],
            password=self.db_config["password"],
            database=self.db_config.get("database")
        )

    async def _run_db(self, fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def _get_help_metadata(self) -> Dict[str, Any]:
        now = time.time()
        if self._meta_cache and (now - self._meta_cache_ts) < self._meta_cache_ttl:
            return self._meta_cache

        def _work():
            try:
                conn = self._get_db_connection()
                agencies = get_unique_agencies(conn)
                types = get_unique_document_types(conn)
                keywords = get_top_keywords(conn, n=30)
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM documents")
                total = cur.fetchone()[0]
                cur.execute("SELECT DISTINCT publication_date FROM documents ORDER BY publication_date DESC LIMIT 1")
                r = cur.fetchone()
                most_recent = r[0] if r else None
                cur.close()
                conn.close()
                return {"total_documents": total, "most_recent": most_recent, "agencies": agencies, "document_types": types, "keywords": keywords}
            except Exception as e:
                logger.debug(f"_get_help_metadata error: {e}")
                return {"total_documents": 0, "most_recent": None, "agencies": [], "document_types": [], "keywords": []}

        self._meta_cache = await self._run_db(_work)
        self._meta_cache_ts = now
        return self._meta_cache

    async def _format_help_text(self, meta: dict) -> str:
        top_agencies = meta.get("agencies", [
            "Agency for Healthcare Research and Quality",
            "Agricultural Marketing Service",
            "Agriculture Department",
            "Alcohol and Tobacco Tax and Trade Bureau",
            "Animal and Plant Health Inspection Service",
            "Antitrust Division",
            "Army Department"
        ])

        popular_keywords = meta.get("keywords", [
            "collection", "request", "information", "proposed", "agency",
            "review", "comment", "activities", "program", "public",
            "meeting", "filing"
        ])

        def format_list(items, width=60, indent=4):
            wrapped_items = []
            for item in items:
                wrapped = textwrap.fill(
                    item,
                    width=width,
                    initial_indent=' ' * indent + '• ',
                    subsequent_indent=' ' * (indent + 2)
                )
                wrapped_items.append(wrapped)
            return "\n".join(wrapped_items)

        top_agencies_text = format_list(top_agencies)
        popular_keywords_text = format_list(popular_keywords)

        help_text = f"""
🔍 Federal Register Search Assistant

How to use:

1️⃣ Search by keyword
• `search <keyword>`
• Example: `search pesticide`
• Searches titles, abstracts, and documents containing the keyword.

2️⃣ Find by agency
• `find <agency>`
• Example: `find EPA`
• Filters documents published by a specific agency.

3️⃣ Get recent documents
• `recent <N>`
• Example: `recent 5`
• Shows the N most recent documents across all agencies.

4️⃣ Show this help
• `help`
• Displays usage instructions, top agencies, and popular keywords.

⚠️ Important:
This assistant strictly answers Federal Register / U.S. regulatory queries only.  
General questions, or unrelated topics will not return results.

Top agencies (sample):  
{top_agencies_text}

Popular keywords (sample):  
{popular_keywords_text}
"""
        return help_text.strip()    

    async def _analyze_database_content(self) -> dict:
        """Return basic info: total documents, recent document date, counts."""
        def _work():
            try:
                conn = self._get_db_connection()
                cur = conn.cursor()

                cur.execute("SELECT COUNT(*) FROM documents")
                total_docs = cur.fetchone()[0]

                cur.execute("SELECT MAX(publication_date) FROM documents")
                latest_date = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM agencies")
                total_agencies = cur.fetchone()[0]

                cur.close()
                conn.close()

                return {
                    "total_documents": total_docs,
                    "latest_publication_date": str(latest_date),
                    "total_agency_entries": total_agencies
                }
            except Exception as e:
                return {"error": str(e)}

        return await self._run_db(_work)
    async def _query_mysql(self, query: str, filters: Optional[Dict[str, Any]] = None, limit: int = 25) -> List[Dict[str, Any]]:
        def _work(q, f, lim):
            try:
                conn = self._get_db_connection()
                cur = conn.cursor(dictionary=True)

                q = (q or "").strip()
                params = []
                use_fulltext = False
                try:
                    cur.execute("SHOW INDEX FROM documents WHERE Index_type='FULLTEXT' LIMIT 1")
                    idx = cur.fetchone()
                    use_fulltext = bool(idx)
                except Exception:
                    use_fulltext = False

                if q and use_fulltext:
                    sql = """
                        SELECT id, title, abstract, excerpt, document_type, publication_date, agencies,
                               MATCH(title, abstract, excerpt, raw_json) AGAINST (%s IN NATURAL LANGUAGE MODE) AS relevance
                        FROM documents
                        WHERE MATCH(title, abstract, excerpt, raw_json) AGAINST (%s IN NATURAL LANGUAGE MODE)
                    """
                    params = [q, q]
                elif q:
                    like = f"%{q}%"
                    sql = """
                        SELECT id, title, abstract, excerpt, document_type, publication_date, agencies
                        FROM documents
                        WHERE (title LIKE %s OR abstract LIKE %s OR excerpt LIKE %s OR full_text LIKE %s OR raw_json LIKE %s)
                    """
                    params = [like, like, like, like, like]
                else:
                    sql = "SELECT id, title, abstract, excerpt, document_type, publication_date, agencies FROM documents WHERE 1=1"
                    params = []

                if f and f.get("agency"):
                    sql += " AND JSON_CONTAINS(agencies, JSON_OBJECT('name', %s))"
                    params.append(f.get("agency"))

                sql += " ORDER BY publication_date DESC LIMIT %s"
                params.append(lim)

                cur.execute(sql, params)
                rows = cur.fetchall()
                cur.close()
                conn.close()
                return rows
            except Exception as e:
                logger.error(f"_query_mysql DB error: {e}")
                return []

        return await self._run_db(_work, query, filters or {}, limit)

    def _parse_agencies(self, raw: Any) -> List[str]:
        if not raw:
            return []
        try:
            if isinstance(raw, str):
                data = json.loads(raw)
            else:
                data = raw
            if isinstance(data, list):
                out = []
                for item in data:
                    if isinstance(item, dict):
                        name = item.get("name") or item.get("raw_name") or item.get("agency")
                        if name:
                            out.append(name)
                    elif isinstance(item, str):
                        out.append(item)
                return out
            if isinstance(data, dict):
                return [data.get("name") or data.get("raw_name") or str(data)]
            return [str(data)]
        except Exception:
            return []

    def _topic_from_title(self, title: str) -> str:
        if not title:
            return "General"
        t = title.lower()
        mapping = {
            'environment': 'Environment', 'air': 'Air Quality', 'energy': 'Energy',
            'health': 'Health', 'medicare': 'Healthcare', 'trade': 'Trade',
            'finance': 'Finance', 'tax': 'Tax', 'pesticide': 'Pesticide'
        }
        for k, v in mapping.items():
            if k in t:
                return v
        return "General"

    def _format_record(self, row: Dict[str, Any]) -> Dict[str, Any]:
        title = row.get("title") or row.get("id") or "(No title)"
        agencies = self._parse_agencies(row.get("agencies"))
        summary = (row.get("excerpt") or row.get("abstract") or "No summary available")[:600]
        return {
            "title": title,
            "date": str(row.get("publication_date") or ""),
            "agencies": agencies,
            "summary": summary
        }

    async def run(self, query: str, filters: Optional[Dict[str, Any]] = None, limit: int = 25) -> str:
        rows = await self._query_mysql(query or "", filters or {}, limit)
        if not rows:
            return "No relevant regulations found."

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            topic = self._topic_from_title(r.get("title", ""))
            grouped.setdefault(topic, []).append(self._format_record(r))

        out = "# 📚 Federal Register Search Results\n\n"
        for topic, items in grouped.items():
            out += f"## 🗂️ {topic}\n\n"
            for it in items:
                agencies = ", ".join(it["agencies"]) if it["agencies"] else "Unknown"
                out += f"### {it['title']}\n"
                out += f"📅 **Date**: {it['date']}\n"
                out += f"🏛️ **Agencies**: {agencies}\n"
                out += f"📝 **Summary**: {it['summary']}\n\n"
        out += "---\n*Use `help` for search tips.*"
        return out

    async def chat(self, message: str) -> str:
        msg = (message or "").strip()
        if not msg:
            return "Please provide a query. Use `help` for examples."

        lower = msg.lower().strip()
        cmd_prefixes = ("search ", "find ", "recent", "help", "get ", "show ")
        for p in cmd_prefixes:
            if lower == p.strip() or lower.startswith(p):
                if lower.startswith("recent"):
                    parts = msg.split()
                    if len(parts) == 2 and parts[1].isdigit():
                        return await self.run("", {}, limit=int(parts[1]))
                    return "Usage: recent <N>"
                if lower.startswith("find "):
                    agency = msg[len("find "):].strip()
                    if not agency:
                        return "Usage: find <agency>"
                    return await self.run("", filters={"agency": agency})
                if lower.startswith("search "):
                    q = msg[len("search "):].strip()
                    if not q:
                        return "Usage: search <keyword>"
                    return await self.run(q)
                if lower == "help":
                    meta = await self._get_help_metadata()
                    return await self._format_help_text(meta)
                break
        tokens = re.findall(r"[A-Za-z0-9\-']+", lower)
        if not tokens:
            return "Please provide a query. Use `help` for examples."

        meta = await self._get_help_metadata()
        domain_tokens = set()
        for k in meta.get("keywords", []):
            domain_tokens.update(re.findall(r"[A-Za-z0-9\-']+", k.lower()))
        for a in meta.get("agencies", []):
            domain_tokens.update(re.findall(r"[A-Za-z0-9\-']+", a.lower()))
        for t in meta.get("document_types", []):
            domain_tokens.update(re.findall(r"[A-Za-z0-9\-']+", str(t).lower()))

        msg_tokens = set(tokens)
        overlap = msg_tokens & domain_tokens
        overlap_ratio = len(overlap) / max(1, len(msg_tokens))

        SHORT_INPUT_THRESHOLD = 0.33
        OVERLAP_THRESHOLD = 0.18

        if len(tokens) <= 2 and overlap_ratio >= SHORT_INPUT_THRESHOLD:
            return await self.run(lower)
        if len(tokens) > 2 and overlap_ratio >= OVERLAP_THRESHOLD:
            return await self.run(lower)

        return (
            "This assistant strictly answers **Federal Register / U.S. regulatory** queries only.\n\n"
            "Try one of the following:\n"
            "• `search <keyword>`\n"
            "• `find <agency>`\n"
            "• `recent <N>`\n"
            "• `help`\n"
        )

    async def _ensure_ollama_reachable(self) -> bool:
        if not self.client:
            return False
        try:
            async with aiohttp.ClientSession() as s:
                url = f"{OLLAMA_BASE}/api/tags"
                async with s.get(url, timeout=3) as r:
                    return r.status == 200
        except Exception:
            return False