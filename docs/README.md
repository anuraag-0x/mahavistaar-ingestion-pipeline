# MahaVistaar Document Intelligence Platform

This folder documents the current architecture, runtime flow, API boundaries, data model, and local deployment shape of the project.

## Documents

- [Architecture Overview & High-Level Design](./ARCHITECTURE_OVERVIEW.md)
- [Frontend Flow & UI Architecture](./FRONTEND_FLOW.md)
- [Backend Flow & Processing Pipeline](./BACKEND_FLOW.md)

## Current System Summary

The platform is an operator console for ingesting source files, extracting text, reviewing OCR output, translating non-English content, reviewing translations, chunking content, reviewing chunks, and indexing approved content for semantic search.

The current implementation is split into:

- `frontend/`: Next.js operator console.
- `backend/`: FastAPI API, PostgreSQL domain model, worker, and adapters.
- Separate repository: `mahavistaar-embedding-service`, branch `dev`, for Hugging Face multilingual embeddings.

The root `.env` is the backend and frontend development configuration. The embedding service has its own local environment in its separate repository.

## Important Current Limitations

- The upload UI accepts video files and records `document_kind=video`, but the ingestion worker currently sends all uploaded files through the PDF OCR adapter. Video transcription, frame extraction, and video OCR are not implemented yet.
- The existing Qdrant collection contains legacy vectors as well as vectors written by the new schema. New indexing uses the documented payload below; a deliberate reindex is required to migrate all existing points.
- The worker is a lightweight PostgreSQL polling process. Temporal is no longer part of the active backend flow.
