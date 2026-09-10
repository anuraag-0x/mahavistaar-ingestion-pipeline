# MahaVistaar Ingestion & Search Backend

An asynchronous, PostgreSQL-backed document ingestion, translation, chunking, and semantic vector search API built on **FastAPI** and **SQLAlchemy 2.0**.

---

## 1. Architecture Overview

The backend uses a clean **Hexagonal (Ports & Adapters)** architecture:

```text
backend/
├── app/
│   ├── api/                  # Modular v1 domain routers + backwards-compatible aliases
│   │   └── v1/
│   │       ├── admin.py      # Audit logging & settings
│   │       ├── auth.py       # Email OTP & RBAC endpoints
│   │       ├── catalog.py    # Scheme catalog & Master AI catalog sync
│   │       ├── chunks.py     # Semantic chunking & exclusions
│   │       ├── documents.py  # Ingestion lifecycle & multi-tenant workflows
│   │       ├── pages.py      # Page-level OCR & multilingual translations
│   │       └── search.py     # Qdrant semantic vector search
│   ├── core/
│   │   ├── config.py         # Pydantic BaseSettings loading .env
│   │   └── database.py       # SQLAlchemy 2.0 asyncpg & psycopg2 engines
│   ├── models/               # Pure PostgreSQL ORM declarative tables
│   ├── schemas/              # Pydantic request/response validation & DTOs
│   ├── ports/                # Abstract interfaces (Storage, VectorStore, AI)
│   ├── adapters/             # Concrete implementations (MinIO, Qdrant, Standalone Embeddings)
│   └── services/             # Pure domain business logic
├── migrations/               # Alembic database migration scripts
├── alembic.ini               # Alembic configuration
├── Dockerfile                # Production container build
└── requirements.txt          # Python dependencies
```

---

## 2. Interactive Swagger & API Documentation

When the backend is running, the interactive documentation interfaces are automatically generated:

* **Swagger UI (Interactive API Explorer):** [http://localhost:8001/docs](http://localhost:8001/docs)
* **ReDoc (Detailed Schema Documentation):** [http://localhost:8001/redoc](http://localhost:8001/redoc)
* **OpenAPI 3.1 JSON Specification:** [http://localhost:8001/openapi.json](http://localhost:8001/openapi.json)

---

## 3. Local Setup & Running

### Prerequisites
- Python 3.11+
- Running PostgreSQL database (and optionally MinIO & Qdrant)

### 1. Install Dependencies
```bash
pip install -r backend/requirements.txt
```

### 2. Configure Environment
Settings are read directly from the root `.env` file:
```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=docs-pipeline
POSTGRES_USER=docs_pipeline
POSTGRES_PASSWORD=Kenpath@123
MINIO_ENDPOINT=localhost:9000
QDRANT_URL=http://localhost:6333
HF_EMBEDDING_SERVICE_URL=http://localhost:8021
```

### 3. Run the Backend
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8001 --reload
```

---

## 4. Database Migrations (Alembic)

Database schema versioning is managed via Alembic:

```bash
# Generate a new migration revision
alembic revision --autogenerate -m "create_initial_tables"

# Apply pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

---

## 5. API Routes Reference

| Domain | Route | Methods | Description |
| :--- | :--- | :--- | :--- |
| **Documents** | `/api/v1/documents` | `GET`, `POST` | List documents, upload files |
| **Documents** | `/api/v1/documents/{id}` | `GET`, `PATCH` | Retrieve or update document status |
| **Pages** | `/api/v1/pages/document/{id}` | `GET` | List OCR pages and translations |
| **Pages** | `/api/v1/pages/{id}/{page}/ocr` | `PATCH` | Update human-reviewed OCR markdown |
| **Pages** | `/api/v1/pages/{id}/{page}/translation` | `PATCH` | Update human-reviewed translation |
| **Chunks** | `/api/v1/chunks/document/{id}` | `GET` | List semantic chunks |
| **Chunks** | `/api/v1/chunks/{id}/{chunk}` | `GET`, `PATCH` | Review or exclude chunks from vector index |
| **Search** | `/api/v1/search` | `POST` | Hybrid vector & semantic search via Qdrant |
| **Catalog** | `/api/v1/catalog/schemes` | `GET` | Query public scheme catalog |
| **Catalog** | `/api/v1/catalog/sync` | `POST` | Upsert document into Master AI catalog |
| **Auth** | `/api/v1/auth/otp/send` | `POST` | Send 6-digit email OTP |
| **Auth** | `/api/v1/auth/otp/verify` | `POST` | Verify OTP and issue session token |
| **Admin** | `/api/v1/admin/audit/{id}` | `GET` | Retrieve document audit trail |
