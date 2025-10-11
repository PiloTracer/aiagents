#!/bin/bash
set -euo pipefail

if ! command -v docling >/dev/null 2>&1; then
  echo "docling CLI not found. Ensure the backend container has docling installed." >&2
  exit 1
fi

INPUT=${1:-}
if [[ -z "$INPUT" ]]; then
  echo "Usage: docling_vlm.sh <file|dir|url> [additional docling args...]" >&2
  exit 1
fi

shift || true

OUTPUT_DIR=${DOC_EXTRACTION_OUTPUT:-/tmp/docling_exports}
mkdir -p "$OUTPUT_DIR"

docling --to html --to md --pipeline vlm --vlm-model granite_docling "$INPUT" "$@" --output "$OUTPUT_DIR"

echo "Docling VLM export complete. Outputs in $OUTPUT_DIR"