# MahaVistaar Document Ingestion & Search Platform

An enterprise, review-driven document ingestion, multilingual translation, semantic chunking, and vector search platform built around **PostgreSQL**, **Qdrant**, **MinIO**, **FastAPI**, and **Next.js**.

---

## Docker deployment

Use the existing PostgreSQL server and start the application stack with:

```bash
docker compose up -d --build --wait --wait-timeout 300
```

Complete the one-time `.env` setup in [the deployment guide](docs/DEPLOYMENT.md)
first. The MinIO console is exposed on port **9001**.

## 1. Subproject Documentation

The repository is organized into distinct subprojects. Refer to the specific README in each directory:

- **[Architecture Overview & High-Level Design (`docs/ARCHITECTURE_OVERVIEW.md`)](docs/ARCHITECTURE_OVERVIEW.md):** 4-Layer presentation diagram, plain-English core flows, hexagonal architecture, and technology stack summary.
- **[Backend Flow (`docs/BACKEND_FLOW.md`)](docs/BACKEND_FLOW.md):** Step-by-step backend processing and two-tier DEV/PROD publishing flow.
- **[Frontend Operator Console (`frontend/README.md`)](frontend/README.md):** Next.js 15 App Router operator console with Keycloak SSO, live PDF preview, OCR Markdown editing, translation review, and chunk inspection.
- **[PostgreSQL Backend API (`backend/README.md`)](backend/README.md):** Redesigned FastAPI service with SQLAlchemy 2.0, Alembic migrations, hexagonal ports & adapters, interactive Swagger UI, and pure PostgreSQL persistence.

---

## 2. Repository Layout

```text
mahavistaar-ingestion-pipeline/
├── frontend/                     # Next.js 15 Operator Console
├── backend/                      # Pure PostgreSQL-backed FastAPI backend
│   ├── app/                      # API routers, models, schemas, ports, adapters, services
│   ├── migrations/               # Alembic database migrations
│   ├── alembic.ini
│   ├── Dockerfile
│   └── requirements.txt
├── .env                          # Local environment configuration
└── README.md                     # Root project documentation
```

---

## 3. Platform Architecture & Service Ports

| Service | Port | Description | Documentation |
| :--- | :--- | :--- | :--- |
| **Frontend UI** | `3000` | Next.js operator console | [`frontend/README.md`](frontend/README.md) |
| **Backend API** | `8002` | FastAPI document ingestion & search API | [`backend/README.md`](backend/README.md) |
| **Keycloak SSO** | `8181` | Authentication & RBAC identity provider | Existing local Keycloak instance |
| **PostgreSQL** | `5432` / `5434` | Relational document state & audit persistence | [`backend/README.md`](backend/README.md) |
| **Qdrant** | `6333` | Vector database for semantic chunk retrieval | [`backend/README.md`](backend/README.md) |
| **MinIO** | `9000` / `9001` | Object storage (original uploads & artifacts) | [`backend/README.md`](backend/README.md) |

---

## 4. Interactive API Documentation (Swagger & ReDoc)

When the backend service is running, explore interactive OpenAPI specifications at:

* **Backend Swagger UI:** [http://localhost:8002/docs](http://localhost:8002/docs)
* **Backend ReDoc:** [http://localhost:8002/redoc](http://localhost:8002/redoc)
* **Backend OpenAPI JSON Schema:** [http://localhost:8002/openapi.json](http://localhost:8002/openapi.json)
