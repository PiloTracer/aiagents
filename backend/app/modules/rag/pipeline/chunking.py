from __future__ import annotations

from typing import Iterable

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .dto import ArtifactPayload, ChunkPayload


class Chunker:
    """Applies consistent chunking for extracted documents."""

    def __init__(self, *, chunk_size: int, chunk_overlap: int):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""],
        )

    def run(self, artifact: ArtifactPayload) -> Iterable[ChunkPayload]:
        splits = self.splitter.split_text(artifact.text)
        for idx, text in enumerate(splits):
            payload = dict(artifact.payload)
            payload.update(
                {
                    "area": artifact.area_slug,
                    "agent": artifact.agent_slug,
                    "source_uri": artifact.source_path.as_uri(),
                    "chunk_index": idx,
                }
            )
            yield ChunkPayload(
                artifact_id=artifact.artifact_id,
                index=idx,
                text=text,
                token_count=len(text.split()),
                payload=payload,
            )
