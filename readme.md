## AI Multi-agent System.

qdrant dashboard:
http://localhost:16433/dashboard

rest:
http://localhost:16433

## Docling Granite CLI (optional)

After the backend container is running you can launch the vision-language doc extraction without changing the image:

```
docker compose exec backend bash /app/bin/docling_vlm.sh /repo/DOCS/area1
```

The script uses the `docling` CLI with the Granite Docling weights and writes exports to `/tmp/docling_exports` inside the container (override with `DOC_EXTRACTION_OUTPUT`).
