# Federal Register Chat Agent

## Project Overview
This project is a **chat-style AI assistant for querying the U.S. Federal Register**.  
It allows users to:
- Search by keywords (`search <keyword>`)
- Filter by agency (`find <agency>`)
- Retrieve recent documents (`recent <N>`)
- Display help (`help`)

It is built using:
- **Python 3.11+**
- **MySQL** database to store Federal Register documents
- **AsyncOpenAI** / Ollama LLM for AI-driven query handling
- **AIOHTTP** for async HTTP requests

---

## Features
- Asynchronous database queries for performance.
- Topic-based grouping of search results.
- Handles documents with missing summaries gracefully.
- Easy-to-use chat interface (terminal or web integration).
- Configurable for different LLM endpoints.

---

## Getting Started
1. Clone the repo:
```bash
git clone https://github.com/<AmanKushwaha47>/<federal-register-agent>.git
