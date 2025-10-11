## Project Scope Overview

DLV2 is a modular multi‑agent RAG platform built around a FastAPI backend, a Next.js frontend, PostgreSQL for relational data, and Qdrant for vector storage. The objective is to ingest large document corpora, chunk & embed them via local or remote LLM services, and expose them to orchestrated agents. This document gives any contributor or LLM assistant enough context to navigate, extend, and troubleshoot the stack quickly.

---

### High-Level Architecture

| Layer | Technology | Responsibilities |
|-------|------------|------------------|
| **Frontend** | Next.js 15 / React 19 | Auth UI, operator dashboards (currently `/auth`, `/me`, `/menu`). |
| **Backend API** | FastAPI + SQLAlchemy | Authentication, user management, ingestion pipelines, vector ops, admin bootstrap. |
| **Relational DB** | PostgreSQL (service `db`) | Stores users, RAG ingestion jobs/artifacts/chunk metadata. Tables autocrate via SQLAlchemy. |
| **Vector Store** | Qdrant (service `dbrag`) | Stores chunk embeddings (collection per area). |
| **Local LLM / Embeddings** | Docker Model Runner (`model-runner.docker.internal/engines/llama.cpp/v1`) | Provides OpenAI-compatible embeddings (default `ai/llama3.1:8B-Q4_K_M`). |
| **OCR / Extraction** | Docling (with Granite VLM optional), Tesseract, RapidOCR/EasyOCR fallbacks | Converts PDFs & images to text prior to chunking. |

All services are orchestrated via `docker-compose.yml` with bind mounts for hot reload and local document access (`DOCS/`).

---

### Repository Layout (Key Paths)

```
.
├─ backend/
│  ├─ app/
│  │  ├─ core/                # Settings, DB, module loader, security helpers
│  │  ├─ modules/
│  │  │  ├─ auth/             # Login API, token issuance
│  │  │  ├─ users/            # Users domain (models, repo, service, bootstrap)
│  │  │  └─ rag/              # Ingestion pipeline (sources, extractors, chunking, embeddings, storage, router/service)
│  │  └─ main.py              # FastAPI app factory, startup hooks
│  ├─ Dockerfile.dev          # Dev image with Tesseract, Docling, debugpy
│  └─ bin/start-dev.sh        # Uvicorn launcher with auto-reload & optional debugpy
├─ frontend/
│  ├─ app/                    # Next.js routes (`/auth`, `/me`, `/menu`, API routes)
│  ├─ Dockerfile.dev          # Dev image; mounts source & runs `npm run dev`
│  └─ app/api/                # Proxy routes (`/api/auth/...`, `/api/rag/...`)
├─ db/                        # Initialization scripts (currently empty or custom)
├─ DOCS/                      # Host-mounted document corpus (areas area1/area2/...)
├─ docker-compose.yml         # Service definitions (db, dbrag, backend, frontend)
├─ .env/.env.example          # Runtime configuration
├─ readme.md                  # Operator quick-start, Docling CLI, local LLM notes
└─ readme.scope.md            # (this file) project scope for assistants
```

---

### Backend Core Concepts

#### Configuration (`backend/app/core/config.py`)

* Uses Pydantic Settings. Important env vars:
  * `DATABASE_URL` – PostgreSQL DSN (`postgresql+psycopg://...`).
  * `DBRAG_QDRANT_URL`/`DBRAG_QDRANT_TIMEOUT_SECONDS` – Qdrant connection & timeout.
  * `RAG_*` settings – chunk sizes, embedding dimension, batch size.
  * `EMBEDDING_PROVIDER` – `"local"` by default (OpenAI-compatible endpoint).
  * `LOCAL_EMBEDDING_BASE_URL` – points to Docker Model Runner (`http://model-runner.docker.internal/engines/llama.cpp/v1`).
  * `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_FULL_NAME` – default admin bootstrap credentials.
  * `DOCLING_VLM_MODEL` – optional (set to model name if Granite Docling VLM is available).

`readme.md` documents how to run the LLaMA engine externally when using Docker Desktop Model Runner.

#### Startup Flow (`backend/app/main.py`)

1. Collect module routers (loading models first).
2. Call `ensure_core_schema()` to auto-create tables (no Alembic).
3. Mount module routers.
4. Startup event:
   * `ensure_qdrant_ready()` – tests Qdrant availability.
   * `ensure_default_admin()` – seeds/updates admin account if env vars present.

#### Authentication

* `/auth/login` – returns JWT (HS256) on success.
* `/auth/me` – requires `Authorization: Bearer`.
* Token TTL controlled by `AUTH_TOKEN_TTL_SECONDS`.
* Password hashing uses Argon2 (via `passlib`).
* Tables created automatically (`users`), admin is active & superuser by default.

#### RAG Module Highlights

| Component | File | Purpose |
|-----------|------|---------|
| Source discovery | `rag/pipeline/sources.py` | Adapters (currently local filesystem) for area folders. |
| Extraction | `rag/pipeline/extractors.py` | Priority: Docling (optional VLM) → Tesseract (`tesserocr`/`pytesseract`) → RapidOCR/ocrmac/EasyOCR → plaintext. |
| Chunking | `rag/pipeline/chunking.py` | RecursiveCharacterTextSplitter with `chunk_size` / `chunk_overlap`. |
| Embeddings | `rag/pipeline/embeddings.py` | Switchable providers (`local`, `openai`, `ollama`, `huggingface`). Local uses OpenAI-compatible API. |
| Storage | `rag/pipeline/storage.py` | Ensures Qdrant collection & upserts in batches (`QDRANT_UPSERT_BATCH_SIZE`). |
| Jobs/Artifacts | `rag/models.py` & `rag/repository.py` | SQLAlchemy models for ingestion status and chunk metadata. |
| Router | `rag/router.py` | `/rag/ingest` (HTTP ingestion trigger), `/rag/jobs` (status). Needs auth. |

Pipeline steps per file:

1. `/rag/ingest`: Accepts array of locations `{uri, area_slug, agent_slug, recursive}`.
2. `IngestionService -> IngestionPipeline.run_job`:
   * Discover files.
   * Extract text (Docling + fallbacks).
   * Chunk & embed.
   * Upsert into Qdrant (collection `rag_{area_slug}`).
   * Record artifacts/chunks in Postgres.

**Performance tips:** first Docling run may download OCR models (logged). Adjust `RAG_MAX_BATCH_SIZE` & `QDRANT_UPSERT_BATCH_SIZE` if Qdrant timeouts occur. Add logging inside pipeline for long PDFs to monitor progress.

---

### Data Model Summary

| Table | Description |
|-------|-------------|
| `users` | Auth accounts (UUID string IDs, hashed passwords, superuser flag). |
| `rag_ingestion_jobs` | Track ingestion runs (area, agent, status, counts, error). |
| `rag_artifacts` | Each ingested document; stores metadata, hash for dedupe. |
| `rag_artifact_chunks` | One row per chunk (preview text, tokens, Qdrant ID, metadata JSON). |

Tables auto-create on startup via SQLAlchemy metadata (no migrations).

Qdrant collections are created per `area_slug` with vector size `RAG_EMBEDDING_DIMENSION`. Embeddings stored in `rag_{area}` collections with metadata payload (artifact, chunk index, etc.).

---

### Local Embedding / LLM Integration

* **Default**: `EMBEDDING_PROVIDER=local` → `EmbeddingFactory._local()` uses `OpenAIEmbeddings` pointed at `LOCAL_EMBEDDING_BASE_URL`.
* **Endpoint**: `http://model-runner.docker.internal/engines/llama.cpp/v1` (Docker Model Runner). Works from containers on Docker Desktop.
* **Switching providers**: Set `EMBEDDING_PROVIDER=openai` and supply `OPENAI_API_KEY` to revert to remote embedding service.
* **Docling VLM**: Leave `DOCLING_VLM_MODEL` unset unless Granite Docling weights are available. Fallbacks handle older configs.

---

### Frontend Highlights

* `/auth` – Styled login/register. Calls `/api/auth/login` (Next.js proxy to backend), stores token.
* `/me` – Displays account info, includes link to `/menu`.
* `/menu` – Operator dashboard to trigger ingestion (POST payloads), view job history, link to Qdrant dashboard.
* `frontend/app/api/**` – Proxy routes ensure cookies (`access_token`) are attached to backend requests.
* Styling is inline CSS (no global Tailwind yet). Consider migrating to CSS modules or Tailwind if UI grows.

---

### Running the Stack (Development)

1. **Prereqs**: Docker Desktop with Model Runner (for local embeddings), Node/npm, Python 3.13 if running locally.
2. **Local environment**:
   ```bash
   cp .env.example .env
   # Fill ADMIN_EMAIL/ADMIN_PASSWORD, HF_TOKEN (if needed), etc.
   ```
3. **Start backend + frontend + databases**:
   ```bash
   docker compose up -d --build backend frontend dbrag db
   ```
   Backend auto-creates tables and seeds default admin.
4. **Start local LLM via Docker Model Runner** (outside compose):
   ```bash
   docker model pull ai/llama3.1:8B-Q4_K_M
   # Launch via Docker Desktop Model Runner UI (preferred) or CLI.
   curl http://model-runner.docker.internal/engines/llama.cpp/v1/models
   ```
5. **Access UI**: `http://localhost:13001/auth` → login with admin credentials from `.env`.
6. **Trigger ingestion**: Use `/menu` to POST to `/rag/ingest` (e.g., `area1`, `agent1`, `uri: area1`).

**Hot reload:** Backend mounts `./backend/app` & `./backend/bin`; frontend mounts `./frontend`. Buttons for dev debugging:
* Backend debugger: exposed on `localhost:15678` (debugpy) if `DEBUGPY=1`.
* Qdrant dashboard: `http://localhost:16433/dashboard`.

---

### Logging & Diagnostics

* Backend logs show Docling pipeline stages, OCR model downloads, Qdrant collection creation, ingestion errors.
* To increase transparency for long documents, add logging inside `IngestionPipeline` after each major step (Docling conversion, chunking, embeddings, Qdrant batch).
* Qdrant timeouts can be mitigated by tweaking `QDRANT_UPSERT_BATCH_SIZE` or raising `DBRAG_QDRANT_TIMEOUT_SECONDS`.
* To inspect database tables:
  ```bash
  docker exec -it dlv2-db-1 psql -U raguser -d ragdb
  select * from users;
  ```
* Admin seeding logs appear at backend startup (`ensure_default_admin`).

---

### Extension Points & TODOs

1. **Agent Orchestration**: Currently placeholders; integrate actual multi-agent coordinator referencing Qdrant collections by `area_slug`.
2. **Front-end UI**: `/auth` and `/menu` are basic; consider adding ingestion progress displays, job filtering, agent config pages.
3. **Monitoring**: Add OpenTelemetry or structured logging for ingestion runtimes to identify bottlenecks.
4. **Ingestion Scalability**: Introduce background workers (Celery / RQ) if synchronous HTTP ingestion becomes a bottleneck.
5. **Document Source Adapters**: Extend `SourceRegistry` to support S3, SharePoint, etc.
6. **Retry / Resume**: Pipeline currently fails on first exception; implement retries or resumable jobs via `rag_artifacts.status`.
7. **Model Warmup**: First-run OCR downloads cause delays; consider pre-warming Docling or caching models in the container image.

---

### Quick Checklist for New Issues

1. **Authentication failing?**  
   - Check `users` table exists (`ensure_core_schema` runs on startup).  
   - Confirm `ADMIN_EMAIL/PASSWORD` in env.  
   - Inspect backend logs for bootstrap messages.

2. **Ingestion slow / failing?**  
   - Watch backend logs: look for Docling model downloads or Qdrant timeouts.  
   - Verify local LLM endpoint at `model-runner.docker.internal`.  
   - Adjust batch sizes / timeouts in `.env`.

3. **Frontend errors?**  
   - Ensure `/api/**` proxies hitting backend at `BACKEND_INTERNAL_URL`.  
   - CSS mostly inline; adjust `frontend/app/auth/page.tsx` and `frontend/app/menu/page.tsx`.

4. **Add new module?**  
   - Create directory under `backend/app/modules/<module>` with `models.py`, `router.py`, etc.  
   - Ensure `models.py` imports register once module is added (auto-loaded by `collect_routers`).  
   - Add tests/an end-to-end ingestion job is triggered via `/rag/ingest`.

---

This scope document should be provided to any future LLMs or contributors to avoid onboarding delay. It highlights where to look, how the services interact, and what configuration needs attention when extending the system.***
