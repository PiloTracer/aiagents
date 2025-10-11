from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Protocol
from urllib.parse import urlparse


@dataclass(slots=True)
class SourceFile:
    uri: str
    path: Path
    content_type: str | None


class SourceAdapter(Protocol):
    def supports(self, uri: str) -> bool: ...

    def discover(self, uri: str, recursive: bool = True) -> Iterable[SourceFile]: ...


class LocalDirectoryAdapter:
    """Discover documents in the local filesystem."""

    def __init__(self, allowed_extensions: set[str]):
        self.allowed_extensions = {ext.lower() for ext in allowed_extensions}

    def supports(self, uri: str) -> bool:
        parsed = urlparse(uri)
        return parsed.scheme in ("", "file")

    def discover(self, uri: str, recursive: bool = True) -> Iterable[SourceFile]:
        parsed = urlparse(uri)
        path = Path(parsed.path or parsed.netloc or uri).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Source path not found: {path}")

        if path.is_file():
            yield from self._yield_if_supported(path)
            return

        if not recursive:
            for child in path.iterdir():
                if child.is_file():
                    yield from self._yield_if_supported(child)
            return

        for child in path.rglob("*"):
            if child.is_file():
                yield from self._yield_if_supported(child)

    def _yield_if_supported(self, path: Path) -> Iterable[SourceFile]:
        ext = path.suffix.lower()
        if self.allowed_extensions and ext not in self.allowed_extensions:
            return
        content_type, _ = mimetypes.guess_type(path.name)
        yield SourceFile(uri=path.as_uri(), path=path, content_type=content_type)


class SourceRegistry:
    """Registry that selects an adapter based on a URI."""

    def __init__(self, adapters: Iterable[SourceAdapter]):
        self.adapters: List[SourceAdapter] = list(adapters)

    def discover(self, uri: str, recursive: bool = True) -> Iterable[SourceFile]:
        for adapter in self.adapters:
            if adapter.supports(uri):
                yield from adapter.discover(uri, recursive=recursive)
                return
        raise ValueError(f"No source adapter configured for URI: {uri}")
