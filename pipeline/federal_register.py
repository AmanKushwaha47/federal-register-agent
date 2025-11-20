import os
import json
import time
import datetime
import requests
import logging
from typing import List, Dict, Optional, Any
import mysql.connector
from mysql.connector import Error
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv("pipeline/config.env")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pipeline_full.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

FR_BASE = os.getenv('FR_BASE', 'https://www.federalregister.gov')
FR_DOCS_API = FR_BASE + '/api/v1/documents.json'
FR_DOC_DETAIL = FR_BASE + '/api/v1/documents/{doc_number}.json'

DEFAULT_PER_PAGE = int(os.getenv('PER_PAGE', '100'))
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '8'))  

class FederalRegisterPipeline:
    def __init__(self):
        self.raw_data_dir = os.getenv('RAW_DIR', 'data/raw')
        self.processed_data_dir = os.getenv('PROCESSED_DIR', 'data/processed')
        os.makedirs(self.raw_data_dir, exist_ok=True)
        os.makedirs(self.processed_data_dir, exist_ok=True)

        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER', 'federal_user'),
            'password': os.getenv('DB_PASS', '!Hydraakk47'),
            'database': os.getenv('DB_NAME', 'federal_register'),
            'autocommit': False
        }

        if not self._test_database_connection():
            raise RuntimeError('Database connection failed; check credentials')

        self._setup_database()
        try:
            self.create_indexes()
        except Exception:
            logger.debug('Index creation skipped or failed; continue')

    def _get_conn(self):
        return mysql.connector.connect(
            host=self.db_config['host'],
            user=self.db_config['user'],
            password=self.db_config['password'],
            database=self.db_config.get('database')
        )

    def _test_database_connection(self) -> bool:
        try:
            conn = mysql.connector.connect(
                host=self.db_config['host'],
                user=self.db_config['user'],
                password=self.db_config['password']
            )
            conn.close()
            logger.info('✅ Database connection successful')
            return True
        except Error as e:
            logger.error(f'❌ Database connection failed: {e}')
            return False

    def _setup_database(self):
        """Create database and base tables (documents + agencies + optional extras).
        This is idempotent (uses IF NOT EXISTS).
        """
        try:
            conn = mysql.connector.connect(
                host=self.db_config['host'],
                user=self.db_config['user'],
                password=self.db_config['password']
            )
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{self.db_config['database']}`")
            conn.database = self.db_config['database']
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id VARCHAR(255) PRIMARY KEY,
                document_number VARCHAR(255),
                title LONGTEXT,
                abstract LONGTEXT,
                document_type VARCHAR(255),
                publication_date DATE,
                start_page INT NULL,
                end_page INT NULL,
                page_length INT NULL,
                pdf_url TEXT,
                html_url TEXT,
                agencies JSON,
                excerpt LONGTEXT,
                full_text LONGTEXT,
                docket_ids JSON,
                cfr_references JSON,
                comments_close_on DATETIME NULL,
                action VARCHAR(255),
                raw_json LONGTEXT,
                content_hash VARCHAR(64),
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX (publication_date),
                INDEX (document_type)
            ) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS agencies (
                id INT AUTO_INCREMENT PRIMARY KEY,
                document_id VARCHAR(255),
                name VARCHAR(255),
                raw_json LONGTEXT,
                UNIQUE KEY unique_doc_agency (document_id, name),
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                INDEX (name)
            ) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)

            conn.commit()
            cursor.close()
            conn.close()
            logger.info('Database setup completed successfully')
        except Error as e:
            logger.error(f'Database setup failed: {e}')
            raise

    def create_indexes(self):
        """Create FULLTEXT indexes to speed up searches. Run once."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            try:
                cursor.execute("ALTER TABLE documents ADD FULLTEXT idx_ft_title_abstract_excerpt (title, abstract, excerpt)")
                logger.info('Added FULLTEXT index on title/abstract/excerpt')
            except Exception as e:
                logger.debug(f'Could not add FULLTEXT index (may already exist or unsupported): {e}')
            try:
                cursor.execute("ALTER TABLE documents ADD FULLTEXT idx_ft_rawjson (raw_json)")
                logger.info('Added FULLTEXT index on raw_json')
            except Exception as e:
                logger.debug(f'Could not add FULLTEXT index on raw_json: {e}')
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.debug(f'Index creation error: {e}')

    def fetch_full_document(self, doc_number: str) -> Dict[str, Any]:
        """Fetch detailed document JSON for a given document_number."""
        url = FR_DOC_DETAIL.format(doc_number=doc_number)
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f'Failed to fetch full document {doc_number}: {e}')
            return {}

    def fetch_documents(self, days_back: int = 30, per_page: int = DEFAULT_PER_PAGE, max_pages: Optional[int] = None, max_retries: int = 3) -> List[Dict[str, Any]]:
        """Fetch shallow documents list using pagination, then fetch full details for each document."""
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days_back)

        params = {
            "conditions[publication_date][gte]": start_date.strftime("%Y-%m-%d"),
            "conditions[publication_date][lte]": end_date.strftime("%Y-%m-%d"),
            "per_page": per_page,
            "order": "newest"
        }

        all_shallow = []
        page = 1
        retries = 0

        while True:
            if max_pages and page > max_pages:
                break

            params['page'] = page
            try:
                logger.info(f'Fetching page {page} (params: {params})')
                resp = requests.get(FR_DOCS_API, params=params, timeout=30)
                logger.info(f'Page {page} status: {resp.status_code}')
                resp.raise_for_status()
                data = resp.json()

                if not isinstance(data, dict) or 'results' not in data:
                    logger.warning(f'Unexpected API response on page {page}')
                    break

                results = data.get('results', [])
                logger.info(f'Fetched {len(results)} shallow docs from page {page}')

                if not results:
                    break

                all_shallow.extend(results)

                filename = os.path.join(self.raw_data_dir, f'federal_register_shallow_{start_date}_{end_date}_page{page}.json')
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                if len(results) < per_page:
                    break

                page += 1
                retries = 0

            except requests.HTTPError as e:
                logger.warning(f'HTTPError fetching page {page}: {e}')
                retries += 1
                if retries >= max_retries:
                    logger.error('Exceeded retries for pagination')
                    break
                time.sleep(2 ** retries)
            except requests.RequestException as e:
                logger.warning(f'RequestException fetching page {page}: {e}')
                retries += 1
                if retries >= max_retries:
                    logger.error('Exceeded retries for pagination')
                    break
                time.sleep(2 ** retries)
            except Exception as e:
                logger.error(f'Unexpected error fetching page {page}: {e}')
                break

        logger.info(f'Total shallow documents fetched: {len(all_shallow)}')

        full_results: List[Dict[str, Any]] = []
        if not all_shallow:
            return []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            future_to_docnum = {}
            for doc in all_shallow:
                doc_num = doc.get('document_number') or doc.get('id')
                if not doc_num:
                    continue
                future = ex.submit(self.fetch_full_document, doc_num)
                future_to_docnum[future] = (doc, doc_num)

            for future in as_completed(future_to_docnum):
                doc_shallow, doc_num = future_to_docnum[future]
                try:
                    full = future.result()
                    merged = {**doc_shallow, **(full or {})}
                    full_results.append(merged)
                except Exception as e:
                    logger.warning(f'Error fetching full doc {doc_num}: {e}')
                    full_results.append(doc_shallow)

        logger.info(f'Total full documents prepared: {len(full_results)}')

        filename = os.path.join(self.processed_data_dir, f'federal_register_full_{start_date}_{end_date}.json')
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(full_results, f, indent=2, ensure_ascii=False)

        return full_results

    def _compute_content_hash(self, doc: Dict[str, Any]) -> str:
        j = json.dumps(doc, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(j.encode('utf-8')).hexdigest()

    def process_documents(self, documents: List[Dict[str, Any]]):
        """Insert or update documents and agencies with content-hash deduplication."""
        if not documents:
            logger.warning('No documents to process')
            return

        conn = None
        try:
            conn = self._get_conn()
            cursor = conn.cursor(buffered=True)
            conn.start_transaction()

            processed_count = 0
            skipped_count = 0

            for doc in documents:
                try:
                    doc_num = doc.get('document_number') or doc.get('id')
                    if not doc_num:
                        logger.warning('Skipping document without document_number')
                        skipped_count += 1
                        continue

                    content_hash = self._compute_content_hash(doc)

                    cursor.execute('SELECT content_hash FROM documents WHERE id = %s', (doc_num,))
                    row = cursor.fetchone()
                    if row and row[0] == content_hash:
                        logger.debug(f'Skipping unchanged doc {doc_num}')
                        continue  # unchanged

                    publication_date = None
                    if doc.get('publication_date'):
                        try:
                            publication_date = str(doc.get('publication_date')).split('T')[0]
                            datetime.datetime.strptime(publication_date, '%Y-%m-%d')
                        except Exception:
                            publication_date = None

                    values = (
                        doc_num,
                        doc.get('document_number', ''),
                        doc.get('title'),
                        doc.get('abstract'),
                        doc.get('type') or doc.get('document_type'),
                        publication_date,
                        doc.get('start_page'),
                        doc.get('end_page'),
                        doc.get('page_length'),
                        doc.get('pdf_url'),
                        doc.get('html_url'),
                        json.dumps(doc.get('agencies', []), ensure_ascii=False) if doc.get('agencies') else None,
                        doc.get('excerpt'),
                        doc.get('full_text'),
                        json.dumps(doc.get('docket_ids', []), ensure_ascii=False) if doc.get('docket_ids') else None,
                        json.dumps(doc.get('cfr_references', []), ensure_ascii=False) if doc.get('cfr_references') else None,
                        doc.get('comments_close_on'),
                        doc.get('action'),
                        json.dumps(doc, ensure_ascii=False),
                        content_hash
                    )

                    insert_sql = """
                        INSERT INTO documents (
                            id, document_number, title, abstract, document_type,
                            publication_date, start_page, end_page, page_length,
                            pdf_url, html_url, agencies, excerpt, full_text,
                            docket_ids, cfr_references, comments_close_on, action,
                            raw_json, content_hash
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            title = VALUES(title),
                            abstract = VALUES(abstract),
                            document_type = VALUES(document_type),
                            publication_date = VALUES(publication_date),
                            start_page = VALUES(start_page),
                            end_page = VALUES(end_page),
                            page_length = VALUES(page_length),
                            pdf_url = VALUES(pdf_url),
                            html_url = VALUES(html_url),
                            agencies = VALUES(agencies),
                            excerpt = VALUES(excerpt),
                            full_text = VALUES(full_text),
                            docket_ids = VALUES(docket_ids),
                            cfr_references = VALUES(cfr_references),
                            comments_close_on = VALUES(comments_close_on),
                            action = VALUES(action),
                            raw_json = VALUES(raw_json),
                            content_hash = VALUES(content_hash),
                            last_updated = CURRENT_TIMESTAMP
                    """

                    cursor.execute(insert_sql, values)

                    agencies = doc.get('agencies', []) or []
                    if isinstance(agencies, list):
                        for agency in agencies:
                            try:
                                name = agency.get('name') if isinstance(agency, dict) else str(agency)
                                if not name:
                                    continue
                                cursor.execute(
                                    "INSERT IGNORE INTO agencies (document_id, name, raw_json) VALUES (%s, %s, %s)",
                                    (doc_num, name, json.dumps(agency, ensure_ascii=False))
                                )
                            except Exception as e:
                                logger.debug(f'Agency insert error for {doc_num}: {e}')

                    processed_count += 1
                    if processed_count % 50 == 0:
                        logger.info(f'Processed {processed_count} documents...')

                except Exception as e:
                    logger.error(f'Error processing document {doc.get("document_number")}: {e}')
                    skipped_count += 1
                    continue

            conn.commit()
            logger.info(f'Successfully processed {processed_count} documents, skipped {skipped_count}')

        except Error as e:
            if conn:
                conn.rollback()
            logger.error(f'Database error during processing: {e}')
            raise
        finally:
            if conn:
                try:
                    cursor.close()
                    conn.close()
                except Exception:
                    pass

    def get_help_metadata(self, top_n_agencies: int = 25, top_n_types: int = 25) -> Dict[str, Any]:
        """Return dynamic metadata for the help page: agencies, document types, recent dates."""
        try:
            conn = self._get_conn()
            cur = conn.cursor(dictionary=True)

            cur.execute("SELECT COUNT(*) as total FROM documents")
            total = cur.fetchone().get('total', 0)

            cur.execute("SELECT DISTINCT publication_date FROM documents ORDER BY publication_date DESC LIMIT 5")
            recent_dates = [r['publication_date'] for r in cur.fetchall()]

            cur.execute("SELECT name, COUNT(*) as cnt FROM agencies GROUP BY name ORDER BY cnt DESC LIMIT %s", (top_n_agencies,))
            agencies = [r['name'] for r in cur.fetchall()]

            cur.execute("SELECT DISTINCT document_type FROM documents ORDER BY document_type LIMIT %s", (top_n_types,))
            types = [r['document_type'] for r in cur.fetchall() if r['document_type']]

            cur.close()
            conn.close()
            return {
                'total_documents': total,
                'recent_dates': recent_dates,
                'top_agencies': agencies,
                'document_types': types
            }
        except Exception as e:
            logger.debug(f'get_help_metadata error: {e}')
            return {
                'total_documents': 0,
                'recent_dates': [],
                'top_agencies': [],
                'document_types': []
            }

if __name__ == '__main__':
    p = FederalRegisterPipeline()
    docs = p.fetch_documents(days_back=30, per_page=100)
    p.process_documents(docs)