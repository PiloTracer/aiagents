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

### Manual run outside compose
```bash
# Set your Hugging Face token for the current session
$env:HF_TOKEN = "hf_youractualtokenhere"

# Optional: verify
echo $env:HF_TOKEN
```


```bash
docker run -d `
  --name bge-embedder `
  --gpus all `
  -p 18082:8002 `
  -e HF_TOKEN=$env:HF_TOKEN `
  ghcr.io/huggingface/text-embeddings-inference:1.8 `
  --model-id BAAI/bge-m3 `
  --pooling mean `
  --hostname 0.0.0.0 `
  --port 8002
```
# one line
docker run -d   --name bge-embedder   --gpus all   -p 18082:8002   -e HF_TOKEN=$env:HF_TOKEN   ghcr.io/huggingface/text-embeddings-inference:1.8   --model-id BAAI/bge-m3   --pooling mean   --hostname 0.0.0.0   --port 8002

Set `LOCAL_EMBEDDING_BASE_URL` and `LOCAL_EMBEDDING_URL` as follows:

- When running the embedder manually on the host:
  - `LOCAL_EMBEDDING_BASE_URL=http://host.docker.internal:18082`
  - `LOCAL_EMBEDDING_URL=http://host.docker.internal:18082/embed`
- When addressing it directly from the host: `LOCAL_EMBEDDING_URL=http://localhost:18082/embed`
- When the embedder runs inside the same Compose stack: `LOCAL_EMBEDDING_URL=http://bge-embedder:8002/embed` (base URL can stay unset).

### Smoke test

```bash
$body = @{ inputs = @("hola José","café sin azúcar") } | ConvertTo-Json -Depth 3
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)

Invoke-RestMethod -Uri "http://localhost:18082/embed" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $bytes
```

# one line
Invoke-RestMethod -Uri "http://host.docker.internal:18082/embed" -Method Post -ContentType "application/json; charset=utf-8" -Body $bytes

Expect 1024-length vectors in the response.
