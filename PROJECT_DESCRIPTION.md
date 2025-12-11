# Federal Register AI Chatbot - Project Description

## Overview
This project is an **AI-powered chatbot assistant** designed to help users search, query, and explore U.S. Federal Register documents through natural language conversations. The chatbot provides an intelligent interface to access regulatory information published by various U.S. government agencies.

---

## What Does This AI Chatbot Do?

### Core Capabilities

#### 1. **Natural Language Querying**
- Users can ask questions in plain English about federal regulations and documents
- The chatbot intelligently interprets queries and returns relevant Federal Register documents
- Supports both structured commands and free-form natural language input

#### 2. **Federal Register Document Search**
The chatbot provides multiple search methods:

**a) Keyword Search (`search <keyword>`)**
   - Searches through document titles, abstracts, excerpts, and full text
   - Uses MySQL FULLTEXT indexing for fast and accurate results
   - Example: `search pesticide` returns all documents related to pesticides

**b) Agency Filtering (`find <agency>`)**
   - Filters documents by specific government agencies
   - Example: `find EPA` shows all Environmental Protection Agency documents
   - Supports searching across hundreds of federal agencies

**c) Recent Documents (`recent <N>`)**
   - Retrieves the most recently published documents
   - Example: `recent 5` shows the 5 most recent Federal Register publications
   - Sorted by publication date in descending order

**d) Help Command (`help`)**
   - Provides dynamic usage instructions
   - Shows top agencies available in the database
   - Displays popular search keywords
   - Gives database statistics (total documents, most recent publication date)

#### 3. **Intelligent Query Routing**
- The chatbot automatically detects the user's intent
- Routes queries to the appropriate search mechanism
- Validates queries against Federal Register domain knowledge
- Rejects off-topic queries to maintain focus on regulatory information

#### 4. **Smart Domain Filtering**
- Uses token-based overlap detection to determine if queries are Federal Register-related
- Maintains a cache of agencies, document types, and keywords from the database
- Calculates relevance scores to ensure queries match the domain
- Returns helpful prompts when queries are off-topic

#### 5. **Formatted Response Display**
The chatbot presents results in an organized, readable format:
- **Topic-based grouping**: Documents are categorized by topics (Environment, Health, Energy, Tax, etc.)
- **Rich metadata**: Each result includes:
  - Document title
  - Publication date
  - Associated agencies
  - Summary/excerpt (up to 600 characters)
- **Markdown formatting**: Results are formatted for easy reading in web interfaces

---

## System Architecture

### 1. **Data Pipeline Component** (`pipeline/federal_register.py`)
**Purpose**: Fetches and stores Federal Register data

**Key Features**:
- **Automated Data Collection**: 
  - Fetches documents from the official Federal Register API
  - Supports date-range based queries
  - Implements pagination to handle large datasets
  - Uses concurrent threading (ThreadPoolExecutor) for efficient bulk downloads

- **Two-Stage Fetching Process**:
  - Stage 1: Fetches shallow document metadata (lightweight queries)
  - Stage 2: Fetches full document details in parallel (using up to 8 workers)
  
- **Database Management**:
  - Creates and maintains MySQL database schema
  - Stores documents with comprehensive metadata
  - Implements content-hash based deduplication (avoids storing unchanged documents)
  - Maintains separate tables for documents and agencies
  
- **Data Storage**:
  - Stores documents with fields like title, abstract, publication date, agencies, CFR references, etc.
  - Saves raw API responses for complete data preservation
  - Creates FULLTEXT indexes for fast searching
  
- **Retry Logic & Error Handling**:
  - Implements exponential backoff for failed API requests
  - Gracefully handles network errors and timeouts
  - Logs all operations for debugging

### 2. **AI Agent Component** (`agent/federal_agent.py`)
**Purpose**: Core intelligence for processing user queries

**Key Features**:
- **Asynchronous Operations**: All database queries and API calls are async for better performance
- **Flexible LLM Integration**: 
  - Supports AsyncOpenAI client
  - Configurable for different LLM endpoints (OpenAI, Ollama, etc.)
  - Environment-based configuration
  
- **Advanced Search Capabilities**:
  - FULLTEXT search when available (for MySQL with FULLTEXT indexes)
  - Fallback to LIKE-based searching when FULLTEXT isn't available
  - Searches across multiple fields: title, abstract, excerpt, full_text, raw_json
  - Supports agency filtering through JSON queries
  
- **Caching & Performance Optimization**:
  - Metadata caching with TTL (15-second cache for help metadata)
  - Reduces database load for frequently accessed data
  
- **Smart Response Formatting**:
  - Groups results by auto-detected topics
  - Handles missing summaries gracefully
  - Parses complex JSON agency data
  - Limits summary length to prevent overwhelming users

- **Domain Validation**:
  - Tokenizes user queries and compares against domain vocabulary
  - Uses overlap ratio thresholds to detect off-topic queries
  - Maintains dynamic list of valid keywords, agencies, and document types

### 3. **Router Agent Component** (`agent/router_agent.py`)
**Purpose**: Provides an alternative command parsing layer

**Features**:
- Thin wrapper around FederalAgent
- Supports alternative command syntax
- Routes all requests to the appropriate FederalAgent methods
- Provides consistent command handling

### 4. **API Backend Component** (`api/main.py`)
**Purpose**: RESTful API server for web and external clients

**Key Features**:
- **FastAPI Framework**: Modern, high-performance web framework
- **CORS Support**: Allows cross-origin requests for web UI integration
- **Endpoints**:
  - `POST /chat`: Main chatbot endpoint (accepts user messages, returns AI responses)
  - `GET /health`: Health check for monitoring
  - `GET /debug/search`: Debug endpoint to test database queries directly
  - `GET /debug/database-info`: Shows database statistics and sample documents
  
- **Request/Response Models**:
  - ChatRequest: Accepts message and optional chat_id
  - ChatResponse: Returns AI response and chat_id
  
- **Error Handling**: Comprehensive error handling with HTTP status codes

### 5. **Web UI Component** (`ui/index.html`)
**Purpose**: User-friendly web interface for the chatbot

**Key Features**:
- **Clean, Modern Design**:
  - Responsive chat interface
  - Message bubbles for user and bot messages
  - Loading states and error handling
  - Scrollable chat history
  
- **Markdown Support**: Uses marked.js to render formatted bot responses
- **Real-time Communication**: Async fetch API calls to backend
- **User Experience**:
  - Auto-scrolling to latest messages
  - Enter key to send messages
  - Disabled inputs during processing
  - Clear error messages for connection issues

### 6. **Database Helper Utilities** (`agent/database_helpers.py`)
**Purpose**: Utility functions for database metadata extraction

**Key Features**:
- **Keyword Extraction**: Extracts popular keywords from document titles
- **Agency Enumeration**: Gets unique list of agencies from the database
- **Document Type Listing**: Retrieves available document types
- **Smart Tokenization**: Filters stopwords and irrelevant tokens
- **JSON Normalization**: Ensures consistent agency data format

---

## Technical Stack

### Backend Technologies
- **Python 3.11+**: Core programming language
- **FastAPI**: Modern web framework for the API
- **AsyncOpenAI**: LLM integration (supports OpenAI API and Ollama)
- **MySQL**: Relational database for document storage
- **mysql-connector-python**: MySQL database driver
- **aiohttp**: Async HTTP client for API requests
- **python-dotenv**: Environment variable management

### Frontend Technologies
- **HTML5/CSS3**: Web interface structure and styling
- **Vanilla JavaScript**: Frontend logic
- **marked.js**: Markdown parsing and rendering

### External Services
- **Federal Register API**: Official U.S. Government API for Federal Register data
- **LLM Service**: Configurable (OpenAI, Ollama, or compatible endpoints)

### Data Storage
- **MySQL Database**: 
  - `documents` table: Stores complete document records
  - `agencies` table: Normalized agency information
  - FULLTEXT indexes for fast searching

---

## Key Technical Features

### 1. **Asynchronous Architecture**
- All I/O operations (database, HTTP) are asynchronous
- Uses asyncio for concurrent operations
- Improves performance and scalability

### 2. **Smart Caching**
- Metadata cache with TTL to reduce database load
- Content-hash based deduplication in the pipeline
- Prevents redundant data storage

### 3. **Robust Error Handling**
- Try-catch blocks throughout the codebase
- Graceful degradation when features are unavailable
- Comprehensive logging for debugging

### 4. **Flexible Configuration**
- Environment-based configuration via .env files
- Configurable LLM endpoints, database credentials
- Adjustable search parameters and timeouts

### 5. **Scalable Search**
- FULLTEXT indexes for fast full-text search
- Pagination support for large result sets
- Configurable result limits

### 6. **Data Quality**
- Handles missing or null fields gracefully
- JSON validation and normalization
- Date parsing with error handling

---

## Use Cases

### 1. **Regulatory Research**
Researchers can quickly find regulations related to specific topics:
- "search environmental protection"
- "find documents about healthcare reform"

### 2. **Agency Monitoring**
Track publications from specific agencies:
- "find EPA"
- "recent documents from FDA"

### 3. **Recent Activity Tracking**
Stay updated on latest regulatory changes:
- "recent 10" - see the 10 most recent documents
- Monitor new publications daily

### 4. **Keyword Discovery**
Use the help command to discover:
- What agencies publish to the Federal Register
- Popular regulatory topics
- Available document types

---

## Data Flow

### Ingestion Flow (Pipeline)
1. Pipeline fetches documents from Federal Register API
2. Documents are enriched with full details
3. Content hash is computed for each document
4. Database is checked for existing documents
5. New/changed documents are inserted/updated
6. Agencies are normalized and stored separately
7. FULLTEXT indexes are created for searching

### Query Flow (User Interaction)
1. User enters query in web UI
2. Frontend sends POST request to `/chat` endpoint
3. FederalAgent receives and analyzes the query
4. Domain validation checks if query is Federal Register-related
5. Query is routed to appropriate search method
6. MySQL database is queried (with FULLTEXT or LIKE)
7. Results are formatted and grouped by topic
8. Response is sent back to user in Markdown format
9. Frontend renders the formatted response

---

## Security & Performance Features

### Security
- Environment variables for sensitive credentials
- Input validation on all user queries
- JSON sanitization for database insertion
- CORS configured for controlled access

### Performance
- Asynchronous I/O for non-blocking operations
- Connection pooling for database queries
- Metadata caching with TTL
- FULLTEXT indexes for O(log n) search complexity
- Parallel document fetching with ThreadPoolExecutor
- Content-hash deduplication to avoid redundant storage

### Reliability
- Retry logic with exponential backoff
- Comprehensive error handling
- Database transaction management
- Logging for debugging and monitoring

---

## Project Structure

```
federal-register-agent/
├── agent/
│   ├── federal_agent.py      # Core AI agent logic
│   ├── router_agent.py        # Command routing layer
│   └── database_helpers.py    # Database utility functions
├── api/
│   ├── main.py                # FastAPI backend server
│   └── test_api.py            # API tests
├── pipeline/
│   ├── federal_register.py    # Data ingestion pipeline
│   └── check_database.py      # Database verification tool
├── ui/
│   └── index.html             # Web chat interface
├── README.md                  # Project setup and usage
└── PROJECT_DESCRIPTION.md     # This file
```

---

## Summary

This **Federal Register AI Chatbot** is a comprehensive system that:
1. **Collects** data from the official Federal Register API
2. **Stores** documents in a searchable MySQL database
3. **Provides** intelligent natural language query capabilities
4. **Delivers** formatted, organized results through a web interface
5. **Ensures** queries stay focused on Federal Register content
6. **Scales** efficiently with async operations and smart caching
7. **Maintains** data quality through validation and normalization

The chatbot serves as a bridge between users and the complex world of U.S. federal regulations, making regulatory information more accessible and discoverable through conversational AI.
