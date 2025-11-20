import sys
import os
import logging

# Add the parent directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from agent.federal_agent import FederalAgent
import uvicorn

from dotenv import load_dotenv
load_dotenv("pipeline/config.env")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize agent
agent = FederalAgent()

class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    chat_id: str

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        response = await agent.chat(request.message)
        return ChatResponse(response=response, chat_id=request.chat_id or "demo_chat")
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Federal Register Agent"}

@app.get("/debug/search")
async def debug_search(query: str = "regulation", agency: str = None):
    """Debug endpoint to test database queries directly"""
    try:
        filters = {"agency": agency} if agency else {}
        data = await agent._query_mysql(query, filters)
        
        return {
            "query": query,
            "agency_filter": agency,
            "results_count": len(data),
            "sample_titles": [doc.get('title', 'No title')[:80] + "..." for doc in data[:3]]
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/debug/database-info")
async def _debug_database_content(self) -> str:
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME        
        )
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT title, publication_date, agencies FROM documents ORDER BY publication_date DESC LIMIT 5")
        samples = cursor.fetchall()
        
        cursor.execute("SELECT COUNT(*) as total FROM documents")
        total = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        result = f"Database has {total['total']} documents.\n\nRecent samples:\n"
        for i, doc in enumerate(samples):
            result += f"{i+1}. {doc['title'][:80]}...\n"
            result += f"   Date: {doc['publication_date']}\n"
            result += f"   Agencies: {doc['agencies'][:100]}...\n\n"
            
        return result
        
    except Exception as e:
        return f"Error checking database: {e}"