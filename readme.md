## AI Multi-agent System.

qdrant dashboard:
http://localhost:16433/dashboard

rest:
http://localhost:16433

## Docling CLI (optional)

After the backend container is running you can launch the vision-language doc extraction without changing the image:

```bash
docker compose exec backend bash /app/bin/docling_vlm.sh /repo/DOCS/area1
```

The script uses the `docling` CLI and writes exports to `/tmp/docling_exports` inside the container (override with `DOC_EXTRACTION_OUTPUT`).

## Get tables in DB:
docker exec dlv2-backend-1 python -c "from sqlalchemy import inspect; from app.core.database import engine; print(inspect(engine).get_table_names())"

## Rebuilding containers:
docker compose up -d --build backend frontend

## install LLaMA 3.1 (8B-Q4_K_M)
- $env:HF_TOKEN="hugging face api key"
- docker model pull ai/llama3.1:8B-Q4_K_M
- docker model run ai/llama3.1:8B-Q4_K_M 'What are three benefits of running LLMs locally?'
- docker model pull ai/mxbai-embed-large

## Local LLaMA 3.1 (8B-Q4_K_M)

Docker Desktop's Model Runner exposes the host `model-runner.docker.internal`. Ensure the `ai/llama3.1:8B-Q4_K_M` engine is running (Docker Desktop ? Extensions ? Model Runner). The backend connects to:

```text
http://model-runner.docker.internal/engines/llama.cpp/v1
```

### Quick verification (from the backend container)

```bash
curl http://model-runner.docker.internal/engines/llama.cpp/v1/models
curl http://model-runner.docker.internal/engines/llama.cpp/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"ai/llama3.1:8B-Q4_K_M","messages":[{"role":"user","content":"Say hello"}]}'
curl http://model-runner.docker.internal/engines/llama.cpp/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ai/llama3.1:8B-Q4_K_M",
    "input": [
      "Artificial intelligence is transforming the world.",
      "Costa Rica is known for its biodiversity."
    ],
    "pooling": "mean"
  }'
```

To switch back to OpenAI embeddings set `EMBEDDING_PROVIDER=openai` and provide `OPENAI_API_KEY`.
