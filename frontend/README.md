# MahaVistaar Operator Console (Frontend)

The frontend for MahaVistaar is a Next.js 15 App Router web application designed for document ingestion monitoring, OCR text review, translation validation, chunk inspection, and administrative RBAC management.

---

## 1. Features
- **Document Management:** Multi-tenant document uploads (MH, GJ, etc.), pipeline stage tracking, and failure recovery.
- **Human-in-the-Loop OCR Review:** Side-by-side PDF preview and live Markdown editing with revision tracking.
- **Multilingual Translation Editor:** Review, adjust, and approve Indic language translations (Marathi, Gujarati, Hindi, etc.).
- **Semantic Chunk Inspection:** View chunk token counts, boundary spans, and toggle vector index exclusions.
- **Catalog Publication & Master Sync:** Promote schemes to public catalog and sync AI system prompt snapshots.
- **Security & Access Control:** Enterprise Keycloak SSO authentication, local email OTP fallback, and role-based permissions.

---

## 2. Quick Start & Local Setup

### Prerequisites
- Node.js 18+ or 20+
- npm or yarn

### Installation
```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install
```

### Environment Configuration
Create or update `.env.local` inside `frontend/`:
```env
NEXT_PUBLIC_API_URL=http://localhost:8001
NEXT_PUBLIC_KEYCLOAK_URL=http://localhost:8181
NEXT_PUBLIC_KEYCLOAK_REALM=docs-pipeline
NEXT_PUBLIC_KEYCLOAK_CLIENT_ID=docs-pipeline-frontend
```

### Running the Development Server
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 3. Project Structure

```text
frontend/
├── public/                 # Static assets and icons
├── src/
│   ├── app/                # Next.js App Router pages
│   │   ├── audit/          # Administrative audit logs
│   │   ├── auth/           # Keycloak SSO callback handlers
│   │   ├── chunks/         # Semantic chunk review dashboard
│   │   ├── documents/      # Document listing and detail viewer
│   │   ├── ingest/         # Document upload and ingestion trigger
│   │   ├── login/          # Login and OTP verification screen
│   │   ├── queue/          # Ingestion queue and Temporal runs
│   │   ├── roles/          # Access roles and permissions
│   │   ├── search/         # Vector and hybrid search UI
│   │   ├── settings/       # System settings
│   │   └── taxonomy/       # Scheme catalog taxonomy
│   ├── auth/               # Keycloak & local OTP AuthProvider
│   ├── components/         # Reusable UI components & ops widgets
│   └── lib/                # API client (`api.ts`), utilities, and pipeline types
├── Dockerfile              # Production container build
├── package.json
└── tsconfig.json
```

---

## 4. Production Build & Docker

```bash
# Build production bundle
npm run build

# Start production server
npm start
```

### Docker Container
```bash
docker build -t mahavistaar-frontend -f Dockerfile .
docker run -p 3000:3000 mahavistaar-frontend
```
