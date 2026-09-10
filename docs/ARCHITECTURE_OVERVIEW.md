# MahaVistaar – Architecture Overview & High-Level Design

> **Executive Summary:** MahaVistaar is an enterprise document intelligence and semantic search platform. It transforms complex multilingual agricultural PDFs and guidelines into verified, searchable knowledge through automated AI extraction (OCR & Translation), human-in-the-loop review, and a two-tier publishing model (DEV Index for testing ➔ PROD Index for live applications).

---

## 1. Simplified 4-Layer Presentation Architecture

```mermaid
flowchart TD
    subgraph L1["1. User & Operator Layer"]
        UI["🖥️ Operator Console (Next.js :3000)<br/>• Document Upload & Monitoring<br/>• OCR / Translation / Chunk Review<br/>• Search Workbench"]
    end

    subgraph L2["2. Core Platform & Logic Layer"]
        API["⚡ Backend API (FastAPI :8002)<br/>• REST Endpoints & RBAC Auth<br/>• Real-Time SSE Live Updates"]
        WORKER["⚙️ Background Worker<br/>• Orchestrates Pipeline Stages<br/>• Job Queue Polling"]
    end

    subgraph L3["3. Data & Storage Layer"]
        DB[("🗄️ PostgreSQL Database<br/>• Document & Job States<br/>• Extracted Pages & Chunks<br/>• Master AI Catalog & Audits")]
        MINIO[("📦 MinIO Object Storage<br/>• Original PDFs & File Artifacts")]
    end

    subgraph L4["4. AI & Search Engine Layer"]
        OCR["👁️ Mistral OCR (Text Extraction)"]
        TRANS["🌐 Gemma LLM (Multilingual Translation)"]
        EMBED["🧠 E5-Large (Dense Embeddings)"]
        DEV_INDEX[("🔍 Qdrant DEV Index<br/>(local-documents-index)")]
        PROD_INDEX[("🚀 Qdrant PROD Index<br/>(prod-documents-index)")]
    end

    %% Simple, intuitive flows
    UI <-->|"HTTP / SSE"| API
    API <-->|"State & Jobs"| DB
    API <-->|"Store / Fetch Files"| MINIO
    API <-->|"DEV / PROD Search"| DEV_INDEX & PROD_INDEX

    WORKER <-->|"Claim Jobs & Update Progress"| DB
    WORKER -->|"Read Files"| MINIO
    WORKER -->|"Extract Text"| OCR
    WORKER -->|"Translate"| TRANS
    WORKER -->|"Embed & Index"| EMBED
    EMBED -->|"1. Auto-Publish to DEV"| DEV_INDEX
    DEV_INDEX -.->|"2. Super Admin Gate"| PROD_INDEX

    %% Color-coded presentation styling
    classDef l1Style fill:#D0E8F2,stroke:#4A90E2,stroke-width:2px,color:#1A252C,font-weight:bold;
    classDef l2Style fill:#C6D8EB,stroke:#3B6E8C,stroke-width:2px,color:#1A252C,font-weight:bold;
    classDef l3Style fill:#D4EDDA,stroke:#28A745,stroke-width:2px,color:#155724,font-weight:bold;
    classDef l4Style fill:#E2D9F3,stroke:#6F42C1,stroke-width:2px,color:#38186D,font-weight:bold;

    class UI l1Style;
    class API,WORKER l2Style;
    class DB,MINIO l3Style;
    class OCR,TRANS,EMBED,DEV_INDEX,PROD_INDEX l4Style;
```

---

## 2. The 3 Core Flows (In Plain English)

### 🔹 Flow 1: Automated Ingestion & AI Extraction
```text
[ Upload PDF ] ➔ [ Mistral OCR ] ➔ [ Language Detection & Gemma Translation ] ➔ [ Semantic Chunking ]
```
1. **Upload:** User uploads a PDF via the web console.
2. **OCR Extraction:** Mistral OCR converts pages into structured markdown.
3. **Translation:** If non-English (e.g. Marathi/Gujarati), Gemma LLM translates it into English while preserving the original text.
4. **Chunking:** Content is split into clean 450-token semantic chunks with page citations.

---

### 🔹 Flow 2: Human Review & Two-Tier Publishing (DEV ➔ PROD)
```text
[ Review & Edit ] ➔ [ Auto-Publish to DEV Index ] ➔ [ Test Search in DEV ] ➔ [ Super Admin Promotes to PROD ]
```
1. **Human-in-the-Loop Review:** Reviewers can edit extracted text, refine translations, or exclude unwanted chunks.
2. **Auto-Publish to DEV Index:** Approved chunks are immediately converted into 1024-dim dense vectors and published to the **Qdrant DEV collection** (`local-documents-index`).
3. **DEV Search Testing:** Operators verify retrieval accuracy in the search playground against the DEV collection.
4. **PROD Promotion Gate:** Super Admin approves the document, promoting it to the **Qdrant PROD collection** (`prod-documents-index`) and syncing the Master Catalog for downstream AI chatbots.

---

### 🔹 Flow 3: Semantic Search Retrieval
```text
[ User Query ] ➔ [ Generate Query Embedding ] ➔ [ Qdrant Vector Match ] ➔ [ Ranked Results with Citations ]
```
1. User enters a query (*e.g., "How to apply for crop insurance subsidy?"*).
2. Backend generates a 1024-dim vector using multilingual `e5-large`.
3. Qdrant performs cosine similarity matching.
4. Returns top matching text snippets with page numbers, document names, and Marathi/English citations.

---

## 3. Technology Stack Cheat Sheet

| Technology | Layer | Purpose & Selection Rationale |
| :--- | :--- | :--- |
| **Next.js 15 (React 19)** | Frontend Console | Modern responsive UI for operator review, PDF side-by-side preview, and search. |
| **FastAPI** | Backend API | High-performance Python async API with automatic interactive Swagger docs. |
| **PostgreSQL 15** | Relational Database | Transactional source of truth for documents, stages, jobs, and live SSE event triggers (`pg_notify`). |
| **MinIO** | Object Storage | S3-compatible, on-prem storage for original PDF files and artifacts. |
| **Qdrant** | Vector Database | Ultra-fast vector search supporting two-tier collections (`DEV` vs `PROD`) and payload filters. |
| **Mistral OCR** | Vision Extraction | Best-in-class extraction for complex multi-column documents and tables. |
| **Gemma vLLM** | Translation Engine | Domain-aware Indic-to-English translation preserving agricultural terminology. |
| **E5-Large** | Text Embeddings | 1024-dimensional multilingual embeddings for cross-lingual search. |
| **Keycloak SSO** | Auth Provider | Enterprise OpenID Connect identity provider with Role-Based Access Control. |

---

## 4. End-to-End Ingestion Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Operator as Operator / Reviewer
    actor SuperAdmin as Super Admin
    participant FE as Next.js Console
    participant API as FastAPI Backend
    participant DB as PostgreSQL
    participant MinIO as MinIO Storage
    participant Worker as Background Worker
    participant AI as AI Services (OCR / Translation / Embeddings)
    participant QdrantDev as Qdrant DEV Index
    participant QdrantProd as Qdrant PROD Index

    %% 1. Registration
    Note over Operator,MinIO: Phase 1: Upload & Registration
    Operator->>FE: Select file & document_kind
    FE->>API: POST /documents/upload (multipart/form-data)
    API->>MinIO: PutObject (original document)
    API->>DB: INSERT into documents & document_jobs
    API-->>FE: Return document metadata (workflow_id)

    %% 2. OCR Stage
    Note over Worker,AI: Phase 2: OCR Extraction
    Worker->>DB: Poll queued job (FOR UPDATE SKIP LOCKED)
    Worker->>MinIO: GetObject (bytes)
    Worker->>AI: Mistral OCR API (process_pdf)
    AI-->>Worker: Extracted markdown pages
    Worker->>DB: INSERT into pages, set stage = 'ocr_review'
    Worker->>DB: pg_notify('document_events')
    DB-->>API: Notify SSE listener
    API-->>FE: Stream document.updated event

    %% 3. OCR Review & Approval
    Note over Operator,API: Phase 3: Human-in-the-Loop OCR Review
    Operator->>FE: Review & Edit Markdown
    FE->>API: PATCH /pages/{id}/{page}/ocr
    API->>DB: UPDATE pages.edited_markdown
    Operator->>FE: Click "Approve OCR"
    FE->>API: POST /documents/{id}/approve-ocr
    API->>DB: UPDATE stage = 'translation_processing', enqueue job

    %% 4. Translation Stage
    Note over Worker,AI: Phase 4: Language Detection & Translation
    Worker->>DB: Claim translation job
    Worker->>Worker: Detect Language (Lingua / Script gate)
    alt Non-English
        Worker->>AI: Gemma LLM / vLLM Translate
        AI-->>Worker: English translated text
        Worker->>DB: UPDATE pages.translated_markdown, stage = 'translation_review'
        Operator->>FE: Click "Approve Translation"
        FE->>API: POST /documents/{id}/approve-translation
        API->>DB: UPDATE stage = 'chunking', enqueue job
    else English Only
        Worker->>DB: UPDATE stage = 'chunking', enqueue job
    end

    %% 5. Chunking & Auto-Publishing to DEV
    Note over Worker,QdrantDev: Phase 5: Chunking & Auto-Publishing to DEV Index
    Worker->>DB: Claim chunking job
    Worker->>Worker: Split text into target chunk spans (450 tokens, overlap 128)
    Worker->>DB: INSERT into chunks, stage = 'chunk_review'
    Operator->>FE: Review chunks, trim text, toggle exclusions
    FE->>API: PATCH /chunks/{id}/{chunk}
    Operator->>FE: Click "Approve Chunks"
    FE->>API: POST /documents/{id}/approve-chunks
    API->>DB: UPDATE stage = 'ingesting', enqueue job

    Worker->>DB: Claim ingestion job & fetch non-excluded chunks
    Worker->>AI: Standalone Embedding Service (POST /v1/embeddings)
    AI-->>Worker: 1024-dim dense vectors
    Worker->>QdrantDev: Upsert points to DEV Index (local-documents-index)
    Worker->>DB: UPSERT master_catalog (status = ['dev'])
    Worker->>DB: UPDATE stage = 'ready_for_ingestion' (or 'approval_for_prod')
    Worker->>DB: pg_notify('document_events', stage='approval_for_prod')
    DB-->>API: Notify SSE listener
    API-->>FE: Document ready for DEV Search & PROD Gate

    %% 6. Promotion to PROD
    Note over SuperAdmin,QdrantProd: Phase 6: Super Admin Promotion to PROD
    SuperAdmin->>FE: Test Search in DEV & Click "Approve for PROD"
    FE->>API: POST /documents/{id}/approve-ingestion (or /catalog/publish-prod)
    API->>QdrantProd: Upsert vectors to PROD Index (prod-documents-index)
    API->>DB: UPDATE master_catalog (status = ['dev', 'live'])
    API->>DB: UPDATE documents (stage = 'completed', ingested_at = now)
    API-->>FE: Stream completion & Live status
```

---

## 5. Backend Hexagonal Architecture

```mermaid
flowchart TD
    subgraph Clients["Incoming Requests"]
        FE["Next.js Operator UI"]
        API_CLIENTS["External AI Tools / API Consumers"]
    end

    subgraph AdaptersIn["Inbound Adapters (FastAPI API Layer)"]
        DOC_ROUTER["Documents Router<br/>(/documents, /upload)"]
        PAGE_ROUTER["Pages Router<br/>(/pages, /ocr)"]
        CHUNK_ROUTER["Chunks Router<br/>(/chunks)"]
        SEARCH_ROUTER["Search Router<br/>(/search)"]
        EVENT_ROUTER["Events Router<br/>(SSE /events)"]
        ADMIN_ROUTER["Admin & Auth Router<br/>(/auth, /admin)"]
    end

    subgraph DomainCore["Domain Core (Services & Ports)"]
        DOC_SVC["Document Service"]
        PAGE_SVC["Page Service"]
        CHUNK_SVC["Chunk Service"]
        SEARCH_SVC["Search Service"]
        CATALOG_SVC["Catalog & Sync Service"]
        INGEST_SVC["Ingestion Service"]
        AUDIT_SVC["Audit Service"]
        AUTH_SVC["Auth & RBAC Service"]
    end

    subgraph WorkerLayer["Asynchronous Worker Engine"]
        WORKER["Background Worker<br/>(backend.worker)"]
    end

    subgraph AdaptersOut["Outbound Adapters (Infrastructure)"]
        MINIO_ADAPTER["MinIO Storage Adapter<br/>(Object Storage)"]
        QDRANT_DEV["Qdrant DEV Adapter<br/>(local-documents-index)"]
        QDRANT_PROD["Qdrant PROD Adapter<br/>(prod-documents-index)"]
        OCR_ADAPTER["Mistral OCR Adapter<br/>(AI Extraction)"]
        TRANS_ADAPTER["Gemma Translation Adapter<br/>(AI Translation)"]
        EMBED_ADAPTER["HF Embedding Adapter<br/>(1024-dim Embeddings)"]
        DB_ADAPTER["SQLAlchemy / asyncpg<br/>(PostgreSQL 15)"]
    end

    %% Inbound Connections
    FE --> DOC_ROUTER & PAGE_ROUTER & CHUNK_ROUTER & SEARCH_ROUTER & EVENT_ROUTER & ADMIN_ROUTER
    API_CLIENTS --> SEARCH_ROUTER & DOC_ROUTER

    DOC_ROUTER --> DOC_SVC
    PAGE_ROUTER --> PAGE_SVC
    CHUNK_ROUTER --> CHUNK_SVC
    SEARCH_ROUTER --> SEARCH_SVC
    ADMIN_ROUTER --> AUTH_SVC & AUDIT_SVC

    %% Service to Outbound
    DOC_SVC & PAGE_SVC & CHUNK_SVC & INGEST_SVC & CATALOG_SVC --> DB_ADAPTER
    DOC_SVC --> MINIO_ADAPTER
    SEARCH_SVC --> EMBED_ADAPTER & QDRANT_DEV & QDRANT_PROD

    %% Worker Connections
    DB_ADAPTER -.->|"Poll Jobs (FOR UPDATE SKIP LOCKED)"| WORKER
    WORKER --> OCR_ADAPTER & TRANS_ADAPTER & EMBED_ADAPTER & MINIO_ADAPTER & QDRANT_DEV & QDRANT_PROD
    WORKER -->|"Update State & pg_notify"| DB_ADAPTER

    %% Visual Styling
    classDef clientStyle fill:#D0E8F2,stroke:#4A90E2,stroke-width:2px,color:#1A252C,font-weight:bold;
    classDef apiStyle fill:#C6D8EB,stroke:#3B6E8C,stroke-width:2px,color:#1A252C,font-weight:bold;
    classDef coreStyle fill:#FAD2A7,stroke:#E67E22,stroke-width:2px,color:#1A252C,font-weight:bold;
    classDef workerStyle fill:#FFE5B4,stroke:#D35400,stroke-width:2px,color:#1A252C,font-weight:bold;
    classDef dbStyle fill:#D4EDDA,stroke:#28A745,stroke-width:2px,color:#155724,font-weight:bold;
    classDef aiStyle fill:#E2D9F3,stroke:#6F42C1,stroke-width:2px,color:#38186D,font-weight:bold;

    class FE,API_CLIENTS clientStyle;
    class DOC_ROUTER,PAGE_ROUTER,CHUNK_ROUTER,SEARCH_ROUTER,EVENT_ROUTER,ADMIN_ROUTER apiStyle;
    class DOC_SVC,PAGE_SVC,CHUNK_SVC,SEARCH_SVC,CATALOG_SVC,INGEST_SVC,AUDIT_SVC,AUTH_SVC coreStyle;
    class WORKER workerStyle;
    class DB_ADAPTER,MINIO_ADAPTER,QDRANT_DEV,QDRANT_PROD dbStyle;
    class OCR_ADAPTER,TRANS_ADAPTER,EMBED_ADAPTER aiStyle;
```

---

## 6. Database Models & Schema Design

### PostgreSQL Relational Tables
- **`documents`**: Document metadata, lifecycle state (`registered`, `ocr_review`, `translation_review`, `chunk_review`, `ready_for_ingestion`, `approval_for_prod`, `completed`, `failed`), tenant instance (`mh`, `gj`), document kind (`advisory`, `scheme`, `video`), and MinIO storage pointers.
- **`document_jobs`**: Asynchronous job queue (`queued`, `running`, `waiting_review`, `completed`, `failed`) consumed by `backend.worker`.
- **`pages`**: Extracted OCR markdown, human edited text, detected language, and translated markdown.
- **`chunks`**: Text chunk units, token counts, page span lineage, and boolean vector exclusion flags (`is_excluded`).
- **`master_catalog`**: Master AI catalog synchronization table holding document entries, prompt snippets, and environment status tiers (`status: ['dev']` or `status: ['dev', 'live']`).
- **`audit_logs`**: Tamper-evident log of all operator actions, stage approvals, reviews, and retries.
- **`document_index_status`**: Indexing status, target collection name, and vector count.

### Qdrant Vector Payload Schema
```json
{
  "id": "e4b2d180-60b1-4f40-8b17-0c7da79712ab",
  "vector": [0.0124, -0.0481, 0.0832, "... 1024 floats ..."],
  "payload": {
    "doc_id": "doc_694fb2193b22",
    "type": "document",
    "chunk_id": "chunk_001",
    "name": "PM_Kisan_Guidelines.pdf",
    "source": "PM Kisan Scheme Operational Manual, Page 1-3",
    "source_mr": "पीएम किसान योजना मार्गदर्शक सूचना, पृष्ठ १-३",
    "text": "The Pradhan Mantri Kisan Samman Nidhi provides financial support..."
  }
}
```

---

## 7. Security, RBAC & Failure Recovery

### Role-Based Access Control
- **`admin`**: Full operational access (Upload documents, edit OCR/translations, curate chunks, test in DEV search, trigger retries).
- **`super_admin`**: Full administration (Promote DEV documents to PROD, manage users & roles, sync Master Catalog to live AI bots).

### Stage-Specific Failure Recovery
If any stage fails due to external API errors, timeouts, or invalid formats, the document enters the `failed` stage. Dedicated idempotent endpoints allow restarting that exact stage without re-uploading the original file:
- **`POST /documents/{id}/retry-ocr`**: Restarts OCR extraction.
- **`POST /documents/{id}/retry-translation`**: Restarts language translation.
- **`POST /documents/{id}/retry-chunking`**: Restarts chunking generation.
- **`POST /documents/{id}/reingest`**: Restarts vector indexing.
- **`DELETE /documents/{id}`**: Soft-deletes document and frees resources.
